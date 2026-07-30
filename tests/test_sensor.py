"""Tests for custom_components/gaggle/sensor.py.

gaggle registers a fixed set of seven sensors (no conditional registration —
unlike the sibling electricity integration's ToU/solar sensors, there's no
per-contract feature to gate on): current billing-period usage/cost, bill
projection, cumulative total usage/cost, usage rate, supply charge.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gaggle.const import (
    CONF_ACCOUNT_NUMBER,
    CONF_CONTRACT_NUMBER,
    CONF_REFRESH_TOKEN,
    DATA_CONSUMPTION_COST,
    DATA_CONSUMPTION_KWH,
    DATA_CONSUMPTION_PERIOD,
    DATA_CONSUMPTION_PERIOD_COST,
    DATA_PROJECTION_COST,
    DATA_SUPPLY_CHARGE,
    DATA_UNIT_RATE,
    DOMAIN,
)
from custom_components.gaggle.coordinator import GaggleCoordinator, GaggleData
from custom_components.gaggle.sensor import (
    SENSOR_DESCRIPTIONS,
    GaggleEnergySensor,
    async_setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_CONTRACT = "9999999999"
_ALL_KEYS = {
    DATA_CONSUMPTION_KWH,
    DATA_CONSUMPTION_COST,
    DATA_CONSUMPTION_PERIOD,
    DATA_CONSUMPTION_PERIOD_COST,
    DATA_PROJECTION_COST,
    DATA_UNIT_RATE,
    DATA_SUPPLY_CHARGE,
}


def _data(
    *,
    period_usage: float | None = 0.0,
    period_cost: float | None = 0.0,
    projection_cost: float | None = 0.0,
    unit_rate: float | None = 0.3,
    supply_charge: float | None = 1.0,
    cumulative_usage: float = 0.0,
    cumulative_cost: float = 0.0,
) -> GaggleData:
    return GaggleData(
        consumption_period_usage=period_usage,
        consumption_period_cost_aud=period_cost,
        projection_cost_aud=projection_cost,
        unit_rate_aud_per_unit=unit_rate,
        supply_charge_aud_per_day=supply_charge,
        latest_cumulative_usage=cumulative_usage,
        latest_cumulative_cost_aud=cumulative_cost,
    )


def _make_entry_with_coordinator(
    hass: HomeAssistant, data: GaggleData | None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REFRESH_TOKEN: "v1.tok",
            CONF_CONTRACT_NUMBER: _CONTRACT,
            CONF_ACCOUNT_NUMBER: "1234567890",
        },
        unique_id="1234567890_9999999999",
    )
    entry.add_to_hass(hass)
    coordinator = GaggleCoordinator(hass, entry, AsyncMock(), _CONTRACT)
    coordinator.data = data  # type: ignore[assignment]
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    return entry


async def _setup_keys(hass: HomeAssistant, data: GaggleData | None) -> list[str]:
    """Run async_setup_entry and return the keys of the entities it registered."""
    entry = _make_entry_with_coordinator(hass, data)
    captured: list[GaggleEnergySensor] = []

    def _add(entities) -> None:
        captured.extend(entities)

    await async_setup_entry(hass, entry, _add)  # type: ignore[arg-type]
    return [e.entity_description.key for e in captured]


class TestSensorRegistration:
    async def test_all_seven_sensors_registered(self, hass: HomeAssistant) -> None:
        keys = await _setup_keys(hass, _data())
        assert set(keys) == _ALL_KEYS
        assert len(keys) == len(SENSOR_DESCRIPTIONS) == 7

    async def test_registration_does_not_depend_on_coordinator_data(
        self, hass: HomeAssistant
    ) -> None:
        """Unlike the sibling ToU/solar integration, nothing here is
        conditional — the sensor set is fixed even with no coordinator data
        yet (e.g. the very first refresh)."""
        keys = await _setup_keys(hass, None)
        assert set(keys) == _ALL_KEYS


class TestNativeValue:
    async def test_period_usage_and_cost_read_none_as_unavailable(
        self, hass: HomeAssistant
    ) -> None:
        """Defensive: if coordinator data ever has None here (e.g. a
        malformed response degraded to defaults with no usable current
        period), the sensor reads unavailable rather than raising."""
        entry = _make_entry_with_coordinator(
            hass, _data(period_usage=None, period_cost=None)
        )
        coordinator = entry.runtime_data.coordinator
        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        period_sensor = GaggleEnergySensor(
            coordinator, entry, by_key[DATA_CONSUMPTION_PERIOD]
        )
        period_cost_sensor = GaggleEnergySensor(
            coordinator, entry, by_key[DATA_CONSUMPTION_PERIOD_COST]
        )
        assert period_sensor.native_value is None
        assert period_cost_sensor.native_value is None

    async def test_projection_reads_real_value(self, hass: HomeAssistant) -> None:
        entry = _make_entry_with_coordinator(hass, _data(projection_cost=211.60))
        coordinator = entry.runtime_data.coordinator
        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        sensor = GaggleEnergySensor(coordinator, entry, by_key[DATA_PROJECTION_COST])
        assert sensor.native_value == pytest.approx(211.60)

    async def test_unit_rate_none_when_plan_has_no_mj_rows(
        self, hass: HomeAssistant
    ) -> None:
        """The tiered-plan rate picker (coordinator.py) returns None when
        the plan has no c/MJ detail row — never a guessed value."""
        entry = _make_entry_with_coordinator(hass, _data(unit_rate=None))
        coordinator = entry.runtime_data.coordinator
        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        sensor = GaggleEnergySensor(coordinator, entry, by_key[DATA_UNIT_RATE])
        assert sensor.native_value is None

    async def test_supply_charge_reads_real_plan_value(
        self, hass: HomeAssistant
    ) -> None:
        """Supply charge comes from the real, fuel-agnostic plan endpoint —
        it should populate normally even while usage endpoints are stubs."""
        entry = _make_entry_with_coordinator(hass, _data(supply_charge=1.31714))
        coordinator = entry.runtime_data.coordinator
        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        sensor = GaggleEnergySensor(coordinator, entry, by_key[DATA_SUPPLY_CHARGE])
        assert sensor.native_value == 1.31714

    async def test_cumulative_sensors_read_seeded_recorder_sums(
        self, hass: HomeAssistant
    ) -> None:
        entry = _make_entry_with_coordinator(
            hass, _data(cumulative_usage=42.5, cumulative_cost=17.25)
        )
        coordinator = entry.runtime_data.coordinator
        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        usage_sensor = GaggleEnergySensor(
            coordinator, entry, by_key[DATA_CONSUMPTION_KWH]
        )
        cost_sensor = GaggleEnergySensor(
            coordinator, entry, by_key[DATA_CONSUMPTION_COST]
        )
        assert usage_sensor.native_value == 42.5
        assert cost_sensor.native_value == 17.25


class TestSensorDescriptions:
    def test_kwh_totals_are_not_energy_dashboard_sources(self) -> None:
        """Both usage-total sensors (cumulative and period) must carry no
        device_class/state_class — they update once per poll, so as an
        Energy source they'd mis-place a whole day's usage on the poll
        hour. The real sources are the gaggle:* statistics fed via
        import_statistics()."""
        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        for key in (DATA_CONSUMPTION_KWH, DATA_CONSUMPTION_PERIOD):
            desc = by_key[key]
            assert desc.device_class is None, key
            assert desc.state_class is None, key

    def test_monetary_totals_are_total_not_measurement(self) -> None:
        """Cumulative and period cost are running AUD totals: MONETARY +
        TOTAL is the only valid pairing (MEASUREMENT is invalid with
        MONETARY)."""
        from homeassistant.components.sensor import (
            SensorDeviceClass,
            SensorStateClass,
        )

        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        for key in (
            DATA_CONSUMPTION_COST,
            DATA_CONSUMPTION_PERIOD_COST,
            DATA_PROJECTION_COST,
        ):
            desc = by_key[key]
            assert desc.device_class is SensorDeviceClass.MONETARY, key
            assert desc.state_class is SensorStateClass.TOTAL, key

    def test_rate_sensors_are_not_monetary(self) -> None:
        """Unit prices (rate, supply charge): MEASUREMENT, no device_class —
        MONETARY is for cumulative amounts, not unit prices."""
        from homeassistant.components.sensor import SensorStateClass

        by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
        for key in (DATA_UNIT_RATE, DATA_SUPPLY_CHARGE):
            desc = by_key[key]
            assert desc.device_class is None, key
            assert desc.state_class is SensorStateClass.MEASUREMENT, key


def test_device_info_manufacturer_is_gaggle(hass: HomeAssistant) -> None:
    entry = _make_entry_with_coordinator(hass, _data())
    coordinator = entry.runtime_data.coordinator
    sensor = GaggleEnergySensor(coordinator, entry, SENSOR_DESCRIPTIONS[0])
    info = sensor._attr_device_info
    assert info is not None
    assert info.get("manufacturer") == "Gaggle"
    assert "unofficial" in (info.get("model") or "").lower()
