"""The Leaperkim EUC integration."""

from __future__ import annotations

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import EucChargingCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Leaperkim EUC from a config entry."""
    address = entry.data[CONF_ADDRESS]
    # Don't require connectable=True as ESPHome proxies may not report this correctly
    ble_device = async_ble_device_from_address(hass, address, connectable=False)

    # If device is not currently advertising, create a placeholder BLE device
    # The coordinator will wait for it to become available
    if not ble_device:
        from bleak.backends.device import BLEDevice
        # Create a minimal BLE device object with just the address
        # The coordinator will update this when the device is discovered
        ble_device = BLEDevice(address=address, name="EUC (waiting...)", details=None, rssi=-127)

    coordinator = EucChargingCoordinator(hass, entry, ble_device)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: EucChargingCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
