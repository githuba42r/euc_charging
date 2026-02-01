"""Data update coordinator for EUC Charging."""

from __future__ import annotations

import asyncio
import logging
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

from .const import (
    DOMAIN, NOTIFY_UUID, CONF_RETRY_COUNT, DEFAULT_RETRY_COUNT,
    KINGSONG_READ_UUID, GOTWAY_READ_UUID, VETERAN_READ_UUID,
    INMOTION_READ_UUID, INMOTION_WRITE_UUID,
    INMOTION_V2_READ_UUID, INMOTION_V2_WRITE_UUID,
    NINEBOT_READ_UUID, NINEBOT_WRITE_UUID,
    NINEBOT_Z_READ_UUID, NINEBOT_Z_WRITE_UUID,
    WheelBrand,
)
from .decoders import EucDecoder, get_decoder_by_data
from .charge_tracker import ChargeTracker

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


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

    def _setup_uuids_for_brand(self, brand: WheelBrand) -> None:
        """Set up read/write UUIDs and keepalive requirements based on brand."""
        if brand == WheelBrand.KINGSONG:
            self._read_uuid = KINGSONG_READ_UUID
            self._write_uuid = None
            self._requires_keepalive = False
        elif brand in (WheelBrand.GOTWAY, WheelBrand.BEGODE):
            self._read_uuid = GOTWAY_READ_UUID
            self._write_uuid = None
            self._requires_keepalive = False
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

    async def _keepalive_loop(self) -> None:
        """Send keepalive messages for brands that require them."""
        if not self._requires_keepalive or not self._write_uuid:
            return
        
        while True:
            try:
                if not self.client or not self.client.is_connected:
                    await asyncio.sleep(1)
                    continue
                
                # Send keepalive based on decoder brand
                if self.decoder:
                    keepalive_data = self.decoder.get_keepalive_packet()
                    if keepalive_data and self._write_uuid:
                        await self.client.write_gatt_char(self._write_uuid, keepalive_data, response=False)
                        _LOGGER.debug("Sent keepalive packet")
                
                # Keep-alive interval (25ms for InMotion, 1s for others)
                if self.decoder and self.decoder.brand in (WheelBrand.INMOTION, WheelBrand.INMOTION_V2):
                    await asyncio.sleep(0.025)  # 25ms
                else:
                    await asyncio.sleep(1.0)  # 1 second
                    
            except (BleakError, asyncio.TimeoutError) as ex:
                _LOGGER.warning("Keepalive failed: %s", ex)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error in keepalive loop")
                await asyncio.sleep(1)

    async def async_config_entry_first_refresh(self) -> None:
        """Handle the first refresh."""
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

                await self.client.connect()
                _LOGGER.info("Successfully connected to %s (%s)", self.ble_device.address, self.ble_device.name)

                # Start notifications on the read characteristic
                # We'll use NOTIFY_UUID as default, and switch once protocol is detected
                read_uuid = self._read_uuid or NOTIFY_UUID
                await self.client.start_notify(read_uuid, self._notification_handler)
                
                # Start keepalive task if required
                if self._requires_keepalive:
                    self._keepalive_task = self.hass.async_create_background_task(
                        self._keepalive_loop(), name="euc_keepalive_loop"
                    )
                    _LOGGER.info("Started keepalive task for bidirectional protocol")
                
                # Clear the device available event after successful connection
                self._device_available.clear()
                
                # Keep the loop running while connected
                while self.client and self.client.is_connected:
                    await asyncio.sleep(1)

            except (BleakError, asyncio.TimeoutError) as ex:
                _LOGGER.warning("Connection failed: %s, will retry...", ex)
                self.async_set_update_error(ex)
                await asyncio.sleep(10)  # Wait before retry
            
            except asyncio.CancelledError:
                if self.client:
                    await self.client.disconnect()
                raise

            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error in connection loop")
                await asyncio.sleep(10)

    @callback
    def _disconnected_callback(self, client: BleakClient) -> None:
        """Handle disconnection."""
        _LOGGER.info("Disconnected from %s", client.address)
        # Clear the device available event so we wait for it to be rediscovered
        self._device_available.clear()
        self._device_seen_recently = False
        self.async_set_update_error(Exception("Disconnected"))

    @callback
    def _notification_handler(self, characteristic: Any, data: bytearray) -> None:
        """Handle BLE notifications."""
        try:
            byte_data = bytes(data)
            
            # Auto-detect protocol if not yet established
            if not self.decoder:
                self.decoder = get_decoder_by_data(byte_data)
                if self.decoder:
                    _LOGGER.info("Protocol detected: %s (brand: %s)", self.decoder.name, self.decoder.brand)
                    # Setup UUIDs for this brand
                    self._setup_uuids_for_brand(self.decoder.brand)
                else:
                    # Buffer is too short or unknown header
                    return

            telemetry = self.decoder.decode(byte_data)
            if telemetry:
                # Add charge estimates with voltage data
                estimates = self.charge_tracker.update(
                    telemetry.get("battery_percent", 0),
                    telemetry.get("is_charging", False),
                    telemetry.get("voltage", 0)
                )
                telemetry["charge_estimates"] = estimates
                
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

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
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
