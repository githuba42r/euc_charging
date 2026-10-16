"""Config flow for Leaperkim EUC integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
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
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    ALL_SERVICE_UUIDS,
    CONF_ENTRY_TYPE,
    CONF_GOTWAY_CELLS,
    CONF_GOTWAY_MODEL,
    CONF_INMOTION_PASSWORD,
    CONF_INMOTION_PASSWORD_MODE,
    CONF_MIN_PRESSURE_PSI,
    CONF_WHEEL_ADDRESS,
    DEFAULT_GOTWAY_CELLS,
    DEFAULT_INMOTION_PASSWORD,
    DEFAULT_MIN_PRESSURE_PSI,
    DEVICE_NAMES,
    DOMAIN,
    ENTRY_TYPE_TPMS,
    GOTWAY_MODEL_AUTO,
    GOTWAY_MODEL_CUSTOM,
    INMOTION_PASSWORD_MAX_LEN,
    PASSWORD_MODE_CUSTOM,
    PASSWORD_MODE_DEFAULT,
    SERVICE_UUID,
    WheelBrand,
    is_inmotion_v1_device,
    is_tpms_entry,
    match_brand_by_name,
)
from .decoders import GotwayDecoder
from .gotway_models import GOTWAY_MODELS
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


def gotway_model_choices() -> list[SelectOptionDict]:
    """Auto-detect, Custom, then every model of EUC World's Gotway/Begode table."""
    return [
        SelectOptionDict(value=GOTWAY_MODEL_AUTO, label="Auto-detect"),
        SelectOptionDict(value=GOTWAY_MODEL_CUSTOM, label="Custom (enter pack size)"),
    ] + [
        SelectOptionDict(
            value=model.name,
            label=f"{model.make or 'Begode'} {model.name} ({model.full_voltage:g} V)",
        )
        for model in GOTWAY_MODELS
    ]


GOTWAY_CELL_CHOICES = [
    SelectOptionDict(value=str(cells), label=f"{cells}S ({cells * 4.2:.1f} V)")
    for cells in GotwayDecoder.CUSTOM_PACK_CELLS
]


def password_schema_fields(mode: str, password: str) -> dict:
    """Default/custom InMotion V1 password fields."""
    return {
        vol.Required(CONF_INMOTION_PASSWORD_MODE, default=mode): SelectSelector(
            SelectSelectorConfig(
                options=[PASSWORD_MODE_DEFAULT, PASSWORD_MODE_CUSTOM],
                translation_key="inmotion_password_mode",
                mode=SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(CONF_INMOTION_PASSWORD, default=password): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }


def resolve_password(
    user_input: dict[str, Any], current: str | None = None
) -> tuple[str | None, str | None]:
    """Return (password, error key) from the password fields.

    The stored custom password is never shown again, so an empty field with
    Custom selected keeps the current custom password.
    """
    if user_input.get(CONF_INMOTION_PASSWORD_MODE, PASSWORD_MODE_DEFAULT) != PASSWORD_MODE_CUSTOM:
        return DEFAULT_INMOTION_PASSWORD, None
    password = (user_input.get(CONF_INMOTION_PASSWORD) or "").strip()
    if not password and current and current != DEFAULT_INMOTION_PASSWORD:
        return current, None
    if not password or len(password) > INMOTION_PASSWORD_MAX_LEN or not password.isascii():
        return None, "invalid_password"
    return password, None


def password_defaults(data: dict[str, Any]) -> tuple[str, str]:
    """(mode, password) to pre-fill the form: never the stored password itself."""
    password = data.get(CONF_INMOTION_PASSWORD, DEFAULT_INMOTION_PASSWORD)
    mode = PASSWORD_MODE_DEFAULT if password == DEFAULT_INMOTION_PASSWORD else PASSWORD_MODE_CUSTOM
    return mode, ""


def build_wheel_options(entries: Iterable[ConfigEntry]) -> list[SelectOptionDict]:
    """Return the wheel dropdown options for the TPMS confirm form.

    "None" comes first, followed by every wheel (non-TPMS) entry that has an
    address. Entries without an address (e.g. ignored discoveries, whose data
    is empty) are skipped.
    """
    return [SelectOptionDict(value=NO_WHEEL, label="None")] + [
        SelectOptionDict(value=entry.data[CONF_ADDRESS], label=entry.title)
        for entry in entries
        if not is_tpms_entry(entry.data) and CONF_ADDRESS in entry.data
    ]


class EucChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Leaperkim EUC."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._show_all_devices = False
        self._pending_wheel: tuple[str | None, str] = (None, "")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self._async_create_wheel_entry(discovery_info)

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

            # TPMS sensors are set up via Bluetooth discovery, never as wheels
            if is_tpms_advertisement(discovery_info.name, discovery_info.manufacturer_data):
                _LOGGER.debug("Skipping %s - TPMS sensor", address)
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

    async def _async_create_wheel_entry(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Create the wheel entry, asking for the password first on InMotion V1."""
        self._pending_wheel = (discovery_info.name, discovery_info.address)
        if is_inmotion_v1_device(discovery_info.name, discovery_info.service_uuids):
            return await self.async_step_inmotion_password()
        return self.async_create_entry(
            title=discovery_info.name, data={CONF_ADDRESS: discovery_info.address}
        )

    async def async_step_inmotion_password(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """InMotion V1 wheels need a password (EUC World default 000000)."""
        errors: dict[str, str] = {}
        name, address = self._pending_wheel
        if user_input is not None:
            password, error = resolve_password(user_input)
            if error:
                errors[CONF_INMOTION_PASSWORD] = error
            else:
                return self.async_create_entry(
                    title=name,
                    data={CONF_ADDRESS: address, CONF_INMOTION_PASSWORD: password},
                )
        return self.async_show_form(
            step_id="inmotion_password",
            data_schema=vol.Schema(password_schema_fields(PASSWORD_MODE_DEFAULT, "")),
            errors=errors,
            description_placeholders={"name": name or address},
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
            return await self._async_create_wheel_entry(self._discovered_device)

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

        wheel_options = build_wheel_options(
            self._async_current_entries(include_ignore=False)
        )
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
        """TPMS entries and wheel entries have options."""
        return True

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the TPMS or wheel options flow."""
        if is_tpms_entry(config_entry.data):
            return TpmsOptionsFlow()
        return WheelOptionsFlow()


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


def wheel_option_fields(entry: ConfigEntry, brand: WheelBrand | None) -> tuple[bool, bool]:
    """Which settings apply: (Gotway model, InMotion V1 password).

    Uses the brand the coordinator detected; before detection, the brand the
    entry title (BLE name) maps to; a wheel matching neither gets both - a
    silent InMotion V1 with an unrecognised name is exactly such a wheel.
    """
    if brand is None:
        # Not detected yet (e.g. wheel off since HA started): go by the name.
        brand = match_brand_by_name(entry.title)
        if brand is None:
            return True, True
    return (
        brand in (WheelBrand.GOTWAY, WheelBrand.BEGODE),
        brand == WheelBrand.INMOTION or CONF_INMOTION_PASSWORD in entry.data,
    )


def gotway_option_fields(options: dict[str, Any]) -> dict:
    return {
        vol.Required(
            CONF_GOTWAY_MODEL, default=options.get(CONF_GOTWAY_MODEL, GOTWAY_MODEL_AUTO)
        ): SelectSelector(
            SelectSelectorConfig(options=gotway_model_choices(), mode=SelectSelectorMode.DROPDOWN)
        ),
        vol.Required(
            CONF_GOTWAY_CELLS, default=str(options.get(CONF_GOTWAY_CELLS, DEFAULT_GOTWAY_CELLS))
        ): SelectSelector(
            SelectSelectorConfig(options=GOTWAY_CELL_CHOICES, mode=SelectSelectorMode.DROPDOWN)
        ),
    }


def gotway_options_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_GOTWAY_MODEL: user_input[CONF_GOTWAY_MODEL],
        CONF_GOTWAY_CELLS: int(user_input[CONF_GOTWAY_CELLS]),
    }


class WheelOptionsFlow(OptionsFlow):
    """Wheel settings: Gotway/Begode model, InMotion V1 password.

    Applied by the entry's update listener without a reload.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Own step id so its strings don't clash with the TPMS options "init"."""
        return await self.async_step_wheel()

    async def async_step_wheel(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self.config_entry
        coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        decoder = getattr(coordinator, "decoder", None)
        brand = decoder.brand if decoder is not None else None
        show_gotway, show_password = wheel_option_fields(entry, brand)
        if not show_gotway and not show_password:
            return self.async_abort(reason="no_wheel_options")

        errors: dict[str, str] = {}
        if user_input is not None:
            options = dict(entry.options)
            if show_gotway:
                options.update(gotway_options_from_input(user_input))
            if show_password:
                password, error = resolve_password(
                    user_input, entry.data.get(CONF_INMOTION_PASSWORD)
                )
                if error:
                    errors[CONF_INMOTION_PASSWORD] = error
                elif password != entry.data.get(CONF_INMOTION_PASSWORD, DEFAULT_INMOTION_PASSWORD):
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_INMOTION_PASSWORD: password}
                    )
            if not errors:
                return self.async_create_entry(data=options)

        fields: dict = {}
        if show_gotway:
            fields.update(gotway_option_fields(dict(entry.options)))
        if show_password:
            fields.update(password_schema_fields(*password_defaults(dict(entry.data))))
        return self.async_show_form(
            step_id="wheel", data_schema=vol.Schema(fields), errors=errors
        )
