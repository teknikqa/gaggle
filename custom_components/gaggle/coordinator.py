"""DataUpdateCoordinator for gaggle.

gaggle pulls AGL Australia GAS smart-meter data into HA's Energy dashboard.
Historical data (past intervals) is pushed to HA's recorder via
async_add_external_statistics() rather than a live state update. This
ensures the Energy dashboard attributes consumption to the interval it
actually occurred in, not to the time of the poll.

Backfill strategy: first install pulls up to BACKFILL_DAYS of history, but
throttled to BACKFILL_CHUNK_DAYS per 24 h poll so we don't hammer the AGL
BFF on startup. Smart endpoint selection per day: days inside the current
billing period use the "Current" endpoint; older days use "Previous".

Once initial backfill is complete, every poll re-fetches the trailing
REWINDOW_DAYS so AGL's day-late AEMO backfills self-heal — a slot first
returned as a placeholder is overwritten once AGL has the real read. The
recorder is idempotent on (statistic_id, start), so the overwrite is safe.

IMPORTANT — gas usage endpoint not yet captured (Phase 0, see
docs/gas-api.md): `AglClient.async_get_gas_usage_summary` and
`async_get_gas_usage_hourly[_previous]` are explicit NotImplementedError
stubs. This coordinator catches that once per cycle and simply leaves the
usage/cost data unpopulated (None) rather than crashing the whole update —
the plan-derived fields (supply charge; a flat usage rate once a real
capture confirms the rate shape) still populate normally from the real,
fuel-agnostic plan endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .agl.client import (
    AGLAuthError,
    AGLError,
    AGLRateLimitError,
    AGLTransportError,
)
from .const import (
    BACKFILL_CHUNK_DAYS,
    BACKFILL_DAYS,
    BACKFILL_INTER_REQUEST_DELAY,
    DOMAIN,
    GAS_USAGE_UNIT,
    RETRY_INTERVAL_ON_ERROR,
    REWINDOW_DAYS,
    SCAN_INTERVAL_HOURLY,
    STAT_CONSUMPTION,
    STAT_COST,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .agl.client import AglClient
    from .agl.models import IntervalReading

_LOGGER = logging.getLogger(__name__)

# Lower bound for the reach-back baseline lookup. Earlier than any possible
# recorder row, so a series whose last stored hour predates the normal
# look-back window is still found. Bounded ABOVE at the fetch cutoff by the
# caller, so it never reads a sum from inside the rewindow being rewritten.
_EARLIEST_HISTORY = datetime(1970, 1, 1, tzinfo=UTC)


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


@dataclass
class GaggleData:
    """Typed coordinator data returned from _async_update_data.

    consumption_period_usage / consumption_period_cost_aud / unit_rate_aud_per_unit
    stay None until their upstream source is available: the bill-period
    fields depend on the gas usage-summary endpoint (a NotImplementedError
    stub — Phase 0, see docs/gas-api.md); the unit rate depends on the
    gas plan rate-shape TODO in coordinator._fetch_and_import. The
    coordinator does not fake data to make those sensors read a value —
    they surface as `unknown` in HA until the real data is available.
    """

    consumption_period_usage: float | None
    consumption_period_cost_aud: float | None
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
            update_interval=SCAN_INTERVAL_HOURLY,
            config_entry=entry,
        )
        self.client = client
        self.contract_number = contract_number
        self._latest_cumulative_usage: float = 0.0
        self._latest_cumulative_cost_aud: float = 0.0
        # Last-seen bill period start — surfaced in diagnostics so period-vs-app
        # mismatch reports can be reasoned about without asking the user.
        # Stays None until the gas usage-summary endpoint is implemented.
        self.last_bill_start: date | None = None
        # True when the last sweep was HALTED mid-chunk (429/transport) —
        # _async_update_data schedules a fast retry off this instead of
        # waiting a full day for the halted chunk.
        self._sweep_halted: bool = False

    async def _async_setup(self) -> None:
        """No-op: first-install backfill is handled incrementally in _fetch_and_import."""

    async def _async_update_data(self) -> GaggleData:
        """Fetch yesterday's intervals, import statistics, return sensor data.

        Failure-aware cadence: a failed poll retries after
        RETRY_INTERVAL_ON_ERROR instead of silently waiting a full 24 h (a
        transient AGL error at poll time would otherwise look exactly like
        "the poll never ran"). The 24 h cadence is restored on the next
        clean success. ConfigEntryAuthFailed is left alone — the reauth flow
        owns that path, and hammering a rejected token would not help.

        A cycle whose backfill sweep was HALTED (429 or transport failure)
        still returns data — the partial import is safe and the sensors keep
        their values — but schedules the fast retry too, so the halted chunk
        is re-fetched in 30 minutes rather than tomorrow.
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
                    SCAN_INTERVAL_HOURLY,
                )
                self.update_interval = RETRY_INTERVAL_ON_ERROR
            raise UpdateFailed(str(err)) from err
        if self._sweep_halted:
            if self.update_interval != RETRY_INTERVAL_ON_ERROR:
                _LOGGER.info(
                    "Backfill sweep halted mid-chunk; retrying in %s",
                    RETRY_INTERVAL_ON_ERROR,
                )
                self.update_interval = RETRY_INTERVAL_ON_ERROR
        elif self.update_interval != SCAN_INTERVAL_HOURLY:
            _LOGGER.info("Poll succeeded; restoring %s cadence", SCAN_INTERVAL_HOURLY)
            self.update_interval = SCAN_INTERVAL_HOURLY
        return data

    async def _fetch_and_import(self) -> GaggleData:
        """Core update: fetch missing intervals + trailing rewindow, return data."""
        stat_id_cons = f"{DOMAIN}:{STAT_CONSUMPTION}_{self.contract_number}"
        stat_id_cost = f"{DOMAIN}:{STAT_COST}_{self.contract_number}"

        # Plan/rates fetch is real and fuel-agnostic — keep it unconditional.
        plan = await self.client.async_get_plan(self.contract_number)

        # Resume points for both series (seeds the cumulative-total sensors
        # even on a cycle where the usage fetch below can't run yet).
        last_cons_sum, last_cons_date = await self._get_last_stat(stat_id_cons)
        last_cost_sum, _ = await self._get_last_stat(stat_id_cost)
        self._latest_cumulative_usage = last_cons_sum or 0.0
        self._latest_cumulative_cost_aud = last_cost_sum or 0.0

        # Bill-period summary + interval backfill both depend on the gas
        # usage endpoints, which are NotImplementedError stubs pending
        # Phase 0 (see docs/gas-api.md). Caught once here rather than per
        # backfill day — see module docstring.
        period_usage: float | None = None
        period_cost: float | None = None
        bill_start: date | None = None
        try:
            summary = await self.client.async_get_gas_usage_summary(
                self.contract_number
            )
        except NotImplementedError as err:
            _LOGGER.debug("Gas usage summary not available yet: %s", err)
        else:
            bill_start = summary.start
            period_usage = _safe_float(summary.consumption_kwh)
            period_cost = _safe_float(
                (summary.cost_label or "").lstrip("$").replace(",", "")
            )

        self.last_bill_start = bill_start

        # AGL `dateTime` slots are UTC; using `date.today()` (OS local time)
        # would skew the fetch range by a day around midnight in non-UTC zones.
        today = datetime.now(UTC).date()
        yesterday = today - timedelta(days=1)
        cons_range = self._chunked_range(
            self._resolve_fetch_start(today, last_cons_date), yesterday
        )

        try:
            await self._fetch_range(cons_range, bill_start)
        except NotImplementedError as err:
            _LOGGER.debug("Gas interval usage endpoint not available yet: %s", err)
            self._sweep_halted = False

        # Flat usage-rate extraction: intentionally NOT implemented. See the
        # TODO in agl/parser.py::parse_plan — the confirmed rate-type string
        # for a gas usage row (c/MJ, c/m³, or something else) is unknown
        # until Phase 0 captures a real gas plan response. Guessing risks a
        # silently wrong rate; leaving it None reads as `unavailable`.
        unit_rate_aud: float | None = None

        supply_charge_aud: float | None = None
        if plan.supply_charge_cents_per_day:
            supply_charge_aud = plan.supply_charge_cents_per_day / 100.0

        return GaggleData(
            consumption_period_usage=period_usage,
            consumption_period_cost_aud=period_cost,
            unit_rate_aud_per_unit=unit_rate_aud,
            supply_charge_aud_per_day=supply_charge_aud,
            latest_cumulative_usage=self._latest_cumulative_usage,
            latest_cumulative_cost_aud=self._latest_cumulative_cost_aud,
        )

    def _resolve_fetch_start(
        self,
        today: date,
        last_stat_date: date | None,
    ) -> date:
        """Choose the first day to fetch per the resume-strategy decision tree.

        - First install: backfill from BACKFILL_DAYS ago.
        - Big gap (> REWINDOW_DAYS behind): resume incrementally from
          last_stat_date + 1.
        - Normal operation: re-fetch the trailing REWINDOW_DAYS so AGL's
          day-late AEMO backfills self-heal.

        The cumulative-sum baseline is NOT chosen here. _import_intervals looks
        it up from the recorder using the actual earliest fetched-interval hour
        as the cutoff. Deriving it from fetch_start UTC midnight was wrong on
        the sibling electricity integration: AGL's period= query is
        interpreted in the contract's local timezone, so the first new
        interval lands at (fetch_start - 1)T14:00Z for an AEST account; a
        cutoff at fetch_start T00:00Z folded ~10 h of about-to-be-overwritten
        old sums into the baseline, producing a phantom kWh jump in the
        cumulative sum every local midnight.
        """
        backfill_floor = today - timedelta(days=BACKFILL_DAYS)
        if last_stat_date is None:
            return backfill_floor
        if last_stat_date < today - timedelta(days=REWINDOW_DAYS):
            return last_stat_date + timedelta(days=1)
        return max(today - timedelta(days=REWINDOW_DAYS), backfill_floor)

    @staticmethod
    def _chunked_range(start: date, yesterday: date) -> tuple[date, date] | None:
        """Cap a series' fetch start to one BACKFILL_CHUNK_DAYS chunk.

        Returns None when the series has nothing to fetch (start past
        yesterday — AGL never has data for today).
        """
        if start > yesterday:
            return None
        return start, min(yesterday, start + timedelta(days=BACKFILL_CHUNK_DAYS - 1))

    async def _get_last_stat(self, stat_id: str) -> tuple[float | None, date | None]:
        """Return (last_sum, last_date) for stat_id, or (None, None) if no rows."""
        from homeassistant.components.recorder.statistics import (
            get_last_statistics,
        )
        from homeassistant.helpers.recorder import get_instance

        last = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, stat_id, True, {"start", "sum"}
        )
        if not last or stat_id not in last:
            return None, None
        rows = last[stat_id]
        if not rows:
            return None, None
        row = rows[0]
        val = row.get("sum")
        raw_start: float = row.get("start") or 0.0
        last_sum = float(val) if val is not None else None
        last_date: date | None = None
        if raw_start:
            last_date = datetime.fromtimestamp(raw_start, tz=UTC).date()
        return last_sum, last_date

    async def _get_baseline_sums(
        self,
        stat_id_cons: str,
        stat_id_cost: str,
        before_dt: datetime,
    ) -> tuple[float, float]:
        """Return cumulative sums at the last hour strictly before before_dt.

        Used by the trailing-rewindow path so newly-imported rows resume from
        the correct baseline. Looks back 2 days to tolerate sparse data, with a
        reach-back fallback for a series whose last row predates that window.
        Returns (0.0, 0.0) if the series has no stored rows at all.
        """
        sums = await self._baseline_sums_before(
            {stat_id_cons, stat_id_cost}, before_dt, look_back_days=2
        )
        return sums[stat_id_cons], sums[stat_id_cost]

    async def _baseline_sums_before(
        self, stat_ids: set[str], before_dt: datetime, *, look_back_days: int
    ) -> dict[str, float]:
        """Return {stat_id: cumulative sum at the last hour strictly before before_dt}.

        Resolution is two-stage. First a cheap bounded window of `look_back_days`
        ending at before_dt — this covers the normal case in a single batched
        recorder call. A series with NO rows in that window is then resolved
        with a second lookup that reaches back to the start of recorded
        history (still bounded above at before_dt).

        Both stages stay strictly *before* before_dt (never get_last_statistics)
        precisely so it cannot read a sum from inside the rewindow rows about
        to be rewritten. A series with no stored rows at all resolves to 0.0.
        """
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

        out = await _last_sums(before_dt - timedelta(days=look_back_days), stat_ids)
        missing = {stat_id for stat_id in stat_ids if stat_id not in out}
        if missing:
            out.update(await _last_sums(_EARLIEST_HISTORY, missing))
        for stat_id in stat_ids:
            out.setdefault(stat_id, 0.0)
        return out

    # C901 note: kept as one function (429-break / smart-endpoint-selection
    # logic) — the per-series-range complexity of the sibling electricity
    # integration that originally justified splitting this further is gone
    # now that gaggle only ever tracks a single (gas) series.
    async def _fetch_range(
        self,
        cons_range: tuple[date, date] | None,
        bill_start: date | None,
    ) -> bool:
        """Fetch the consumption day range with smart endpoint selection, then import.

        Returns True if the sweep reached the end of the range, False if an
        AGL 429/transport failure halted it early — the caller keeps a
        halted-sweep fast retry pending in that case.

        Sleeps between requests so a chunk-of-7 first-install backfill doesn't
        hammer AGL's BFF in under a second. AGL rate limits are account-wide.
        """
        self._sweep_halted = False
        if cons_range is None:
            return True
        start, end = cons_range

        all_intervals: list[IntervalReading] = []
        current = start
        first = True
        rate_limited = False
        while current <= end:
            if not first:
                await asyncio.sleep(BACKFILL_INTER_REQUEST_DELAY)
            first = False
            previous = bill_start is not None and current < bill_start
            readings = await self._fetch_day_consumption(current, previous)
            if readings is None:  # rate-limited/transport — halt the chunk
                rate_limited = True
                break
            all_intervals.extend(readings)
            current += timedelta(days=1)

        if all_intervals:
            await self._import_intervals(all_intervals)

        self._sweep_halted = rate_limited
        return not rate_limited

    async def _fetch_day_consumption(
        self, day: date, previous: bool
    ) -> list[IntervalReading] | None:
        """Fetch one day of gas usage intervals.

        Returns [] on a skippable AGL HTTP error (logged, the loop continues)
        and None on AGLRateLimitError OR AGLTransportError so the caller halts
        the chunk. Transport failures (network blip, timeout, challenge page)
        are endpoint-wide and transient — skipping the day would advance the
        resume point past it and leave a permanent hole; halting retries the
        whole chunk next cycle instead.

        NotImplementedError (the gas usage-fetch stub) is deliberately NOT
        caught here — it propagates to _fetch_and_import, which handles it
        once per cycle rather than retrying it on every remaining day.
        """
        try:
            if previous:
                return await self.client.async_get_gas_usage_hourly_previous(
                    self.contract_number, day
                )
            return await self.client.async_get_gas_usage_hourly(
                self.contract_number, day
            )
        except AGLRateLimitError as err:
            _LOGGER.warning(
                "AGL rate-limited at %s; halting backfill chunk: %s", day, err
            )
            return None
        except AGLTransportError as err:
            _LOGGER.warning(
                "Transport failure at %s; halting backfill chunk: %s", day, err
            )
            return None
        except AGLError as err:
            _LOGGER.debug("Fetch skip %s: %s", day, err)
            return []

    @staticmethod
    def _bucket_hourly(
        intervals: list[IntervalReading],
    ) -> tuple[dict[datetime, float], dict[datetime, float]]:
        """Bucket 30-min intervals into hourly (consumption, cost) sums."""
        hour_cons: dict[datetime, float] = {}
        hour_cost: dict[datetime, float] = {}
        for r in intervals:
            h = r.dt.replace(minute=0, second=0, microsecond=0)
            hour_cons[h] = hour_cons.get(h, 0.0) + r.kwh
            hour_cost[h] = hour_cost.get(h, 0.0) + r.cost_aud
        return hour_cons, hour_cost

    async def _import_intervals(self, intervals: list[IntervalReading]) -> None:
        """Aggregate 30-min intervals to hourly and push to recorder statistics.

        The cumulative-sum baseline is looked up against the recorder using
        the hour right before the EARLIEST fetched interval as the cutoff —
        never a fetch_start-derived UTC midnight (see _resolve_fetch_start).
        """
        hour_cons, hour_cost = self._bucket_hourly(intervals)

        # Nothing fetched → nothing to import, and no baseline lookup needed.
        if not hour_cons:
            return

        stat_id_cons = f"{DOMAIN}:{STAT_CONSUMPTION}_{self.contract_number}"
        stat_id_cost = f"{DOMAIN}:{STAT_COST}_{self.contract_number}"

        # Baseline cutoff = the earliest fetched interval hour. _get_baseline_sums
        # returns the cumulative sum at the last hour strictly before it, so the
        # to-be-overwritten rewindow rows are excluded regardless of timezone/DST.
        cutoff = min(hour_cons)
        initial_cons_sum, initial_cost_sum = await self._get_baseline_sums(
            stat_id_cons, stat_id_cost, cutoff
        )

        contract = self.contract_number
        cons_sum = self._emit_series(
            stat_id_cons,
            f"AGL Gas Consumption ({contract})",
            GAS_USAGE_UNIT,
            "energy",
            hour_cons,
            initial_cons_sum,
        )
        cost_sum = self._emit_series(
            stat_id_cost,
            f"AGL Gas Cost ({contract})",
            "AUD",
            None,
            hour_cost,
            initial_cost_sum,
        )

        # Update the in-memory cumulatives for the device-card sensors.
        self._latest_cumulative_usage = cons_sum
        self._latest_cumulative_cost_aud = cost_sum

    def _emit_series(
        self,
        stat_id: str,
        name: str,
        unit: str,
        unit_class: str | None,
        hourly: dict[datetime, float],
        initial_sum: float,
    ) -> float:
        """Build the cumulative hourly rows for one series and import them.

        Idempotent on (statistic_id, start) — safe for rewindow overwrites.
        Returns the final cumulative sum.
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
        for h in sorted(hourly):
            running += hourly[h]
            stats.append(StatisticData(start=h, state=hourly[h], sum=running))
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
