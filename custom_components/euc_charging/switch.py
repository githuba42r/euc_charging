"""Switch platform for EUC Charging integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, sanitize_wheel_id
from .coordinator import EucChargingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EUC switches."""
    coordinator: EucChargingCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([EucAutoConnectSwitch(coordinator, entry)])


class EucAutoConnectSwitch(SwitchEntity):
    """Switch to control automatic connection to EUC."""

    _attr_has_entity_name = True
    _attr_name = "Auto Connect"

    def __init__(self, coordinator: EucChargingCoordinator, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._coordinator = coordinator
        self._entry = entry
        
        # Generate unique_id using entry_id for persistence
        self._attr_unique_id = f"{entry.entry_id}_auto_connect"
        
        # Set suggested_object_id to include wheel identifier for better entity IDs
        wheel_id = sanitize_wheel_id(coordinator.ble_device.name or "euc")
        self._attr_suggested_object_id = f"euc_{wheel_id}_auto_connect"
        
        self._attr_is_on = True  # Default to enabled
        
        # Initialize the coordinator's auto-connect state
        self._coordinator.auto_connect_enabled = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.ble_device.address)},
            name=self._coordinator.ble_device.name or "EUC",
            manufacturer="Leaperkim",
            connections={("bluetooth", self._coordinator.ble_device.address)},
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True  # Switch is always available

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._attr_is_on

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self._attr_is_on:
            return "mdi:bluetooth-connect"
        return "mdi:bluetooth-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.info("Enabling auto-connect for %s", self._coordinator.ble_device.address)
        self._attr_is_on = True
        self._coordinator.auto_connect_enabled = True
        self.async_write_ha_state()
        
        # Trigger a reconnection attempt if device is available
        self._coordinator.trigger_reconnect()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.info("Disabling auto-connect for %s", self._coordinator.ble_device.address)
        self._attr_is_on = False
        self._coordinator.auto_connect_enabled = False
        self.async_write_ha_state()
        
        # Disconnect if currently connected
        if self._coordinator.client and self._coordinator.client.is_connected:
            _LOGGER.info("Disconnecting from %s due to auto-connect disabled", self._coordinator.ble_device.address)
            await self._coordinator.disconnect()
