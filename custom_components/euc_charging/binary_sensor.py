"""Binary sensor platform for Leaperkim EUC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, sanitize_wheel_id
from .coordinator import EucChargingCoordinator


@dataclass
class EucChargingBinarySensorDescription(BinarySensorEntityDescription):
    """Class describing Leaperkim binary sensor entities."""
    value_fn: Callable[[dict[str, Any]], bool | None] = lambda x: None


BINARY_SENSORS: tuple[EucChargingBinarySensorDescription, ...] = (
    EucChargingBinarySensorDescription(
        key="is_charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.get("is_charging", False),  # Default to False if not present
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leaperkim binary sensors."""
    coordinator: EucChargingCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        EucChargingBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class EucChargingBinarySensor(CoordinatorEntity[EucChargingCoordinator], BinarySensorEntity):
    """Representation of a Leaperkim Binary Sensor."""

    entity_description: EucChargingBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EucChargingCoordinator,
        description: EucChargingBinarySensorDescription,
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
        # Charging sensor should always be available (shows Off when disconnected)
        # This ensures it shows as "off" rather than "unknown" when disconnected
        return True

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not self.coordinator.data:
            # When disconnected, show as Off instead of Unknown
            return False
        # For is_charging, default to False if not explicitly set
        # This ensures we show Off instead of Unknown when connected but not charging
        result = self.entity_description.value_fn(self.coordinator.data)
        if self.entity_description.key == "is_charging" and result is None:
            return False
        return result
