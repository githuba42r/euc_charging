"""Entities for Motoeye VD TPMS sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    STATE_ON,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_MIN_PRESSURE_PSI,
    CONF_WHEEL_ADDRESS,
    DEFAULT_MIN_PRESSURE_PSI,
    DOMAIN,
)
from .tpms import is_low_battery, is_low_pressure
from .tpms_coordinator import TpmsCoordinator


@dataclass(frozen=True, kw_only=True)
class TpmsSensorDescription(SensorEntityDescription):
    """Describes a TPMS sensor; value_fn reads from the coordinator."""

    value_fn: Callable[[TpmsCoordinator], Any]


TPMS_SENSORS: tuple[TpmsSensorDescription, ...] = (
    TpmsSensorDescription(
        key="pressure",
        name="Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.KPA,
        suggested_unit_of_measurement=UnitOfPressure.PSI,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.reading.pressure_kpa if c.reading else None,
    ),
    TpmsSensorDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.reading.temperature if c.reading else None,
    ),
    TpmsSensorDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.reading.battery_percent if c.reading else None,
    ),
    TpmsSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.reading.battery_voltage if c.reading else None,
    ),
    TpmsSensorDescription(
        key="rssi",
        name="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.reading.rssi if c.reading else None,
    ),
    TpmsSensorDescription(
        key="last_seen",
        name="Last Seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.last_seen,
    ),
)


def _resolve_via_device_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Resolve the wheel device's registry id for via_device_id, if any.

    Resolved once per entry (not per entity) by the setup helpers and passed
    into each entity's constructor.
    """
    wheel_address = entry.data.get(CONF_WHEEL_ADDRESS)
    if not wheel_address:
        return None
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, wheel_address)})
    return device.id if device else None


class TpmsEntity(Entity):
    """Common device/unique-id/listener handling for TPMS entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TpmsCoordinator,
        entry: ConfigEntry,
        key: str,
        via_device_id: str | None = None,
    ) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{coordinator.address}_{key}"
        device_info: DeviceInfo = {
            "identifiers": {(DOMAIN, coordinator.address)},
            "name": entry.title,
            "manufacturer": "Motoeye",
            "model": "VD TPMS",
        }
        if via_device_id:
            device_info["via_device_id"] = via_device_id
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self._update_from_coordinator()
        self.async_write_ha_state()

    def _update_from_coordinator(self) -> None:
        raise NotImplementedError


class TpmsSensor(TpmsEntity, RestoreSensor):
    """A TPMS reading that keeps its last value while the sensor sleeps."""

    entity_description: TpmsSensorDescription

    def __init__(self, coordinator: TpmsCoordinator, entry: ConfigEntry,
                 description: TpmsSensorDescription,
                 via_device_id: str | None = None) -> None:
        super().__init__(coordinator, entry, description.key, via_device_id)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.reading is not None:
            self._update_from_coordinator()
        elif (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value

    def _update_from_coordinator(self) -> None:
        self._attr_native_value = self.entity_description.value_fn(self.coordinator)


class TpmsAlarm(TpmsEntity, BinarySensorEntity, RestoreEntity):
    """A TPMS alarm that keeps its last state while the sensor sleeps."""

    def __init__(self, coordinator: TpmsCoordinator, entry: ConfigEntry,
                 description: BinarySensorEntityDescription,
                 predicate: Callable[[TpmsCoordinator], bool],
                 via_device_id: str | None = None) -> None:
        super().__init__(coordinator, entry, description.key, via_device_id)
        self.entity_description = description
        self._predicate = predicate

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.reading is not None:
            self._update_from_coordinator()
        elif (last := await self.async_get_last_state()) is not None and last.state in ("on", "off"):
            self._attr_is_on = last.state == STATE_ON

    def _update_from_coordinator(self) -> None:
        self._attr_is_on = self._predicate(self.coordinator)


def build_tpms_alarms(
    coordinator: TpmsCoordinator, entry: ConfigEntry, via_device_id: str | None = None
) -> list[TpmsAlarm]:
    """Build the Low Pressure / Low Battery alarm entities for a TPMS entry."""
    min_psi = entry.options.get(CONF_MIN_PRESSURE_PSI, DEFAULT_MIN_PRESSURE_PSI)
    return [
        TpmsAlarm(
            coordinator, entry,
            BinarySensorEntityDescription(
                key="low_pressure", name="Low Pressure",
                device_class=BinarySensorDeviceClass.PROBLEM,
            ),
            lambda c: is_low_pressure(c.reading, min_psi),
            via_device_id,
        ),
        TpmsAlarm(
            coordinator, entry,
            BinarySensorEntityDescription(
                key="low_battery", name="Low Battery",
                device_class=BinarySensorDeviceClass.BATTERY,
            ),
            lambda c: is_low_battery(c.reading),
            via_device_id,
        ),
    ]


async def async_setup_tpms_sensors(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add TPMS sensors for a TPMS config entry."""
    coordinator: TpmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    via_device_id = _resolve_via_device_id(hass, entry)
    async_add_entities(TpmsSensor(coordinator, entry, d, via_device_id) for d in TPMS_SENSORS)


async def async_setup_tpms_binary_sensors(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Low Pressure / Low Battery alarms for a TPMS config entry."""
    coordinator: TpmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    via_device_id = _resolve_via_device_id(hass, entry)
    async_add_entities(build_tpms_alarms(coordinator, entry, via_device_id))
