"""DataUpdateCoordinator for gaggle.

gaggle pulls AGL Australia GAS smart-meter data into HA's Energy dashboard.

CONFIRMED real shape (Phase 0 capture, 2026-07-30, see docs/gas-api.md):
a BASIC (non-smart) gas meter has no interval or daily data. One call to
``async_get_gas_usage_basic`` returns the current billing period (an
ESTIMATE + AGL's own bill PROJECTION, not a meter read) and a window of
already-billed PAST periods with real totals. This is a fundamentally
different shape from the sibling electricity integration's per-day
interval backfill:

  - No throttled multi-request backfill loop — one GET per poll gets
    everything AGL currently has.
  - Historical data (past_periods) is pushed to HA's recorder via
    async_add_external_statistics() exactly as haggle does, but as ONE
    SPARSE POINT PER COMPLETED BILLING PERIOD (~bimonthly) rather than an
    hourly series. There is no smooth daily/hourly Energy-dashboard chart
    for a basic gas meter — there's no underlying data to build one from.
  - The current period's estimate/projection are sensor-only data (see
    sensor.py) — never imported as statistics, since they are not a
    confirmed meter read and would misrepresent the recorder's "sum" as a
    real historical fact.

The cumulative-sum baseline for statistics import is still looked up from
the recorder (not assumed to start at 0) for the same reason the sibling
electricity integration does this: AGL's response is a bounded WINDOW of
past periods (5 in the confirmed capture), not full account history, so an
older already-imported period can eventually age out of what a given poll
returns. Without a baseline lookup, that would restart the cumulative sum
from a wrong point and step the recorder's TOTAL_INCREASING sum backwards.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .agl.client import AGLAuthError, AGLError
from .const import (
    DOMAIN,
    GAS_RATE_TYPE,
    GAS_USAGE_UNIT,
    RETRY_INTERVAL_ON_ERROR,
    SCAN_INTERVAL,
    STAT_CONSUMPTION,
    STAT_COST,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .agl.client import AglClient
    from .agl.models import GasPastPeriod

_LOGGER = logging.getLogger(__name__)

# Lower bound for the reach-back baseline lookup. Earlier than any possible
# recorder row, so a series whose last stored row predates the normal
# look-back window is still found. Bounded ABOVE at the fetch cutoff by the
# caller, so it never reads a sum from a period about to be (re)written.
_EARLIEST_HISTORY = datetime(1970, 1, 1, tzinfo=UTC)
# Look-back window for the cheap first-stage baseline query. Periods are
# ~60 days apart (bimonthly billing); 400 days comfortably covers a full
# year of periods so the common case resolves without the reach-back stage.
_BASELINE_LOOK_BACK_DAYS = 400


def _safe_float(raw: Any) -> float:
    """Coerce raw API value to a non-negative finite float, defaulting to 0.0."""
    try:
        value = float(raw)
    except TypeError, ValueError:
        return 0.0
    if not math.isfinite(value) or value < 0:
        _LOGGER.warning("Rejecting non-finite/negative coordinator value: %r", raw)
        return 0.0
    return value


def _midnight_utc(day: date) -> datetime:
    """Midnight UTC of a calendar date, as an hour-aligned recorder timestamp.

    A documented simplification: the period actually ends at LOCAL
    midnight, not UTC midnight, so this can place a period's statistic row
    up to ~14h off the "true" boundary depending on the contract's
    timezone. Unlike the sibling electricity integration's hourly rewindow
    (where an equivalent shortcut caused a real double-counted phantom
    spike, AGENTS.md), a period row is written ONCE and never revisited
    with a different baseline, so the only consequence here is a coarse
    chart bar landing on the adjacent day for some timezones — not a
    correctness/double-counting bug. Acceptable given periods are ~60 days
    apart; revisit if this ever needs day-precision.
    """
    return datetime.combine(day, time.min, tzinfo=UTC)


@dataclass
class GaggleData:
    """Typed coordinator data returned from _async_update_data.

    consumption_period_usage / consumption_period_cost_aud / projection_cost_aud
    are the current period's ESTIMATE and AGL's own PROJECTION — not a real
    meter read. They are sensor-only values (see sensor.py); they are never
    imported as statistics, unlike latest_cumulative_usage/cost_aud which
    mirror the gaggle:* statistics built from real past_periods.
    """

    consumption_period_usage: float | None
    consumption_period_cost_aud: float | None
    projection_cost_aud: float | None
    unit_rate_aud_per_unit: float | None
    supply_charge_aud_per_day: float | None
    latest_cumulative_usage: float  # cumulative total usage sensor
    latest_cumulative_cost_aud: float  # cumulative total cost sensor


class GaggleCoordinator(DataUpdateCoordinator[GaggleData]):
    """Fetches AGL gas data and drives statistics import."""

    config_entry: ConfigEntry[object]

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry[object],
        client: AglClient,
        contract_number: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self.contract_number = contract_number
        self._latest_cumulative_usage: float = 0.0
        self._latest_cumulative_cost_aud: float = 0.0
        # Last-seen bill period start — surfaced in diagnostics.
        self.last_bill_start: date | None = None

    async def _async_setup(self) -> None:
        """No-op: nothing to do before the first _async_update_data call."""

    async def _async_update_data(self) -> GaggleData:
        """Fetch the current gas usage summary, import period statistics, return sensor data.

        Failure-aware cadence: a failed poll retries after
        RETRY_INTERVAL_ON_ERROR instead of silently waiting a full day (a
        transient AGL error at poll time would otherwise look exactly like
        "the poll never ran"). SCAN_INTERVAL is restored on the next clean
        success. ConfigEntryAuthFailed is left alone — the reauth flow owns
        that path, and hammering a rejected token would not help.
        """
        try:
            data = await self._fetch_and_import()
        except AGLAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AGLError as err:
            if self.update_interval != RETRY_INTERVAL_ON_ERROR:
                _LOGGER.info(
                    "Poll failed (%s); retrying in %s instead of %s",
                    err,
                    RETRY_INTERVAL_ON_ERROR,
                    SCAN_INTERVAL,
                )
                self.update_interval = RETRY_INTERVAL_ON_ERROR
            raise UpdateFailed(str(err)) from err
        if self.update_interval != SCAN_INTERVAL:
            _LOGGER.info("Poll succeeded; restoring %s cadence", SCAN_INTERVAL)
            self.update_interval = SCAN_INTERVAL
        return data

    async def _fetch_and_import(self) -> GaggleData:
        """Core update: one usage call + one plan call, then import period statistics."""
        plan = await self.client.async_get_plan(self.contract_number)
        summary = await self.client.async_get_gas_usage_basic(self.contract_number)

        self.last_bill_start = summary.period_start

        await self._import_periods(summary.past_periods)

        # Tiered plan simplification: pick the LAST c/MJ detail row
        # (typically "Thereafter") rather than parsing usage thresholds out
        # of free-text titles. See agl/parser.py::parse_plan for the
        # rationale and limitation (under-reads for light users who never
        # reach that tier).
        unit_rate_aud: float | None = None
        for rate in plan.unit_rates:
            if rate.get("kind") == "detail" and rate.get("type") == GAS_RATE_TYPE:
                unit_rate_aud = _safe_float(rate.get("price")) / 100.0

        supply_charge_aud: float | None = None
        if plan.supply_charge_cents_per_day:
            supply_charge_aud = plan.supply_charge_cents_per_day / 100.0

        return GaggleData(
            consumption_period_usage=summary.usage_so_far_mj,
            consumption_period_cost_aud=summary.cost_so_far_aud,
            projection_cost_aud=summary.projection_aud,
            unit_rate_aud_per_unit=unit_rate_aud,
            supply_charge_aud_per_day=supply_charge_aud,
            latest_cumulative_usage=self._latest_cumulative_usage,
            latest_cumulative_cost_aud=self._latest_cumulative_cost_aud,
        )

    async def _get_baseline_sums(
        self, stat_id_cons: str, stat_id_cost: str, before_dt: datetime
    ) -> tuple[float, float]:
        """Return cumulative sums at the last row strictly before before_dt.

        Two-stage: a cheap batched window of _BASELINE_LOOK_BACK_DAYS ending
        at before_dt, with a reach-back fallback (to the start of recorded
        history) for a series with no rows in that window. Both stages stay
        strictly before before_dt so this never reads a sum from a period
        about to be (re)written. A series with no stored rows resolves to
        0.0.
        """
        sums = await self._baseline_sums_before({stat_id_cons, stat_id_cost}, before_dt)
        return sums[stat_id_cons], sums[stat_id_cost]

    async def _baseline_sums_before(
        self, stat_ids: set[str], before_dt: datetime
    ) -> dict[str, float]:
        if not stat_ids:
            return {}
        from homeassistant.components.recorder.statistics import (
            statistics_during_period,
        )
        from homeassistant.helpers.recorder import get_instance

        instance = get_instance(self.hass)

        async def _last_sums(start_dt: datetime, ids: set[str]) -> dict[str, float]:
            result = await instance.async_add_executor_job(
                statistics_during_period,
                self.hass,
                start_dt,
                before_dt,
                set(ids),
                "hour",
                None,
                {"sum"},
            )
            sums: dict[str, float] = {}
            for stat_id in ids:
                rows = result.get(stat_id) or []
                last = rows[-1].get("sum") if rows else None
                if last is not None:
                    sums[stat_id] = float(last)
            return sums

        out = await _last_sums(
            before_dt - timedelta(days=_BASELINE_LOOK_BACK_DAYS), stat_ids
        )
        missing = {stat_id for stat_id in stat_ids if stat_id not in out}
        if missing:
            out.update(await _last_sums(_EARLIEST_HISTORY, missing))
        for stat_id in stat_ids:
            out.setdefault(stat_id, 0.0)
        return out

    async def _import_periods(self, past_periods: list[GasPastPeriod]) -> None:
        """Import one HA statistic point per completed billing period.

        Idempotent on (statistic_id, start) — re-importing the same period
        AGL still returns on a later poll just overwrites with the same
        values, which is safe and simpler than tracking "did this change."
        """
        if not past_periods:
            return

        stat_id_cons = f"{DOMAIN}:{STAT_CONSUMPTION}_{self.contract_number}"
        stat_id_cost = f"{DOMAIN}:{STAT_COST}_{self.contract_number}"

        ordered = sorted(past_periods, key=lambda p: p.start)
        cutoff = _midnight_utc(ordered[0].start)
        initial_cons_sum, initial_cost_sum = await self._get_baseline_sums(
            stat_id_cons, stat_id_cost, cutoff
        )

        # Keyed at each period's END date: the date its total became known,
        # not the date it started accruing (see _midnight_utc docstring for
        # the UTC-vs-local simplification this still carries).
        period_cons: dict[datetime, float] = {}
        period_cost: dict[datetime, float] = {}
        for p in ordered:
            row_dt = _midnight_utc(p.end)
            period_cons[row_dt] = p.usage_mj
            period_cost[row_dt] = p.cost_aud

        contract = self.contract_number
        cons_sum = self._emit_series(
            stat_id_cons,
            f"AGL Gas Consumption ({contract})",
            GAS_USAGE_UNIT,
            "energy",
            period_cons,
            initial_cons_sum,
        )
        cost_sum = self._emit_series(
            stat_id_cost,
            f"AGL Gas Cost ({contract})",
            "AUD",
            None,
            period_cost,
            initial_cost_sum,
        )

        self._latest_cumulative_usage = cons_sum
        self._latest_cumulative_cost_aud = cost_sum

    def _emit_series(
        self,
        stat_id: str,
        name: str,
        unit: str,
        unit_class: str | None,
        rows: dict[datetime, float],
        initial_sum: float,
    ) -> float:
        """Build the cumulative rows for one series and import them.

        Idempotent on (statistic_id, start). Returns the final cumulative
        sum. Granularity-agnostic — the caller decides what `rows`' keys
        mean (period-end dates here; the sibling electricity integration
        uses hourly interval starts for the same method shape).
        """
        # Local imports: recorder must not be imported at module level.
        from homeassistant.components.recorder.models import (
            StatisticData,
            StatisticMeanType,
            StatisticMetaData,
        )
        from homeassistant.components.recorder.statistics import (
            async_add_external_statistics,
        )

        running = initial_sum
        stats: list[StatisticData] = []
        for dt in sorted(rows):
            running += rows[dt]
            stats.append(StatisticData(start=dt, state=rows[dt], sum=running))
        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                unit_class=unit_class,
                has_sum=True,
                name=name,
                source=DOMAIN,
                statistic_id=stat_id,
                unit_of_measurement=unit,
            ),
            stats,
        )
        return running
