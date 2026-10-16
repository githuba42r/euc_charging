"""Data update coordinator for EUC Charging."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.device import BLEDevice

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_register_callback,
    BluetoothCallback,
    BluetoothCallbackMatcher,
    BluetoothChange,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, NOTIFY_UUID, CONF_RETRY_COUNT, DEFAULT_RETRY_COUNT,
    STORAGE_VERSION, STORAGE_SAVE_DELAY,
    KINGSONG_READ_UUID, GOTWAY_READ_UUID, VETERAN_READ_UUID,
    INMOTION_READ_UUID, INMOTION_WRITE_UUID, INMOTION_WRITE_SERVICE_UUID,
    INMOTION_V2_SERVICE_UUID, NINEBOT_SERVICE_UUID,
    INMOTION_V2_READ_UUID, INMOTION_V2_WRITE_UUID,
    NINEBOT_READ_UUID, NINEBOT_WRITE_UUID,
    NINEBOT_Z_READ_UUID, NINEBOT_Z_WRITE_UUID,
    WheelBrand,
    match_brand_by_name,
    CONF_GOTWAY_CELLS,
    CONF_GOTWAY_MODEL,
    CONF_INMOTION_PASSWORD,
    DEFAULT_GOTWAY_CELLS,
    DEFAULT_INMOTION_PASSWORD,
    GOTWAY_MODEL_AUTO,
    GOTWAY_MODEL_CUSTOM,
    INMOTION_PASSWORD_SILENT_CONNECTS,
    ISSUE_GOTWAY_MODEL,
    ISSUE_INMOTION_PASSWORD,
)
from .decoders import (
    EucDecoder,
    GotwayDecoder,
    InMotionDecoder,
    get_decoder_by_brand,
    get_decoder_by_data,
)
from .charge_tracker import ChargeTracker

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


def _known(value: Any, fallback: Any) -> Any:
    """Return value unless the protocol couldn't provide it (None)."""
    return fallback if value is None else value


class EucChargingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching EUC data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        ble_device: BLEDevice,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # We push updates
        )
        self.entry = entry
        self.ble_device = ble_device
        self.client: BleakClient | None = None
        self.decoder: EucDecoder | None = None
        self.charge_tracker = ChargeTracker()
        self._loop_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._retry_count = entry.options.get(CONF_RETRY_COUNT, DEFAULT_RETRY_COUNT)
        self._cancel_callback: BluetoothCallback | None = None
        self._device_available = asyncio.Event()
        self._device_seen_recently = False
        self._read_uuid: str | None = None
        self._write_uuid: str | None = None
        self._requires_keepalive = False
        # Set once notifications are enabled on a connection; the request loop
        # waits on it so nothing is written before replies can be received.
        self._requests_enabled = asyncio.Event()
        self._write_failure_logged = False
        # Decoder chosen from the BLE name (request-driven protocols) rather
        # than from data; dropped if it never decodes anything.
        self._preselected = False
        self._preselect_disabled = False
        self._connects_without_data = 0
        # InMotion V1: connections where the password went out but no live data came back
        self._silent_password_connects = 0
        self._password_issue_open = False
        # Whether the Gotway "select model" issue is raised; None = not yet
        # synced this run (so a stale issue from a previous run gets cleared).
        self._gotway_issue_open: bool | None = None
        self.auto_connect_enabled = True  # Default to enabled
        self._reconnect_event = asyncio.Event()
        
        # Store last known values (persist even when disconnected)
        self.last_connected_time: datetime | None = None
        self.last_voltage: float | None = None
        self.last_battery_percent: float | None = None
        self.last_trip_distance: float | None = None
        self.last_total_distance: float | None = None

        # Backing store so the last known values also survive a Home Assistant restart
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    async def _async_load_last_known(self) -> None:
        """Restore the last known values from disk."""
        try:
            stored = await self._store.async_load()
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to load stored last known values")
            return

        if not stored:
            _LOGGER.debug("No stored last known values for %s", self.ble_device.address)
            return

        self.last_voltage = stored.get("last_voltage")
        self.last_battery_percent = stored.get("last_battery_percent")
        self.last_trip_distance = stored.get("last_trip_distance")
        self.last_total_distance = stored.get("last_total_distance")

        if raw_time := stored.get("last_connected_time"):
            self.last_connected_time = dt_util.parse_datetime(raw_time)

        _LOGGER.info(
            "Restored last known values for %s: battery=%s%%, voltage=%sV, last connected=%s",
            self.ble_device.address,
            self.last_battery_percent,
            self.last_voltage,
            self.last_connected_time,
        )

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        """Return the last known values in a JSON serialisable form."""
        return {
            "last_connected_time": (
                self.last_connected_time.isoformat() if self.last_connected_time else None
            ),
            "last_voltage": self.last_voltage,
            "last_battery_percent": self.last_battery_percent,
            "last_trip_distance": self.last_trip_distance,
            "last_total_distance": self.last_total_distance,
        }

    @callback
    def _schedule_save(self) -> None:
        """Queue a debounced write of the last known values."""
        self._store.async_delay_save(self._data_to_save, STORAGE_SAVE_DELAY)

    def _setup_uuids_for_brand(self, brand: WheelBrand) -> None:
        """Set up read/write UUIDs and keepalive requirements based on brand."""
        if brand == WheelBrand.KINGSONG:
            # Live data is pushed; the only write is the name request used to
            # pick the model's battery curve (same characteristic, wh/z.java).
            self._read_uuid = KINGSONG_READ_UUID
            self._write_uuid = KINGSONG_READ_UUID
            self._requires_keepalive = True
        elif brand in (WheelBrand.GOTWAY, WheelBrand.BEGODE):
            # Gotway streams unprompted; the writes are the one-off "N"/"V"
            # name/firmware probe used to pick the wheel model (same characteristic).
            self._read_uuid = GOTWAY_READ_UUID
            self._write_uuid = GOTWAY_READ_UUID
            self._requires_keepalive = True
        elif brand in (WheelBrand.VETERAN, WheelBrand.LEAPERKIM):
            self._read_uuid = VETERAN_READ_UUID
            self._write_uuid = None
            self._requires_keepalive = False
        elif brand == WheelBrand.INMOTION:
            self._read_uuid = INMOTION_READ_UUID
            self._write_uuid = INMOTION_WRITE_UUID
            self._requires_keepalive = True
        elif brand == WheelBrand.INMOTION_V2:
            self._read_uuid = INMOTION_V2_READ_UUID
            self._write_uuid = INMOTION_V2_WRITE_UUID
            self._requires_keepalive = True
        elif brand == WheelBrand.NINEBOT:
            self._read_uuid = NINEBOT_READ_UUID
            self._write_uuid = NINEBOT_WRITE_UUID
            self._requires_keepalive = True
        elif brand == WheelBrand.NINEBOT_Z:
            self._read_uuid = NINEBOT_Z_READ_UUID
            self._write_uuid = NINEBOT_Z_WRITE_UUID
            self._requires_keepalive = True
        else:
            # Default to Veteran/KingSong UUIDs
            self._read_uuid = NOTIFY_UUID
            self._write_uuid = None
            self._requires_keepalive = False

    # Poll interval once the decoder has nothing left to send.
    IDLE_REQUEST_INTERVAL = 5.0
    # Connections without a decoded packet before a name-preselected decoder
    # is dropped in favour of detecting the protocol from data.
    PRESELECT_MAX_EMPTY_CONNECTS = 3

    async def _keepalive_loop(self) -> None:
        """Write the decoder's requests (keepalives, handshakes, register polls)."""
        if not self._requires_keepalive or not self._write_uuid:
            return
        
        while True:
            try:
                if not self.client or not self.client.is_connected:
                    self._requests_enabled.clear()
                if not self._requests_enabled.is_set():
                    # Idle until a connection has notifications enabled.
                    await self._requests_enabled.wait()
                    continue
                
                # The decoder decides what to send and when (static keepalive,
                # Gotway name probe, Ninebot request/response state machine).
                interval = self.IDLE_REQUEST_INTERVAL
                decoder = self.decoder
                if decoder:
                    for packet in decoder.get_requests():
                        if not self._write_uuid:
                            break
                        for i, piece in enumerate(decoder.split_write(packet)):
                            if i and decoder.write_chunk_delay:
                                await asyncio.sleep(decoder.write_chunk_delay)
                            await self.client.write_gatt_char(self._write_uuid, piece, response=False)
                        _LOGGER.debug("Sent request %s", packet.hex())
                        self._write_failure_logged = False
                    if decoder.has_pending_requests:
                        interval = decoder.request_interval
                
                await asyncio.sleep(interval)
                    
            except (BleakError, asyncio.TimeoutError) as ex:
                # Warn once per failure streak; a dead link would otherwise log every second.
                if not self._write_failure_logged:
                    _LOGGER.warning("Request write failed: %s", ex)
                    self._write_failure_logged = True
                else:
                    _LOGGER.debug("Request write failed: %s", ex)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error in keepalive loop")
                await asyncio.sleep(1)

    async def async_config_entry_first_refresh(self) -> None:
        """Handle the first refresh."""
        # Restore last known values before any entity is created, so the "last_*"
        # sensors report their stored value immediately instead of Unknown.
        await self._async_load_last_known()

        # Register a callback to be notified when the device is discovered
        self._cancel_callback = async_register_callback(
            self.hass,
            self._bluetooth_discovery_callback,
            BluetoothCallbackMatcher(address=self.ble_device.address),
            BluetoothChange.ADVERTISEMENT,
        )
        
        # Check if device is already available (don't require connectable flag for ESPHome proxies)
        ble_device = async_ble_device_from_address(
            self.hass, self.ble_device.address, connectable=False
        )
        if ble_device:
            self.ble_device = ble_device
            self._device_available.set()
            _LOGGER.info("Device %s already available at startup", self.ble_device.address)
        
        # We don't poll, so we just start the connection loop
        # But HA expects data to be available after this calls.
        # Since we might not be connected yet, we set initial data to empty or wait briefly.
        self._loop_task = self.hass.async_create_background_task(
            self._connect_loop(), name="euc_charging_connect_loop"
        )
        # We don't raise ConfigEntryNotReady here because we want to allow HA to start
        # while we try to connect in background.
        self.data = {}

    @callback
    def _bluetooth_discovery_callback(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        """Handle Bluetooth discovery updates."""
        # Log which source (proxy) is reporting the device
        source = getattr(service_info, 'source', 'unknown')
        _LOGGER.info(
            "Bluetooth discovery callback: %s (%s), change: %s, RSSI: %s, source: %s",
            service_info.device.name or "Unknown",
            service_info.device.address,
            change,
            service_info.rssi,
            source,
        )
        # Update the BLE device with the latest service info
        self.ble_device = service_info.device
        self._device_seen_recently = True
        # Signal that the device is available
        self._device_available.set()

    async def _connect_loop(self) -> None:
        """Main connection loop."""
        while True:
            try:
                # Check if auto-connect is disabled
                if not self.auto_connect_enabled:
                    # If currently connected, disconnect
                    if self.client and self.client.is_connected:
                        _LOGGER.info("Auto-connect disabled, disconnecting from %s", self.ble_device.address)
                        
                        # Save current values to last_* properties before disconnecting
                        if self.data:
                            _LOGGER.debug(
                                "Saving last known values on manual disconnect: battery=%.1f%%, voltage=%.2fV",
                                self.data.get("battery_percent") or 0,
                                self.data.get("voltage") or 0
                            )
                            self.last_voltage = _known(self.data.get("voltage"), self.last_voltage)
                            self.last_battery_percent = _known(self.data.get("battery_percent"), self.last_battery_percent)
                            self.last_trip_distance = _known(self.data.get("trip_distance"), self.last_trip_distance)
                            self.last_total_distance = _known(self.data.get("total_distance"), self.last_total_distance)
                            self.last_connected_time = dt_util.now()
                            self._schedule_save()

                        try:
                            read_uuid = self._read_uuid or NOTIFY_UUID
                            await self.client.stop_notify(read_uuid)
                            await self.client.disconnect()
                        except (BleakError, asyncio.TimeoutError) as ex:
                            _LOGGER.debug("Error during disconnect: %s", ex)
                        self.client = None
                        
                        # Clear data so sensors become unavailable (except "last_*" sensors which persist)
                        # This will trigger all listeners to update, including the "last_*" sensors
                        self.async_set_updated_data(None)
                    
                    # Wait for reconnect event or check again in 5 seconds
                    try:
                        await asyncio.wait_for(self._reconnect_event.wait(), timeout=5.0)
                        self._reconnect_event.clear()
                    except asyncio.TimeoutError:
                        pass
                    continue
                
                # If already connected, just sleep and continue
                if self.client and self.client.is_connected:
                    await asyncio.sleep(5)
                    continue

                # Wait for device to be available (discovered via Bluetooth)
                _LOGGER.debug("Waiting for device %s to be available...", self.ble_device.address)
                
                # Check periodically with timeout
                device_found = False
                for attempt in range(60):  # Wait up to 5 minutes (60 * 5 seconds)
                    # Don't require connectable flag for ESPHome proxies
                    ble_device = async_ble_device_from_address(
                        self.hass, self.ble_device.address, connectable=False
                    )
                    if ble_device:
                        self.ble_device = ble_device
                        device_found = True
                        _LOGGER.debug("Device found via address lookup on attempt %d", attempt + 1)
                        break
                    
                    # Also check if the discovery callback set the event
                    try:
                        await asyncio.wait_for(self._device_available.wait(), timeout=5.0)
                        device_found = True
                        _LOGGER.debug("Device found via discovery callback on attempt %d", attempt + 1)
                        break
                    except asyncio.TimeoutError:
                        continue
                
                if not device_found:
                    _LOGGER.warning(
                        "Device %s not found after 5 minutes, will retry...",
                        self.ble_device.address
                    )
                    # Clear data so sensors become unavailable (except "last_*" sensors which persist)
                    self.async_set_updated_data(None)
                    self.async_set_update_error(
                        Exception("Device not available - is it powered on?")
                    )
                    await asyncio.sleep(30)  # Wait 30 seconds before trying again
                    continue

                # Device is available, try to connect
                _LOGGER.info(
                    "Device %s is available (name: %s, rssi: %s), attempting to connect...",
                    self.ble_device.address,
                    getattr(self.ble_device, 'name', 'Unknown'),
                    getattr(self.ble_device, 'rssi', 'unknown')
                )
                
                self.client = BleakClient(
                    self.ble_device,
                    disconnected_callback=self._disconnected_callback,
                    timeout=20.0,
                )

                self._requests_enabled.clear()
                await self.client.connect()
                _LOGGER.info("Successfully connected to %s (%s)", self.ble_device.address, self.ble_device.name)

                # Ninebot/InMotion wheels only answer requests, so their protocol can't be
                # detected from incoming data: pick it from the BLE name up front.
                self._check_preselected_decoder()
                self._check_inmotion_password()
                if not self.decoder:
                    self._preselect_decoder_by_name()

                # Start notifications on the read characteristic
                # We'll use NOTIFY_UUID as default, and switch once protocol is detected
                read_uuid = self._read_uuid or NOTIFY_UUID
                try:
                    await self.client.start_notify(read_uuid, self._notification_handler)
                except BleakError:
                    if not self._preselected:
                        raise
                    # The name-picked protocol's characteristic isn't there: forget
                    # it and listen on the default characteristic instead.
                    _LOGGER.warning(
                        "Preselected %s has no characteristic %s; detecting from data",
                        self.decoder.name if self.decoder else None, read_uuid,
                    )
                    self._drop_preselected_decoder()
                    await self.client.start_notify(NOTIFY_UUID, self._notification_handler)

                # Restart the protocol session only now that replies can arrive,
                # so the first request of a handshake/probe isn't lost.
                if self.decoder:
                    self.decoder.reset_session()
                self._requests_enabled.set()
                
                # Start keepalive task if required
                self._ensure_keepalive_task()
                
                # Clear the device available event after successful connection
                self._device_available.clear()
                
                # Keep the loop running while connected
                while self.client and self.client.is_connected:
                    await asyncio.sleep(1)

            except (BleakError, asyncio.TimeoutError) as ex:
                _LOGGER.warning("Connection failed: %s, will retry...", ex)
                # Clear data so sensors become unavailable (except "last_*" sensors which persist)
                self.async_set_updated_data(None)
                self.async_set_update_error(ex)
                await asyncio.sleep(10)  # Wait before retry
            
            except asyncio.CancelledError:
                if self.client:
                    await self.client.disconnect()
                raise

            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error in connection loop")
                await asyncio.sleep(10)

    def _wheel_name(self) -> str | None:
        """BLE name, or the config entry title when a proxy reports no name."""
        return getattr(self.ble_device, "name", None) or getattr(self.entry, "title", None)

    def _gatt_service_uuids(self) -> set[str] | None:
        """Service UUIDs of the connected wheel (None if unknown)."""
        services = getattr(self.client, "services", None)
        if not services:
            return None
        try:
            return {str(service.uuid).lower() for service in services}
        except (TypeError, AttributeError, BleakError):
            return None

    def _preselect_brand(self) -> WheelBrand | None:
        """Request-driven brand from the BLE name, checked against GATT services.

        InMotion V2 and Ninebot Z use the Nordic UART service, InMotion V1 the
        FFE5 write service and Ninebot One FFE0 (const.py; ui/a.java). When the
        services are known they settle V1/V2 and One/Z, and veto a name match
        whose service is missing.
        """
        brand = match_brand_by_name(self._wheel_name())
        if brand not in (
            WheelBrand.NINEBOT, WheelBrand.NINEBOT_Z,
            WheelBrand.INMOTION, WheelBrand.INMOTION_V2,
        ):
            return None
        services = self._gatt_service_uuids()
        if services is None:
            return brand
        nus = INMOTION_V2_SERVICE_UUID in services
        if brand in (WheelBrand.INMOTION, WheelBrand.INMOTION_V2):
            if nus:
                return WheelBrand.INMOTION_V2
            if INMOTION_WRITE_SERVICE_UUID in services:
                return WheelBrand.INMOTION
            return None
        if nus and NINEBOT_SERVICE_UUID not in services:
            return WheelBrand.NINEBOT_Z
        if NINEBOT_SERVICE_UUID in services and not nus:
            return WheelBrand.NINEBOT
        return brand if (nus or NINEBOT_SERVICE_UUID in services) else None

    def _preselect_decoder_by_name(self) -> None:
        """Create the decoder from the BLE name for request-driven protocols."""
        if self._preselect_disabled:
            return
        brand = self._preselect_brand()
        if brand is None:
            return
        self.decoder = get_decoder_by_brand(brand)
        self._configure_decoder()
        self._preselected = True
        self._connects_without_data = 0
        _LOGGER.info("Protocol preselected from BLE name: %s", self.decoder.name)
        self._setup_uuids_for_brand(brand)

    def _drop_preselected_decoder(self) -> None:
        """Forget a name-picked decoder for good and fall back to data detection."""
        self.decoder = None
        self._preselected = False
        self._preselect_disabled = True
        self._setup_uuids_for_brand(WheelBrand.UNKNOWN)

    def _check_preselected_decoder(self) -> None:
        """Drop a preselected decoder after several connections with no decoded packet."""
        if not self._preselected or not self.decoder:
            return
        if self.decoder.packet_count > 0:
            self._preselected = False   # confirmed; treat like a detected decoder
            return
        if isinstance(self.decoder, InMotionDecoder):
            # A silent InMotion V1 is most likely a wrong password (raised as a
            # repair issue), not a wrong protocol: its FFE5 service was checked.
            return
        self._connects_without_data += 1
        if self._connects_without_data > self.PRESELECT_MAX_EMPTY_CONNECTS:
            _LOGGER.warning(
                "%s decoded nothing in %d connections; detecting the protocol from data",
                self.decoder.name, self.PRESELECT_MAX_EMPTY_CONNECTS,
            )
            self._drop_preselected_decoder()

    # --- wheel options and repair issues ---------------------------------------

    def _issue_id(self, kind: str) -> str:
        return f"{kind}_{self.entry.entry_id}"

    @callback
    def _configure_decoder(self) -> None:
        """Apply the entry's wheel settings to the current decoder."""
        decoder = self.decoder
        options = getattr(self.entry, "options", {}) or {}
        data = getattr(self.entry, "data", {}) or {}
        if isinstance(decoder, GotwayDecoder):
            choice = options.get(CONF_GOTWAY_MODEL, GOTWAY_MODEL_AUTO)
            if choice == GOTWAY_MODEL_CUSTOM:
                decoder.set_custom_pack(int(options.get(CONF_GOTWAY_CELLS, DEFAULT_GOTWAY_CELLS)))
            elif choice != GOTWAY_MODEL_AUTO and decoder.set_model(choice):
                pass
            else:
                decoder.clear_model_override()
        elif isinstance(decoder, InMotionDecoder):
            decoder.password = data.get(CONF_INMOTION_PASSWORD, DEFAULT_INMOTION_PASSWORD)

    @callback
    def async_apply_options(self) -> None:
        """Entry options/data changed: apply without reloading."""
        decoder = self.decoder
        password_before = getattr(decoder, "password", None)
        self._configure_decoder()
        if isinstance(decoder, InMotionDecoder) and decoder.password != password_before:
            # Retry with the new password straight away and give it fresh chances.
            self._silent_password_connects = 0
            self._preselect_disabled = False
            decoder.reset_session()
        self._update_issues()

    @callback
    def _update_issues(self) -> None:
        """Raise/clear the Gotway model and InMotion password repair issues."""
        if self.hass is None or getattr(self.entry, "entry_id", None) is None:
            return
        decoder = self.decoder
        if isinstance(decoder, GotwayDecoder):
            unmatched = decoder.model_unmatched
            if unmatched == self._gotway_issue_open:
                pass   # no change; avoid touching the registry on every packet
            elif unmatched:
                self._gotway_issue_open = True
                ir.async_create_issue(
                    self.hass, DOMAIN, self._issue_id(ISSUE_GOTWAY_MODEL),
                    is_fixable=True,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=ISSUE_GOTWAY_MODEL,
                    translation_placeholders={"name": self.entry.title or ""},
                    data={"entry_id": self.entry.entry_id},
                )
            else:
                self._gotway_issue_open = False
                ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(ISSUE_GOTWAY_MODEL))
        if (
            isinstance(decoder, InMotionDecoder)
            and decoder.values_received
            and (self._password_issue_open or self._silent_password_connects)
        ):
            self._silent_password_connects = 0
            self._password_issue_open = False
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(ISSUE_INMOTION_PASSWORD))

    @callback
    def _check_inmotion_password(self) -> None:
        """At connect: count the previous InMotion V1 session if it stayed silent."""
        decoder = self.decoder
        if not isinstance(decoder, InMotionDecoder):
            return
        if not decoder.password_sent or decoder.values_received:
            return
        self._silent_password_connects += 1
        if self._silent_password_connects >= INMOTION_PASSWORD_SILENT_CONNECTS:
            self._password_issue_open = True
            ir.async_create_issue(
                self.hass, DOMAIN, self._issue_id(ISSUE_INMOTION_PASSWORD),
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_INMOTION_PASSWORD,
                translation_placeholders={"name": self.entry.title or ""},
                data={"entry_id": self.entry.entry_id},
            )

    def _detection_matches_name(self, decoder: EucDecoder) -> bool:
        """Reject a data-based detection that contradicts a passive brand's BLE name.

        A Veteran (DC 5A 5C) detection is always accepted: that header can't
        come from another brand, and EUC World itself switches a wheel it took
        for a Gotway to Veteran on seeing it (wh/s.java h()).
        """
        if decoder.brand in (WheelBrand.VETERAN, WheelBrand.LEAPERKIM):
            return True
        hint = match_brand_by_name(self._wheel_name())
        passive = {
            WheelBrand.VETERAN: (WheelBrand.VETERAN, WheelBrand.LEAPERKIM),
            WheelBrand.KINGSONG: (WheelBrand.KINGSONG,),
            WheelBrand.GOTWAY: (WheelBrand.GOTWAY, WheelBrand.BEGODE),
        }
        if hint not in passive:
            return True
        if decoder.brand in passive[hint]:
            return True
        _LOGGER.debug(
            "Ignoring %s-looking data from %s-named wheel", decoder.brand, hint
        )
        return False

    @callback
    def _ensure_keepalive_task(self) -> None:
        """Start the request loop if this protocol writes and it isn't running."""
        if not self._requires_keepalive:
            return
        if self._keepalive_task and not self._keepalive_task.done():
            return
        self._keepalive_task = self.hass.async_create_background_task(
            self._keepalive_loop(), name="euc_keepalive_loop"
        )
        _LOGGER.info("Started request task for bidirectional protocol")

    @callback
    def _disconnected_callback(self, client: BleakClient) -> None:
        """Handle disconnection."""
        _LOGGER.info("Disconnected from %s", client.address)
        
        # Save current values to last_* properties before clearing data
        # Use self.data if available, otherwise keep existing last_* values
        if self.data:
            _LOGGER.debug(
                "Saving last known values on disconnect: battery=%.1f%%, voltage=%.2fV, total_distance=%.2fkm",
                self.data.get("battery_percent") or 0,
                self.data.get("voltage") or 0,
                self.data.get("total_distance") or 0
            )
            self.last_voltage = _known(self.data.get("voltage"), self.last_voltage)
            self.last_battery_percent = _known(self.data.get("battery_percent"), self.last_battery_percent)
            self.last_trip_distance = _known(self.data.get("trip_distance"), self.last_trip_distance)
            self.last_total_distance = _known(self.data.get("total_distance"), self.last_total_distance)
        else:
            _LOGGER.warning(
                "No data available on disconnect, keeping existing last known values: "
                "battery=%.1f%%, voltage=%.2fV, total_distance=%.2fkm",
                self.last_battery_percent or 0,
                self.last_voltage or 0,
                self.last_total_distance or 0
            )
        
        # Update last connected time to disconnect time
        self.last_connected_time = dt_util.now()
        _LOGGER.info(
            "Updated last_connected_time to %s (disconnect time)",
            self.last_connected_time.isoformat() if self.last_connected_time else "None"
        )
        self._schedule_save()

        # Stop the request loop until the next connection enables notifications
        self._requests_enabled.clear()

        # Clear the device available event so we wait for it to be rediscovered
        self._device_available.clear()
        self._device_seen_recently = False
        
        # Clear data so sensors become unavailable (except "last_*" sensors which persist)
        # This will trigger all listeners to update, including the "last_*" sensors
        self.async_set_updated_data(None)
        self.async_set_update_error(Exception("Disconnected"))

    @callback
    def _notification_handler(self, characteristic: Any, data: bytearray) -> None:
        """Handle BLE notifications."""
        try:
            byte_data = bytes(data)
            
            # Auto-detect protocol if not yet established
            if not self.decoder:
                decoder = get_decoder_by_data(byte_data)
                if decoder and not self._detection_matches_name(decoder):
                    # A chunk that starts mid-frame can look like another
                    # brand's header; trust the BLE name for passive brands.
                    return
                self.decoder = decoder
                if self.decoder:
                    _LOGGER.info("Protocol detected: %s (brand: %s)", self.decoder.name, self.decoder.brand)
                    # Setup UUIDs for this brand
                    self._setup_uuids_for_brand(self.decoder.brand)
                    self._configure_decoder()
                else:
                    # Buffer is too short or unknown header
                    return

            telemetry = self.decoder.decode(byte_data)
            if telemetry:
                self._update_issues()

            # Protocols detected from data only start writing (Gotway/KingSong
            # model probe) once a packet has actually decoded, so a
            # misdetection never sends bytes to the wheel.
            if self.decoder.packet_count > 0:
                self._ensure_keepalive_task()
            if telemetry:
                # Update last connected time and store last known values.
                # Only overwrite when the packet actually carried the field, so a
                # partial packet can't wipe a value we already know.
                self.last_connected_time = dt_util.now()
                if (voltage := telemetry.get("voltage")) is not None:
                    self.last_voltage = voltage
                if (battery := telemetry.get("battery_percent")) is not None:
                    self.last_battery_percent = battery
                if (trip := telemetry.get("trip_distance")) is not None:
                    self.last_trip_distance = trip
                if (total := telemetry.get("total_distance")) is not None:
                    self.last_total_distance = total
                self._schedule_save()

                # Add charge estimates with voltage data. Some protocols can't
                # report battery percent or charging state (None); don't feed
                # unknowns into the tracker.
                battery_percent = telemetry.get("battery_percent")
                estimates = self.charge_tracker.update(
                    battery_percent if battery_percent is not None else 0,
                    bool(telemetry.get("is_charging")) and battery_percent is not None,
                    telemetry.get("voltage") or 0,
                )
                telemetry["charge_estimates"] = estimates
                
                # Add last connected time to telemetry
                telemetry["last_connected_time"] = self.last_connected_time
                
                self.async_set_updated_data(telemetry)
                
                # Update device registry if needed (e.g. on first packet with model info)
                if self.ble_device and telemetry.get("model") and telemetry.get("version"):
                    device_registry = dr.async_get(self.hass)
                    device_entry = device_registry.async_get_device(
                        identifiers={(DOMAIN, self.ble_device.address)}
                    )
                    if device_entry and (
                        device_entry.model != telemetry["model"] or 
                        device_entry.sw_version != telemetry["version"]
                    ):
                        device_registry.async_update_device(
                            device_entry.id,
                            model=telemetry["model"],
                            manufacturer=telemetry.get("manufacturer", "Leaperkim"),
                            sw_version=telemetry["version"],
                        )

        except Exception as ex:
            _LOGGER.error("Error decoding packet: %s", ex)

    def trigger_reconnect(self) -> None:
        """Trigger a reconnection attempt."""
        self._reconnect_event.set()

    async def disconnect(self) -> None:
        """Disconnect from the EUC."""
        if self.client and self.client.is_connected:
            try:
                read_uuid = self._read_uuid or NOTIFY_UUID
                await self.client.stop_notify(read_uuid)
                await self.client.disconnect()
            except (BleakError, asyncio.TimeoutError) as ex:
                _LOGGER.debug("Error during disconnect: %s", ex)
            self.client = None

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        # Flush the last known values immediately, cancelling any pending delayed
        # write, so they survive a restart or a reload of the config entry.
        try:
            await self._store.async_save(self._data_to_save())
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to save last known values on shutdown")

        # Unregister the Bluetooth discovery callback
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None
        
        # Cancel keepalive task
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        
        if self.client and self.client.is_connected:
            try:
                read_uuid = self._read_uuid or NOTIFY_UUID
                await self.client.stop_notify(read_uuid)
                await self.client.disconnect()
            except (BleakError, asyncio.TimeoutError):
                pass
