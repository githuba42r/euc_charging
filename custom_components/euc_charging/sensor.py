"""Sensor platform for Leaperkim EUC."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfSpeed,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime

from .const import DOMAIN, sanitize_wheel_id
from .coordinator import EucChargingCoordinator
from .charge_tracker import ChargeEstimates

_LOGGER = logging.getLogger(__name__)


@dataclass
class EucChargingSensorDescription(SensorEntityDescription):
    """Class describing Leaperkim sensor entities."""
    value_fn: Callable[[dict[str, Any]], Any] = lambda x: None


SENSORS: tuple[EucChargingSensorDescription, ...] = (
    EucChargingSensorDescription(
        key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("voltage"),
    ),
    EucChargingSensorDescription(
        key="battery_percent",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("battery_percent"),
    ),
    EucChargingSensorDescription(
        key="total_distance",
        name="Total Distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("total_distance"),
    ),
    EucChargingSensorDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("temperature"),
    ),
    # Charge time estimate sensors
    EucChargingSensorDescription(
        key="charge_time_to_80",
        name="Time to 80%",
        icon="mdi:battery-charging-80",
        value_fn=lambda data: (
            data.get("charge_estimates").time_to_80_formatted 
            if data.get("charge_estimates") and data.get("is_charging") 
            else "0:00 hr"  # Show 0:00 when not charging
        ),
    ),
    EucChargingSensorDescription(
        key="charge_time_to_90",
        name="Time to 90%",
        icon="mdi:battery-charging-90",
        value_fn=lambda data: (
            data.get("charge_estimates").time_to_90_formatted 
            if data.get("charge_estimates") and data.get("is_charging") 
            else "0:00 hr"  # Show 0:00 when not charging
        ),
    ),
    EucChargingSensorDescription(
        key="charge_time_to_95",
        name="Time to 95%",
        icon="mdi:battery-charging-high",
        value_fn=lambda data: (
            data.get("charge_estimates").time_to_95_formatted 
            if data.get("charge_estimates") and data.get("is_charging") 
            else "0:00 hr"  # Show 0:00 when not charging
        ),
    ),
    EucChargingSensorDescription(
        key="charge_time_to_100",
        name="Time to 100%",
        icon="mdi:battery-charging-100",
        value_fn=lambda data: (
            data.get("charge_estimates").time_to_100_formatted 
            if data.get("charge_estimates") and data.get("is_charging") 
            else "0:00 hr"  # Show 0:00 when not charging
        ),
    ),
    EucChargingSensorDescription(
        key="charge_rate",
        name="Charge Rate",
        native_unit_of_measurement=f"{PERCENTAGE}/min",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:speedometer",
        value_fn=lambda data: (
            data.get("charge_estimates").charge_rate_pct 
            if data.get("charge_estimates") and data.get("is_charging") 
            and data.get("charge_estimates").charge_rate_pct is not None 
            else 0  # Show 0 when not charging instead of None/Unknown
        ),
    ),
    # Last connected/updated sensors (persist even when disconnected)
    EucChargingSensorDescription(
        key="last_connected_time",
        name="Last Connected",
        icon="mdi:clock-outline",
        value_fn=lambda data: data.get("last_connected_time"),
    ),
    EucChargingSensorDescription(
        key="last_voltage",
        name="Last Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        icon="mdi:battery-clock",
        entity_registry_enabled_default=False,
        value_fn=lambda data: None,  # We'll override this in the sensor class
    ),
    EucChargingSensorDescription(
        key="last_battery_percent",
        name="Last Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:battery-clock",
        entity_registry_enabled_default=False,
        value_fn=lambda data: None,  # We'll override this in the sensor class
    ),
    EucChargingSensorDescription(
        key="last_trip_distance",
        name="Last Trip Distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        icon="mdi:map-marker-distance",
        entity_registry_enabled_default=False,
        value_fn=lambda data: None,  # We'll override this in the sensor class
    ),
    EucChargingSensorDescription(
        key="last_total_distance",
        name="Last Total Distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        icon="mdi:counter",
        entity_registry_enabled_default=False,
        value_fn=lambda data: None,  # We'll override this in the sensor class
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leaperkim sensors."""
    coordinator: EucChargingCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        EucChargingSensor(coordinator, description) for description in SENSORS
    )


class EucChargingSensor(CoordinatorEntity[EucChargingCoordinator], SensorEntity):
    """Representation of a Leaperkim Sensor."""

    entity_description: EucChargingSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EucChargingCoordinator,
        description: EucChargingSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        
        # Generate unique_id using MAC address for persistence
        self._attr_unique_id = f"{coordinator.ble_device.address}_{description.key}"
        
        # Set suggested_object_id to include wheel identifier for better entity IDs
        wheel_id = sanitize_wheel_id(coordinator.ble_device.name or "euc")
        self._attr_suggested_object_id = f"euc_{wheel_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        data = self.coordinator.data or {}
        model = data.get("model", "Unknown Model")
        manufacturer = data.get("manufacturer", "Leaperkim")
        sw_version = data.get("version")

        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.ble_device.address)},
            name=f"{manufacturer} {model} ({self.coordinator.ble_device.name})",
            manufacturer=manufacturer,
            model=model,
            sw_version=sw_version,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # "Last known" sensors should always be available once enabled
        # They will show None until the wheel connects for the first time
        if self.entity_description.key in (
            "last_voltage",
            "last_battery_percent",
            "last_trip_distance",
            "last_total_distance",
            "last_connected_time",
        ):
            # Always available - will show as having no value until wheel connects
            return True
        
        # All other sensors require active connection (data must exist)
        return self.coordinator.data is not None

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Handle "last known" sensors specially - they read from coordinator's stored values
        if self.entity_description.key == "last_voltage":
            value = self.coordinator.last_voltage
            _LOGGER.debug("last_voltage sensor value: %s", value)
            return value
        elif self.entity_description.key == "last_battery_percent":
            value = self.coordinator.last_battery_percent
            _LOGGER.debug("last_battery_percent sensor value: %s", value)
            return value
        elif self.entity_description.key == "last_trip_distance":
            return self.coordinator.last_trip_distance
        elif self.entity_description.key == "last_total_distance":
            return self.coordinator.last_total_distance
        elif self.entity_description.key == "last_connected_time":
            value = self.coordinator.last_connected_time
            _LOGGER.debug("last_connected_time sensor value: %s", value)
            # Format as readable date/time string (e.g., "2026-03-04 12:29:26")
            if value:
                return value.strftime("%Y-%m-%d %H:%M:%S")
            return None
        
        # All other sensors use the normal value_fn
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return None
            
        # Add system voltage to the voltage sensor
        if self.entity_description.key == "voltage":
            return {
                "system_voltage": self.coordinator.data.get("system_voltage"),
            }
            
        # Add charge estimates to the battery sensor
        if self.entity_description.key == "battery_percent":
            estimates: ChargeEstimates | None = self.coordinator.data.get("charge_estimates")
            if estimates and estimates.charge_rate_pct > 0:
                attrs = {
                    "charge_rate_pct_min": estimates.charge_rate_pct,
                    "averaging_window": estimates.averaging_window,
                }
                if estimates.time_to_80 is not None:
                    attrs["time_to_80"] = estimates.time_to_80_formatted
                if estimates.time_to_90 is not None:
                    attrs["time_to_90"] = estimates.time_to_90_formatted
                if estimates.time_to_95 is not None:
                    attrs["time_to_95"] = estimates.time_to_95_formatted
                if estimates.time_to_100 is not None:
                    attrs["time_to_100"] = estimates.time_to_100_formatted
                return attrs
            
        return None
