"""Config flow for Leaperkim EUC integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    ALL_SERVICE_UUIDS,
    CONF_ENTRY_TYPE,
    CONF_MIN_PRESSURE_PSI,
    CONF_WHEEL_ADDRESS,
    DEFAULT_MIN_PRESSURE_PSI,
    DEVICE_NAMES,
    DOMAIN,
    ENTRY_TYPE_TPMS,
    SERVICE_UUID,
    is_tpms_entry,
    match_brand_by_name,
)
from .tpms import is_tpms_advertisement

_LOGGER = logging.getLogger(__name__)

NO_WHEEL = "none"
MIN_PRESSURE_SCHEMA = vol.All(vol.Coerce(float), vol.Range(min=1, max=150))


def build_tpms_entry(address: str, user_input: dict[str, Any]) -> tuple[dict, dict]:
    """Return (data, options) for a TPMS config entry from the confirm form."""
    data: dict[str, Any] = {CONF_ADDRESS: address, CONF_ENTRY_TYPE: ENTRY_TYPE_TPMS}
    wheel = user_input.get(CONF_WHEEL_ADDRESS)
    if wheel and wheel != NO_WHEEL:
        data[CONF_WHEEL_ADDRESS] = wheel
    options = {CONF_MIN_PRESSURE_PSI: float(user_input[CONF_MIN_PRESSURE_PSI])}
    return data, options


class EucChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Leaperkim EUC."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._show_all_devices = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=discovery_info.name,
                data={CONF_ADDRESS: discovery_info.address},
            )

        self._discovered_devices = {}
        current_addresses = self._async_current_ids()

        _LOGGER.debug("Starting device discovery, scanning all Bluetooth devices...")
        all_devices_count = 0
        matching_by_service = 0
        matching_by_name = 0
        
        for discovery_info in async_discovered_service_info(self.hass):
            all_devices_count += 1
            address = discovery_info.address
            
            _LOGGER.debug(
                "Found BT device: %s (%s), Services: %s, Manufacturer: %s, RSSI: %s",
                discovery_info.name or "Unknown",
                address,
                discovery_info.service_uuids,
                discovery_info.manufacturer_data,
                discovery_info.rssi,
            )
            
            if address in current_addresses:
                _LOGGER.debug("Skipping %s - already configured", address)
                continue
            
            if address in self._discovered_devices:
                continue

            # If showing all devices, include everything
            if self._show_all_devices:
                self._discovered_devices[address] = discovery_info
                continue

            # Match by service UUID (most reliable) - check all supported UUIDs
            matched_by_uuid = False
            for service_uuid in ALL_SERVICE_UUIDS:
                if service_uuid in discovery_info.service_uuids:
                    _LOGGER.info("Found EUC device by service UUID %s: %s (%s)", service_uuid, discovery_info.name, address)
                    self._discovered_devices[address] = discovery_info
                    matching_by_service += 1
                    matched_by_uuid = True
                    break
            
            if matched_by_uuid:
                continue
            
            # Fallback: Match by device name (for ESPHome proxies that may not forward service UUIDs)
            if match_brand_by_name(discovery_info.name):
                _LOGGER.info("Found EUC device by name match: %s (%s)", discovery_info.name, address)
                self._discovered_devices[address] = discovery_info
                matching_by_name += 1
                continue

        _LOGGER.info(
            "Discovery complete: scanned %d devices, found %d by service UUID, %d by name, total %d matches",
            all_devices_count,
            matching_by_service,
            matching_by_name,
            len(self._discovered_devices)
        )

        if not self._discovered_devices:
            _LOGGER.warning(
                "No EUC devices found. Looking for service UUIDs %s or names matching %s. "
                "Scanned %d total devices. Is the device already connected to another app?",
                ALL_SERVICE_UUIDS,
                DEVICE_NAMES,
                all_devices_count
            )
            return await self.async_step_no_devices()
        
        # Reset the show_all flag
        self._show_all_devices = False

        titles = {
            address: f"{info.name} ({address})"
            for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(titles)}
            ),
        )

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the step where no devices are found."""
        if user_input is not None:
            if user_input.get("manual_entry"):
                return await self.async_step_manual()
            if user_input.get("show_all"):
                self._show_all_devices = True
                return await self.async_step_user()
            # User clicked "Rescan"
            return await self.async_step_user()

        return self.async_show_form(
            step_id="no_devices",
            data_schema=vol.Schema({
                vol.Optional("manual_entry", default=False): bool,
                vol.Optional("show_all", default=False): bool,
            }),
            last_step=False,
            description_placeholders={
                "help": "No EUC devices found. Make sure your device is powered on and in range. You can rescan or enter the MAC address manually."
            }
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual device entry."""
        errors = {}
        
        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper().strip()
            
            # Validate MAC address format
            import re
            if not re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', address):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"EUC ({address})",
                    data={CONF_ADDRESS: address},
                )
        
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): str,
            }),
            errors=errors,
            description_placeholders={
                "help": "Enter the Bluetooth MAC address of your EUC (e.g., 88:25:83:F3:5D:30)"
            }
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        if is_tpms_advertisement(discovery_info.name, discovery_info.manufacturer_data):
            self._discovered_device = discovery_info
            return await self.async_step_tpms_confirm()

        # Check if any of our supported service UUIDs are present
        if any(uuid in discovery_info.service_uuids for uuid in ALL_SERVICE_UUIDS):
            self._discovered_device = discovery_info
            return await self.async_step_bluetooth_confirm()

        return self.async_abort(reason="not_supported")

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovered_device is not None
        
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_device.name,
                data={CONF_ADDRESS: self._discovered_device.address},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovered_device.name
            },
        )

    async def async_step_tpms_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a discovered TPMS sensor: name, wheel link, minimum pressure."""
        assert self._discovered_device is not None
        address = self._discovered_device.address

        if user_input is not None:
            data, options = build_tpms_entry(address, user_input)
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=data, options=options
            )

        wheel_options = [SelectOptionDict(value=NO_WHEEL, label="None")] + [
            SelectOptionDict(value=entry.data[CONF_ADDRESS], label=entry.title)
            for entry in self._async_current_entries()
            if not is_tpms_entry(entry.data)
        ]
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=f"TPMS {address[-5:]}"): str,
            vol.Required(CONF_WHEEL_ADDRESS, default=NO_WHEEL): SelectSelector(
                SelectSelectorConfig(options=wheel_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_MIN_PRESSURE_PSI, default=DEFAULT_MIN_PRESSURE_PSI): MIN_PRESSURE_SCHEMA,
        })
        return self.async_show_form(
            step_id="tpms_confirm",
            data_schema=schema,
            description_placeholders={"address": address},
        )

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        """Only TPMS entries have options."""
        return is_tpms_entry(config_entry.data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the TPMS options flow."""
        return TpmsOptionsFlow()


class TpmsOptionsFlow(OptionsFlow):
    """Edit a TPMS sensor's minimum pressure."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_MIN_PRESSURE_PSI: float(user_input[CONF_MIN_PRESSURE_PSI])}
            )

        current = self.config_entry.options.get(CONF_MIN_PRESSURE_PSI, DEFAULT_MIN_PRESSURE_PSI)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_MIN_PRESSURE_PSI, default=current): MIN_PRESSURE_SCHEMA,
            }),
        )
