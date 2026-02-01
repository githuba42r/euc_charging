#!/usr/bin/env python3
"""
EUC Scanner and Debugger.

This tool connects to EUC devices and streams raw + decoded data for debugging.
It uses the decoders from the custom component but mocks the Home Assistant environment
to run standalone.
"""

import asyncio
import logging
import sys
import argparse
import time
from datetime import datetime
from typing import Optional, Any

# Mock Home Assistant imports BEFORE importing custom_components
import types

# 1. Define the mocks
ha = types.ModuleType('homeassistant')
ha.components = types.ModuleType('homeassistant.components')
ha.components.bluetooth = types.ModuleType('homeassistant.components.bluetooth')
ha.components.bluetooth.async_ble_device_from_address = lambda *args, **kwargs: None
ha.components.bluetooth.BluetoothServiceInfoBleak = type('BluetoothServiceInfoBleak', (), {})

ha.config_entries = types.ModuleType('homeassistant.config_entries')
ha.config_entries.ConfigEntry = type('ConfigEntry', (), {})
ha.config_entries.ConfigFlow = type('ConfigFlow', (), {})

ha.const = types.ModuleType('homeassistant.const')
ha.const.CONF_ADDRESS = "address"
ha.const.Platform = type('Platform', (), {'SENSOR': 'sensor', 'BINARY_SENSOR': 'binary_sensor'})

ha.core = types.ModuleType('homeassistant.core')
ha.core.HomeAssistant = type('HomeAssistant', (), {})
ha.core.callback = lambda x: x

ha.exceptions = types.ModuleType('homeassistant.exceptions')
ha.exceptions.ConfigEntryNotReady = type('ConfigEntryNotReady', (Exception,), {})

ha.helpers = types.ModuleType('homeassistant.helpers')
ha.helpers.device_registry = types.ModuleType('homeassistant.helpers.device_registry')
ha.helpers.device_registry.async_get = lambda *args: None

ha.helpers.entity_platform = types.ModuleType('homeassistant.helpers.entity_platform')
ha.helpers.entity_platform.AddEntitiesCallback = type('AddEntitiesCallback', (), {})

ha.helpers.update_coordinator = types.ModuleType('homeassistant.helpers.update_coordinator')
class MockDataUpdateCoordinator:
    def __class_getitem__(cls, item):
        return cls
    def __init__(self, *args, **kwargs):
        pass
ha.helpers.update_coordinator.DataUpdateCoordinator = MockDataUpdateCoordinator
ha.helpers.update_coordinator.UpdateFailed = type('UpdateFailed', (Exception,), {})

ha.data_entry_flow = types.ModuleType('homeassistant.data_entry_flow')
ha.data_entry_flow.FlowResult = type('FlowResult', (), {})

# 2. Inject into sys.modules
sys.modules['homeassistant'] = ha
sys.modules['homeassistant.components'] = ha.components
sys.modules['homeassistant.components.bluetooth'] = ha.components.bluetooth
sys.modules['homeassistant.config_entries'] = ha.config_entries
sys.modules['homeassistant.const'] = ha.const
sys.modules['homeassistant.core'] = ha.core
sys.modules['homeassistant.exceptions'] = ha.exceptions
sys.modules['homeassistant.helpers'] = ha.helpers
sys.modules['homeassistant.helpers.device_registry'] = ha.helpers.device_registry
sys.modules['homeassistant.helpers.entity_platform'] = ha.helpers.entity_platform
sys.modules['homeassistant.helpers.update_coordinator'] = ha.helpers.update_coordinator
sys.modules['homeassistant.data_entry_flow'] = ha.data_entry_flow

# Now we can import from the component
sys.path.append(".")
try:
    from bleak import BleakScanner, BleakClient, BleakError
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except ImportError:
    print("Error: 'bleak' is required. Run: pip install bleak")
    sys.exit(1)

try:
    from custom_components.euc_charging.decoders import EucDecoder, get_decoder_by_data
    from custom_components.euc_charging.const import SERVICE_UUID, NOTIFY_UUID
except ImportError as e:
    print(f"Error importing local decoder: {e}")
    print("Ensure you are running from the root of the euc-dump repository.")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger("euc_debug")

class EucDebugger:
    def __init__(self, raw_only: bool = False, snapshot: bool = False):
        self.devices: dict[str, tuple[BLEDevice, AdvertisementData]] = {}
        self.selected_device: Optional[BLEDevice] = None
        self.decoder: Optional[EucDecoder] = None
        self.raw_only = raw_only
        self.snapshot = snapshot
        self.start_time = time.time()
        self.packet_count = 0
        self.stop_event = asyncio.Event()

    def detection_callback(self, device: BLEDevice, advertisement_data: AdvertisementData):
        if SERVICE_UUID.lower() in advertisement_data.service_uuids:
            if device.address not in self.devices:
                self.devices[device.address] = (device, advertisement_data)
                print(f"  [+] Found: {device.name or 'Unknown'} ({device.address}) RSSI: {advertisement_data.rssi}")

    async def scan(self):
        print("--- Scanning for EUC Devices (5s) ---")
        scanner = BleakScanner(self.detection_callback)
        await scanner.start()
        await asyncio.sleep(5)
        await scanner.stop()

        if not self.devices:
            print("\nNo devices found matching the EUC Service UUID.")
            return

        print("\n--- Available Devices ---")
        sorted_devices = sorted(self.devices.values(), key=lambda x: x[1].rssi, reverse=True)
        
        for idx, (dev, adv) in enumerate(sorted_devices):
            print(f"{idx + 1}. {dev.name or 'Unknown'} ({dev.address}) - RSSI: {adv.rssi}")

        while True:
            try:
                choice = input("\nSelect device # (or 'q' to quit): ")
                if choice.lower() == 'q':
                    sys.exit(0)
                
                idx = int(choice) - 1
                if 0 <= idx < len(sorted_devices):
                    self.selected_device = sorted_devices[idx][0]
                    break
                print("Invalid selection.")
            except ValueError:
                print("Please enter a number.")

        if self.selected_device:
            await self.connect_and_stream(self.selected_device)

    def notification_handler(self, sender: Any, data: bytearray):
        # Bleak callback signature: (sender: BleakGATTCharacteristic, data: bytearray)
        # But 'sender' is an object, commonly treated as ID or ignored. 
        # Type checkers might complain if we hint it as int.
        byte_data = bytes(data)
        self.packet_count += 1
        
        # Hex dump
        hex_str = ' '.join(f'{b:02X}' for b in byte_data)
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        if not self.decoder:
            self.decoder = get_decoder_by_data(byte_data)
            if self.decoder:
                print(f"\n[{timestamp}] PROTOCOL DETECTED: {self.decoder.name}")
            else:
                print(f"[{timestamp}] UNKNOWN PROTOCOL: {hex_str}")
                return

        if self.raw_only:
            print(f"[{timestamp}] RAW: {hex_str}")
            return

        telemetry = self.decoder.decode(byte_data)
        if telemetry:
            print(f"[{timestamp}] RAW: {hex_str}")
            print(f"    Voltage: {telemetry.get('voltage', 0):.2f}V | "
                  f"Speed: {telemetry.get('speed', 0):.1f}km/h | "
                  f"Batt: {telemetry.get('battery_percent', 0):.1f}% | "
                  f"Amp: {telemetry.get('current', 0):.2f}A")
            print(f"    User Dist: {telemetry.get('trip_distance', 0):.2f}km | "
                  f"Total Dist: {telemetry.get('total_distance', 0):.2f}km")
            
            # Debug distance bytes
            # Offsets: Trip=8 (4 bytes), Total=12 (4 bytes)
            # We need to account for the header if byte_data includes it?
            # The 'data' passed here is usually the payload.
            # Decoder expects the full frame including header.
            # Check byte_data length.
            if len(byte_data) >= 16:
                t_bytes = byte_data[8:12]
                tot_bytes = byte_data[12:16]
                print(f"    Debug Dist Bytes (8-11): {t_bytes.hex().upper()} -> {telemetry.get('trip_distance', 0):.2f}")
                print(f"    Debug Totl Bytes (12-15): {tot_bytes.hex().upper()} -> {telemetry.get('total_distance', 0):.2f}")

            if telemetry.get('is_charging'):
                 print(f"    STATUS: CHARGING | Mode: {telemetry.get('charge_mode')}")
            
            if self.snapshot:
                print("\nSnapshot complete. Exiting...")
                self.stop_event.set()
        else:
             # Partial packet or error
             print(f"[{timestamp}] PARTIAL/ERR: {hex_str}")

    async def connect_and_stream(self, device: BLEDevice):
        print(f"\n--- Connecting to {device.address} ---")
        
        try:
            async with BleakClient(device, timeout=20.0) as client:
                print("Connected!")
                print("Subscribing to notifications...")
                
                await client.start_notify(NOTIFY_UUID, self.notification_handler)
                
                print("\nStreaming Data... (Press Ctrl+C to stop)")
                while not self.stop_event.is_set():
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            print("\nStopping...")
        except BleakError as e:
            print(f"\nBLE Error: {e}")
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EUC Debugger")
    parser.add_argument("--raw", action="store_true", help="Show only raw hex data")
    parser.add_argument("--snapshot", action="store_true", help="Connect, get one packet, and exit")
    args = parser.parse_args()

    debugger = EucDebugger(raw_only=args.raw, snapshot=args.snapshot)
    try:
        asyncio.run(debugger.scan())
    except KeyboardInterrupt:
        print("\nAborted.")
