"""Tests for GaggleCoordinator statistics import logic.

Covers _import_periods (aggregation, running sum, baseline continuity),
_fetch_and_import (one usage call + one plan call per poll, tiered-rate
selection), _async_update_data (failure-aware retry cadence), and the
two-stage baseline reach-back (_baseline_sums_before).

This coordinator is fundamentally simpler than the sibling electricity
integration's: there is no per-day backfill loop, no rewindow, no
NotImplementedError handling in the real flow (the gas usage endpoint is
now confirmed and implemented — see docs/gas-api.md). All recorder calls
are patched at the boundary — async_add_external_statistics and the
recorder instance — so no real SQLite DB is needed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gaggle.agl.models import (
    GasPastPeriod,
    GasUsageSummary,
    PlanRates,
)
from custom_components.gaggle.const import (
    CONF_ACCOUNT_NUMBER,
    CONF_CONTRACT_NUMBER,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    STAT_CONSUMPTION,
)
from custom_components.gaggle.coordinator import GaggleCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONTRACT = "9999999999"

_ENTRY_DATA = {
    CONF_REFRESH_TOKEN: "v1.testtoken",
    CONF_CONTRACT_NUMBER: _CONTRACT,
    CONF_ACCOUNT_NUMBER: "1234567890",
}


def _make_past_period(
    start: date, end: date, usage_mj: float, cost_aud: float
) -> GasPastPeriod:
    return GasPastPeriod(start=start, end=end, usage_mj=usage_mj, cost_aud=cost_aud)


def _empty_summary() -> GasUsageSummary:
    """A GasUsageSummary with no past periods and zeroed current-period fields."""
    today = datetime.now(UTC).date()
    return GasUsageSummary(
        period_start=today,
        period_end=today,
        current_day=0,
        max_days_in_period=0,
        cost_so_far_aud=0.0,
        usage_so_far_mj=0.0,
        projection_aud=0.0,
        past_periods=[],
    )


def _empty_plan() -> PlanRates:
    return PlanRates(
        product_name="",
        unit_rates=[],
        supply_charge_cents_per_day=0.0,
    )


def _make_coordinator(
    hass: HomeAssistant,
    client: MagicMock | None = None,
) -> GaggleCoordinator:
    """Create a GaggleCoordinator without running setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_ENTRY_DATA,
        unique_id="1234567890_9999999999",
    )
    entry.add_to_hass(hass)
    if client is None:
        client = AsyncMock()
    return GaggleCoordinator(hass, entry, client, _CONTRACT)


# These functions are imported with `from ... import` inside method bodies, so
# we patch them at the source module (not on the coordinator module itself).
_PATCH_ADD_STATS = (
    "homeassistant.components.recorder.statistics.async_add_external_statistics"
)
_PATCH_GET_INSTANCE = "homeassistant.helpers.recorder.get_instance"


def _mock_get_instance(return_value: dict) -> MagicMock:
    """Return a mock for get_instance whose executor_job returns return_value."""
    mock_instance = MagicMock()
    mock_instance.async_add_executor_job = AsyncMock(return_value=return_value)
    return MagicMock(return_value=mock_instance)


# ---------------------------------------------------------------------------
# _import_periods — aggregation
# ---------------------------------------------------------------------------


class TestImportPeriodsAggregation:
    async def test_two_periods_produce_two_rows(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass)
        periods = [
            _make_past_period(date(2026, 4, 16), date(2026, 6, 11), 2523.0, 98.252),
            _make_past_period(date(2026, 2, 11), date(2026, 4, 15), 1909.0, 76.516),
        ]

        with (
            patch(_PATCH_ADD_STATS) as mock_add,
            patch.object(
                coord, "_get_baseline_sums", new=AsyncMock(return_value=(0.0, 0.0))
            ),
        ):
            await coord._import_periods(periods)

        # Called twice: once for consumption, once for cost.
        assert mock_add.call_count == 2
        cons_stats = mock_add.call_args_list[0][0][2]
        assert len(cons_stats) == 2

    async def test_rows_keyed_at_period_end_date(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass)
        periods = [
            _make_past_period(date(2026, 4, 16), date(2026, 6, 11), 2523.0, 98.252)
        ]

        with (
            patch(_PATCH_ADD_STATS) as mock_add,
            patch.object(
                coord, "_get_baseline_sums", new=AsyncMock(return_value=(0.0, 0.0))
            ),
        ):
            await coord._import_periods(periods)

        cons_stats = mock_add.call_args_list[0][0][2]
        assert cons_stats[0]["start"] == datetime(2026, 6, 11, tzinfo=UTC)

    async def test_running_sum_is_cumulative_in_start_order(
        self, hass: HomeAssistant
    ) -> None:
        """Periods passed out of chronological order still produce a sum
        chain ordered by start date, not input order."""
        coord = _make_coordinator(hass)
        periods = [
            _make_past_period(date(2026, 4, 16), date(2026, 6, 11), 100.0, 10.0),
            _make_past_period(date(2026, 2, 11), date(2026, 4, 15), 50.0, 5.0),
        ]

        with (
            patch(_PATCH_ADD_STATS) as mock_add,
            patch.object(
                coord, "_get_baseline_sums", new=AsyncMock(return_value=(0.0, 0.0))
            ),
        ):
            await coord._import_periods(periods)

        cons_stats = mock_add.call_args_list[0][0][2]
        # Earlier period (Feb-Apr, 50.0) must be emitted first, then the
        # later one (Apr-Jun, 100.0) on top of it.
        sums = [s["sum"] for s in cons_stats]
        assert sums == [pytest.approx(50.0), pytest.approx(150.0)]

    async def test_baseline_offset_applied_to_running_total(
        self, hass: HomeAssistant
    ) -> None:
        coord = _make_coordinator(hass)
        periods = [_make_past_period(date(2026, 4, 16), date(2026, 6, 11), 100.0, 10.0)]

        with (
            patch(_PATCH_ADD_STATS) as mock_add,
            patch.object(
                coord, "_get_baseline_sums", new=AsyncMock(return_value=(500.0, 50.0))
            ),
        ):
            await coord._import_periods(periods)

        cons_stats = mock_add.call_args_list[0][0][2]
        cost_stats = mock_add.call_args_list[1][0][2]
        assert cons_stats[0]["sum"] == pytest.approx(600.0)
        assert cost_stats[0]["sum"] == pytest.approx(60.0)

    async def test_latest_cumulative_updated(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass)
        periods = [
            _make_past_period(date(2026, 4, 16), date(2026, 6, 11), 100.0, 10.0),
            _make_past_period(date(2026, 2, 11), date(2026, 4, 15), 50.0, 5.0),
        ]

        with (
            patch(_PATCH_ADD_STATS),
            patch.object(
                coord, "_get_baseline_sums", new=AsyncMock(return_value=(0.0, 0.0))
            ),
        ):
            await coord._import_periods(periods)

        assert coord._latest_cumulative_usage == pytest.approx(150.0)
        assert coord._latest_cumulative_cost_aud == pytest.approx(15.0)

    async def test_empty_periods_skips_import(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass)
        mock_baseline = AsyncMock(return_value=(0.0, 0.0))

        with (
            patch(_PATCH_ADD_STATS) as mock_add,
            patch.object(coord, "_get_baseline_sums", new=mock_baseline),
        ):
            await coord._import_periods([])

        mock_add.assert_not_called()
        mock_baseline.assert_not_called()

    async def test_baseline_looked_up_at_earliest_period_start(
        self, hass: HomeAssistant
    ) -> None:
        """The baseline cutoff must be the EARLIEST period's start date, so a
        later poll's baseline lookup never reads a sum from a period about
        to be (re)written — same class of guard as the sibling electricity
        integration's hourly baseline cutoff (AGENTS.md)."""
        coord = _make_coordinator(hass)
        periods = [
            _make_past_period(date(2026, 4, 16), date(2026, 6, 11), 100.0, 10.0),
            _make_past_period(date(2026, 2, 11), date(2026, 4, 15), 50.0, 5.0),
        ]
        mock_baseline = AsyncMock(return_value=(0.0, 0.0))

        with (
            patch(_PATCH_ADD_STATS),
            patch.object(coord, "_get_baseline_sums", new=mock_baseline),
        ):
            await coord._import_periods(periods)

        mock_baseline.assert_awaited_once()
        _, _, cutoff_arg = mock_baseline.call_args[0]
        assert cutoff_arg == datetime(2026, 2, 11, tzinfo=UTC)


# ---------------------------------------------------------------------------
# _import_periods — stat_id and metadata
# ---------------------------------------------------------------------------


class TestImportPeriodsStatId:
    async def test_statistic_id_contains_domain_and_contract(
        self, hass: HomeAssistant
    ) -> None:
        coord = _make_coordinator(hass)
        periods = [_make_past_period(date(2026, 4, 16), date(2026, 6, 11), 100.0, 10.0)]

        with (
            patch(_PATCH_ADD_STATS) as mock_add,
            patch.object(
                coord, "_get_baseline_sums", new=AsyncMock(return_value=(0.0, 0.0))
            ),
        ):
            await coord._import_periods(periods)

        cons_meta = mock_add.call_args_list[0][0][1]
        expected_id = f"{DOMAIN}:{STAT_CONSUMPTION}_{_CONTRACT}"
        assert cons_meta["statistic_id"] == expected_id
        assert cons_meta["source"] == DOMAIN

    async def test_metadata_has_correct_unit_and_has_sum(
        self, hass: HomeAssistant
    ) -> None:
        from custom_components.gaggle.const import GAS_USAGE_UNIT

        coord = _make_coordinator(hass)
        periods = [_make_past_period(date(2026, 4, 16), date(2026, 6, 11), 100.0, 10.0)]

        with (
            patch(_PATCH_ADD_STATS) as mock_add,
            patch.object(
                coord, "_get_baseline_sums", new=AsyncMock(return_value=(0.0, 0.0))
            ),
        ):
            await coord._import_periods(periods)

        cons_meta = mock_add.call_args_list[0][0][1]
        assert cons_meta["unit_of_measurement"] == GAS_USAGE_UNIT
        assert cons_meta["has_sum"] is True
        assert cons_meta["unit_class"] == "energy"

        cost_meta = mock_add.call_args_list[1][0][1]
        assert cost_meta["unit_of_measurement"] == "AUD"
        assert cost_meta["unit_class"] is None


# ---------------------------------------------------------------------------
# _async_setup — a no-op
# ---------------------------------------------------------------------------


class TestAsyncSetupIsNoop:
    async def test_setup_does_not_call_client(self, hass: HomeAssistant) -> None:
        mock_client = AsyncMock()
        coord = _make_coordinator(hass, client=mock_client)
        await coord._async_setup()
        mock_client.async_get_gas_usage_basic.assert_not_called()
        mock_client.async_get_plan.assert_not_called()


# ---------------------------------------------------------------------------
# _async_update_data — failure-aware cadence
# ---------------------------------------------------------------------------


class TestUpdateDataAuthError:
    async def test_auth_error_raises_config_entry_auth_failed(
        self, hass: HomeAssistant
    ) -> None:
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.gaggle.agl.client import AGLAuthError

        coord = _make_coordinator(hass)

        with (
            patch.object(
                coord,
                "_fetch_and_import",
                new_callable=AsyncMock,
                side_effect=AGLAuthError("token revoked"),
            ),
            pytest.raises(ConfigEntryAuthFailed),
        ):
            await coord._async_update_data()

    async def test_agl_error_raises_update_failed(self, hass: HomeAssistant) -> None:
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.gaggle.agl.client import AGLError

        coord = _make_coordinator(hass)

        with (
            patch.object(
                coord,
                "_fetch_and_import",
                new_callable=AsyncMock,
                side_effect=AGLError("network error"),
            ),
            pytest.raises(UpdateFailed),
        ):
            await coord._async_update_data()

    async def test_failed_poll_shortens_retry_interval(
        self, hass: HomeAssistant
    ) -> None:
        """A transient AGL failure retries after RETRY_INTERVAL_ON_ERROR
        instead of silently waiting a full poll cycle."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.gaggle.agl.client import AGLError
        from custom_components.gaggle.const import (
            RETRY_INTERVAL_ON_ERROR,
            SCAN_INTERVAL,
        )

        coord = _make_coordinator(hass)
        assert coord.update_interval == SCAN_INTERVAL
        with (
            patch.object(
                coord,
                "_fetch_and_import",
                new_callable=AsyncMock,
                side_effect=AGLError("HTTP 500 fetching AGL data"),
            ),
            pytest.raises(UpdateFailed),
        ):
            await coord._async_update_data()
        assert coord.update_interval == RETRY_INTERVAL_ON_ERROR

    async def test_successful_poll_restores_cadence(self, hass: HomeAssistant) -> None:
        from custom_components.gaggle.const import (
            RETRY_INTERVAL_ON_ERROR,
            SCAN_INTERVAL,
        )

        coord = _make_coordinator(hass)
        coord.update_interval = RETRY_INTERVAL_ON_ERROR  # as after a failure
        with patch.object(
            coord,
            "_fetch_and_import",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ):
            await coord._async_update_data()
        assert coord.update_interval == SCAN_INTERVAL

    async def test_auth_failure_leaves_interval_untouched(
        self, hass: HomeAssistant
    ) -> None:
        """Auth failures hand over to the reauth flow — no fast retry that
        would hammer a rejected token."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.gaggle.agl.client import AGLAuthError
        from custom_components.gaggle.const import SCAN_INTERVAL

        coord = _make_coordinator(hass)
        with (
            patch.object(
                coord,
                "_fetch_and_import",
                new_callable=AsyncMock,
                side_effect=AGLAuthError("token revoked"),
            ),
            pytest.raises(ConfigEntryAuthFailed),
        ):
            await coord._async_update_data()
        assert coord.update_interval == SCAN_INTERVAL


# ---------------------------------------------------------------------------
# _fetch_and_import — one usage call + one plan call per poll
# ---------------------------------------------------------------------------


class TestFetchAndImport:
    async def test_calls_usage_and_plan_exactly_once(self, hass: HomeAssistant) -> None:
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = _empty_summary()
        mock_client.async_get_plan.return_value = _empty_plan()
        coord = _make_coordinator(hass, client=mock_client)

        with patch.object(coord, "_import_periods", new_callable=AsyncMock):
            await coord._fetch_and_import()

        mock_client.async_get_gas_usage_basic.assert_awaited_once_with(_CONTRACT)
        mock_client.async_get_plan.assert_awaited_once_with(_CONTRACT)

    async def test_past_periods_forwarded_to_import(self, hass: HomeAssistant) -> None:
        summary = _empty_summary()
        summary.past_periods = [
            _make_past_period(date(2026, 4, 16), date(2026, 6, 11), 100.0, 10.0)
        ]
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = summary
        mock_client.async_get_plan.return_value = _empty_plan()
        coord = _make_coordinator(hass, client=mock_client)

        with patch.object(
            coord, "_import_periods", new_callable=AsyncMock
        ) as mock_import:
            await coord._fetch_and_import()

        mock_import.assert_awaited_once_with(summary.past_periods)

    async def test_last_bill_start_set_from_summary(self, hass: HomeAssistant) -> None:
        summary = _empty_summary()
        summary.period_start = date(2026, 6, 12)
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = summary
        mock_client.async_get_plan.return_value = _empty_plan()
        coord = _make_coordinator(hass, client=mock_client)

        with patch.object(coord, "_import_periods", new_callable=AsyncMock):
            await coord._fetch_and_import()

        assert coord.last_bill_start == date(2026, 6, 12)

    async def test_returns_gaggle_data_with_current_period_fields(
        self, hass: HomeAssistant
    ) -> None:
        from custom_components.gaggle.coordinator import GaggleData

        summary = _empty_summary()
        summary.usage_so_far_mj = 3441.21
        summary.cost_so_far_aud = 159.20
        summary.projection_aud = 211.60
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = summary
        mock_client.async_get_plan.return_value = _empty_plan()
        coord = _make_coordinator(hass, client=mock_client)

        with patch.object(coord, "_import_periods", new_callable=AsyncMock):
            result = await coord._fetch_and_import()

        assert isinstance(result, GaggleData)
        assert result.consumption_period_usage == pytest.approx(3441.21)
        assert result.consumption_period_cost_aud == pytest.approx(159.20)
        assert result.projection_cost_aud == pytest.approx(211.60)

    async def test_supply_charge_extracted_from_plan(self, hass: HomeAssistant) -> None:
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = _empty_summary()
        mock_client.async_get_plan.return_value = PlanRates(
            product_name="Special Saver",
            unit_rates=[
                {
                    "kind": "detail",
                    "type": "c/MJ",
                    "price": 3.9875,
                    "title": "First 1644 MJ",
                },
                {
                    "kind": "detail",
                    "type": "c/day",
                    "price": 79.9755,
                    "title": "Supply charge",
                },
            ],
            supply_charge_cents_per_day=79.9755,
        )
        coord = _make_coordinator(hass, client=mock_client)

        with patch.object(coord, "_import_periods", new_callable=AsyncMock):
            result = await coord._fetch_and_import()

        assert result.supply_charge_aud_per_day == pytest.approx(0.799755)

    async def test_unit_rate_picks_last_tier(self, hass: HomeAssistant) -> None:
        """Real gas plans are tiered (First/Next/Thereafter); the coordinator
        picks the LAST c/MJ detail row as a documented simplification."""
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = _empty_summary()
        mock_client.async_get_plan.return_value = PlanRates(
            product_name="Special Saver",
            unit_rates=[
                {
                    "kind": "detail",
                    "type": "c/MJ",
                    "price": 3.9875,
                    "title": "First 1644 MJ",
                },
                {
                    "kind": "detail",
                    "type": "c/MJ",
                    "price": 3.7477,
                    "title": "Next 1314 MJ",
                },
                {
                    "kind": "detail",
                    "type": "c/MJ",
                    "price": 2.563,
                    "title": "Thereafter",
                },
            ],
            supply_charge_cents_per_day=0.0,
        )
        coord = _make_coordinator(hass, client=mock_client)

        with patch.object(coord, "_import_periods", new_callable=AsyncMock):
            result = await coord._fetch_and_import()

        assert result.unit_rate_aud_per_unit == pytest.approx(0.02563)

    async def test_unit_rate_none_when_no_mj_rows(self, hass: HomeAssistant) -> None:
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = _empty_summary()
        mock_client.async_get_plan.return_value = PlanRates(
            product_name="Special Saver",
            unit_rates=[
                {
                    "kind": "detail",
                    "type": "c/day",
                    "price": 79.9755,
                    "title": "Supply charge",
                },
            ],
            supply_charge_cents_per_day=79.9755,
        )
        coord = _make_coordinator(hass, client=mock_client)

        with patch.object(coord, "_import_periods", new_callable=AsyncMock):
            result = await coord._fetch_and_import()

        assert result.unit_rate_aud_per_unit is None

    async def test_cumulative_fields_reflect_import_result(
        self, hass: HomeAssistant
    ) -> None:
        mock_client = AsyncMock()
        mock_client.async_get_gas_usage_basic.return_value = _empty_summary()
        mock_client.async_get_plan.return_value = _empty_plan()
        coord = _make_coordinator(hass, client=mock_client)

        async def _fake_import(_periods: object) -> None:
            coord._latest_cumulative_usage = 4432.0
            coord._latest_cumulative_cost_aud = 285.05

        with patch.object(coord, "_import_periods", side_effect=_fake_import):
            result = await coord._fetch_and_import()

        assert result.latest_cumulative_usage == pytest.approx(4432.0)
        assert result.latest_cumulative_cost_aud == pytest.approx(285.05)


# ---------------------------------------------------------------------------
# Baseline lookup — two-stage reach-back design
# ---------------------------------------------------------------------------


class TestBaselineReachBack:
    """_baseline_sums_before backs the period-statistics baseline lookup.

    Two-stage: a cheap bounded window, then a reach-back to the start of
    recorded history for anything still missing — guards against an older
    already-imported period aging out of AGL's returned window and
    resetting the cumulative sum to 0.0 (a downward TOTAL_INCREASING step).
    """

    async def test_reaches_back_when_absent_from_narrow_window(
        self, hass: HomeAssistant
    ) -> None:
        from custom_components.gaggle.coordinator import _EARLIEST_HISTORY

        coord = _make_coordinator(hass)
        stat_id = f"{DOMAIN}:{STAT_CONSUMPTION}_{_CONTRACT}"
        before = datetime(2026, 6, 1, tzinfo=UTC)

        def _executor(_func: object, _hass: object, start_dt: datetime, *_rest: object):
            if start_dt == _EARLIEST_HISTORY:
                return {stat_id: [{"sum": 5.0}, {"sum": 42.0}]}
            return {}

        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(side_effect=_executor)
        with patch(_PATCH_GET_INSTANCE, MagicMock(return_value=mock_instance)):
            out = await coord._baseline_sums_before({stat_id}, before)

        assert out[stat_id] == pytest.approx(42.0)
        # Two recorder calls: the narrow window, then the reach-back fallback.
        assert mock_instance.async_add_executor_job.await_count == 2

    async def test_no_reach_back_when_present_in_window(
        self, hass: HomeAssistant
    ) -> None:
        coord = _make_coordinator(hass)
        stat_id = f"{DOMAIN}:{STAT_CONSUMPTION}_{_CONTRACT}"
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(
            return_value={stat_id: [{"sum": 9.0}]}
        )
        with patch(_PATCH_GET_INSTANCE, MagicMock(return_value=mock_instance)):
            out = await coord._baseline_sums_before(
                {stat_id}, datetime(2026, 6, 1, tzinfo=UTC)
            )
        assert out[stat_id] == pytest.approx(9.0)
        assert mock_instance.async_add_executor_job.await_count == 1

    async def test_no_rows_anywhere_resolves_to_zero(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass)
        stat_id = f"{DOMAIN}:{STAT_CONSUMPTION}_{_CONTRACT}"
        with patch(_PATCH_GET_INSTANCE, _mock_get_instance({})):
            out = await coord._baseline_sums_before({stat_id}, datetime.now(UTC))
        assert out[stat_id] == 0.0

    async def test_empty_ids_short_circuits(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass)
        assert await coord._baseline_sums_before(set(), datetime.now(UTC)) == {}
