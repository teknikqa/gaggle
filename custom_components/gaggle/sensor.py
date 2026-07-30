"""Sensor entities for gaggle.

Cumulative consumption / cost use import_statistics() to feed historical
data into the HA Energy dashboard (data is always for past intervals; a
live state sensor would attribute everything to "now"). Entities backed
by live coordinator data use the standard CoordinatorEntity pattern.

Six sensors total:
  - consumption_period / consumption_period_cost — current billing-period
    usage / cost (device-card values; None/`unknown` until the gas
    usage-summary endpoint is implemented — see docs/gas-api.md)
  - consumption / consumption_cost — cumulative total usage / cost
    (device-card values, seeded from the gaggle:* statistics)
  - unit_rate — usage rate (AUD per unit; None until the gas plan
    rate-shape TODO in coordinator.py is resolved)
  - supply_charge — supply charge (AUD/day; from the real, fuel-agnostic
    plan endpoint)

state_class choices:
  - TOTAL_INCREASING would be wrong here: these entities update once per
    24 h poll, not continuously, so none of them are Energy-dashboard
    sources — the gaggle:* statistics fed via import_statistics() are.
  - TOTAL for the period cost (a cumulative AUD total for a known period)
  - unset on rate sensors (MEASUREMENT, no device_class) and on the raw
    kWh/MJ totals (see the "no Energy source" note below)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CONSUMPTION_COST,
    DATA_CONSUMPTION_KWH,
    DATA_CONSUMPTION_PERIOD,
    DATA_CONSUMPTION_PERIOD_COST,
    DATA_SUPPLY_CHARGE,
    DATA_UNIT_RATE,
    DOMAIN,
    GAS_USAGE_UNIT,
)
from .coordinator import GaggleCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import GaggleConfigEntry

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    # --- Cumulative total usage (device-card value, NOT an Energy source) ---
    # The all-time cumulative total is fed to the Energy dashboard via
    # import_statistics() (gaggle:consumption_<contract>), which places every
    # unit in its true hour. This entity is only the latest known value for
    # the device card. It carries NO device_class/state_class ON PURPOSE so
    # it cannot be picked as an Energy-dashboard source: its state moves once
    # per 24 h poll, so HA would attribute a whole day's usage to the poll
    # hour on the wrong day. De-listing also stops it emitting long-term
    # statistics of its own.
    SensorEntityDescription(
        key=DATA_CONSUMPTION_KWH,
        translation_key="consumption",
        native_unit_of_measurement=GAS_USAGE_UNIT,
        suggested_display_precision=3,
    ),
    # --- Cumulative total cost (device-card value) ---
    # A running monetary total, so MONETARY + TOTAL is the valid pairing
    # (state_class=MEASUREMENT is invalid with device_class=MONETARY).
    SensorEntityDescription(
        key=DATA_CONSUMPTION_COST,
        translation_key="consumption_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="AUD",
        suggested_display_precision=2,
    ),
    # --- Sub-period usage total (device-card value, NOT an Energy source) ---
    # "This period" total, reset at the billing boundary. Like the cumulative
    # total above, it carries NO device_class/state_class: it also advances
    # only once per daily poll, so as an Energy source it would mis-place a
    # whole day's usage on the poll hour. The Energy-dashboard source is
    # always the gaggle:… statistics.
    SensorEntityDescription(
        key=DATA_CONSUMPTION_PERIOD,
        translation_key="consumption_period",
        native_unit_of_measurement=GAS_USAGE_UNIT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=DATA_CONSUMPTION_PERIOD_COST,
        translation_key="consumption_period_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="AUD",
        suggested_display_precision=2,
    ),
    # --- Rates (instantaneous prices) ---
    # NOT MONETARY — that device_class is for cumulative amounts ($87.38 of
    # cost so far this period), not unit prices. Keep state_class=MEASUREMENT
    # so HA's recorder tracks min/mean/max in long-term statistics. Removing
    # `device_class` loses the $-chip in the entity card UI; the unit string
    # still makes the meaning clear.
    SensorEntityDescription(
        key=DATA_UNIT_RATE,
        translation_key="unit_rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=f"AUD/{GAS_USAGE_UNIT}",
    ),
    SensorEntityDescription(
        key=DATA_SUPPLY_CHARGE,
        translation_key="supply_charge",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="AUD/day",
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: GaggleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up gaggle sensor entities for the entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        GaggleEnergySensor(coordinator, entry, desc) for desc in SENSOR_DESCRIPTIONS
    )


class GaggleEnergySensor(CoordinatorEntity[GaggleCoordinator], SensorEntity):
    """A sensor backed by the gaggle coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GaggleCoordinator,
        entry: GaggleConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        # `manufacturer` and `model` here drive HA's "Service info" card.
        # This is an unofficial third-party integration — AGL Energy did not
        # write, sanction, or endorse it. Don't put "AGL" in `manufacturer`
        # even with a qualifier; the surface is too easily mistaken for an
        # official AGL product.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Gaggle",
            model="AGL smart gas meter (unofficial integration)",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | None:
        """Return the current sensor value from coordinator data."""
        value = getattr(self.coordinator.data, self.entity_description.key)
        return float(value) if value is not None else None
