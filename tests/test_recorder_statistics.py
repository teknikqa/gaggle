"""Recorder-backed statistics tests — the real engine, no boundary mocks.

Every other statistics test in this suite patches the recorder at the
boundary (async_add_external_statistics / get_instance). That mocked seam
is exactly where the repo's production defects escaped (the sibling
electricity integration's v0.3.0 phantom-midnight-spike class), so this
module re-runs the sum-chain scenario against phcc's `recorder_mock` — a
real in-memory SQLite recorder running HA's real statistics engine.
Slow-ish per test (~0.2 s) but a different failure domain: it catches
semantic drift between our import logic and the recorder's actual
cumulative-sum handling across HA releases.

Scenario map (each pins a real defect CLASS, adapted from the sibling
electricity integration this codebase was forked from):
- test_aged_out_period_baseline_continuity → the period-level analog of
  the v0.3.0 phantom-spike class: a later poll's response window no
  longer includes an older already-imported period, and the baseline
  lookup must still find it rather than resetting the sum chain to 0.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from itertools import pairwise
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.gaggle.agl.models import GasPastPeriod
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

# --- cpython gh-145754 shim -------------------------------------------------
# Python 3.14.2's unittest.mock resolves autospec signatures with
# inspect.signature(..., Format.VALUE), which evaluates PEP 649 deferred
# annotations.  phcc's async_test_recorder fixture autospec-patches recorder
# functions whose annotations name TYPE_CHECKING-only symbols, so fixture
# setup dies with NameError ('Recorder' at recorder/migration.py, 'Session'
# at helpers/recorder.py).  Fixed upstream (cpython PR #146191, 3.14 branch);
# until every dev/CI interpreter carries the fix, materialise the two names.
# Harmless where the interpreter is already fixed (hasattr guards).


def _materialize_recorder_annotations() -> None:
    from homeassistant.components import recorder
    from homeassistant.components.recorder import migration
    from homeassistant.helpers import recorder as recorder_helper
    from sqlalchemy.orm.session import Session

    if not hasattr(migration, "Recorder"):
        migration.Recorder = recorder.Recorder  # type: ignore[attr-defined]
    if not hasattr(recorder_helper, "Session"):
        recorder_helper.Session = Session  # type: ignore[attr-defined]


_materialize_recorder_annotations()

# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(
    recorder_mock, enable_custom_integrations: None
) -> None:
    """Override the suite-wide autouse fixture for this module only.

    The conftest version depends on `hass` alone, which would set hass up
    before the recorder — phcc's `recorder_db_url` asserts the recorder
    fixtures initialise first.  Requesting `recorder_mock` ahead of
    `enable_custom_integrations` restores the required order.
    """


_CONTRACT = "9999999999"


def _make_coordinator(hass: HomeAssistant) -> GaggleCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REFRESH_TOKEN: "v1.testtoken",
            CONF_CONTRACT_NUMBER: _CONTRACT,
            CONF_ACCOUNT_NUMBER: "1234567890",
        },
        unique_id="1234567890_9999999999",
    )
    entry.add_to_hass(hass)
    return GaggleCoordinator(hass, entry, AsyncMock(), _CONTRACT)


def _period(start: date, end: date, usage_mj: float, cost_aud: float) -> GasPastPeriod:
    return GasPastPeriod(start=start, end=end, usage_mj=usage_mj, cost_aud=cost_aud)


async def _read_series(hass: HomeAssistant, stat_id: str) -> list[dict]:
    """Read every stored row for stat_id from the REAL recorder."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import statistics_during_period

    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(2020, 1, 1, tzinfo=UTC),
        None,
        {stat_id},
        "hour",
        None,
        {"start", "state", "sum"},
    )
    return list(result.get(stat_id) or [])


async def test_aged_out_period_baseline_continuity(
    recorder_mock, hass: HomeAssistant
) -> None:
    """The period-level analog of the sibling electricity integration's
    v0.3.0 phantom-spike class.

    AGL's usage.basic.Gas response is a bounded WINDOW of past periods, not
    full account history. Import P1+P2, then simulate a later poll whose
    window has aged P1 out (only P2+P3 returned). The baseline lookup must
    still find P1's stored sum, so P2's sum is unchanged and P3 stacks
    correctly on top — never a downward step in the recorder's
    TOTAL_INCREASING sum.
    """
    coord = _make_coordinator(hass)
    stat_id = f"{DOMAIN}:{STAT_CONSUMPTION}_{_CONTRACT}"

    p1 = _period(date(2026, 2, 11), date(2026, 4, 15), 100.0, 10.0)
    p2 = _period(date(2026, 4, 16), date(2026, 6, 11), 150.0, 15.0)
    p3 = _period(date(2026, 6, 12), date(2026, 8, 14), 200.0, 20.0)

    # First poll: AGL's window returns P1 + P2.
    await coord._import_periods([p1, p2])
    await async_wait_recording_done(hass)

    rows = await _read_series(hass, stat_id)
    assert len(rows) == 2
    assert abs(rows[0]["sum"] - 100.0) < 1e-9
    assert abs(rows[1]["sum"] - 250.0) < 1e-9

    # Later poll: P1 has aged out of AGL's returned window; only P2 + P3
    # come back now (P2 unchanged, P3 newly completed).
    await coord._import_periods([p2, p3])
    await async_wait_recording_done(hass)

    rows = await _read_series(hass, stat_id)
    assert len(rows) == 3
    sums = [row["sum"] for row in rows]
    # Must stay [100, 250, 450] -- P2's sum must NOT reset to 150 (which is
    # what a baseline of 0.0 for the second import would produce).
    assert abs(sums[0] - 100.0) < 1e-9
    assert abs(sums[1] - 250.0) < 1e-9
    assert abs(sums[2] - 450.0) < 1e-9
    assert all(b >= a for a, b in pairwise(sums))


async def test_idempotent_reimport_does_not_duplicate_rows(
    recorder_mock, hass: HomeAssistant
) -> None:
    """async_add_external_statistics updates in place on (statistic_id,
    start) — re-importing the exact same batch must not create duplicate
    rows or double the cumulative sum."""
    coord = _make_coordinator(hass)
    stat_id = f"{DOMAIN}:{STAT_CONSUMPTION}_{_CONTRACT}"

    periods = [_period(date(2026, 2, 11), date(2026, 4, 15), 100.0, 10.0)]
    await coord._import_periods(periods)
    await async_wait_recording_done(hass)
    await coord._import_periods(periods)
    await async_wait_recording_done(hass)

    rows = await _read_series(hass, stat_id)
    assert len(rows) == 1
    assert abs(rows[-1]["sum"] - 100.0) < 1e-9


async def test_consumption_and_cost_series_both_written(
    recorder_mock, hass: HomeAssistant
) -> None:
    """Both series (consumption + cost) land in the recorder from one
    import, and each keeps its own independent cumulative sum."""
    from custom_components.gaggle.const import STAT_COST

    coord = _make_coordinator(hass)
    cons_id = f"{DOMAIN}:{STAT_CONSUMPTION}_{_CONTRACT}"
    cost_id = f"{DOMAIN}:{STAT_COST}_{_CONTRACT}"

    periods = [
        _period(date(2026, 2, 11), date(2026, 4, 15), 100.0, 10.0),
        _period(date(2026, 4, 16), date(2026, 6, 11), 150.0, 15.0),
    ]
    await coord._import_periods(periods)
    await async_wait_recording_done(hass)

    cons_rows = await _read_series(hass, cons_id)
    cost_rows = await _read_series(hass, cost_id)
    assert len(cons_rows) == 2
    assert len(cost_rows) == 2
    assert abs(cons_rows[-1]["sum"] - 250.0) < 1e-9
    assert abs(cost_rows[-1]["sum"] - 25.0) < 1e-9
