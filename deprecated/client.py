#!/usr/bin/env python3
"""
Leaperkim Sherman S - Bluetooth LE Client
Connects to the EUC and captures telemetry data.
"""

import asyncio
import struct
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from decoder import ShermanSDecoder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Target device configuration
TARGET_MAC = "88:25:83:F3:5D:30"
TARGET_NAMES = ["LK3336", "Sherman S", "Veteran", "Sherman"]

# Sherman S BLE UUIDs (discovered from device)
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # Same as notify on this device

# Log file
LOG_FILE = Path(__file__).parent / "battery_data.log"


class ShermanSClient:
    """BLE client for Leaperkim Sherman S EUC."""

    def __init__(self, address: str = TARGET_MAC):
        self.address = address
        self.client: BleakClient | None = None
        self.decoder = ShermanSDecoder()
        self.running = False
        self._log_file = None
        self._callbacks: list[Callable] = []

    def add_callback(self, callback: Callable):
        """Add a callback for telemetry updates."""
        self._callbacks.append(callback)

    async def find_device(self, timeout: float = 30.0):
        """Scan for the target device."""
        logger.info(f"Scanning for device {self.address}...")

        device = await BleakScanner.find_device_by_address(
            self.address, timeout=timeout
        )

        if not device:
            # Try finding by name
            devices = await BleakScanner.discover(timeout=timeout)
            for d in devices:
                name = d.name or ""
                if any(n in name for n in TARGET_NAMES):
                    device = d
                    break

        if device:
            logger.info(f"✓ Found device: {device.name} ({device.address})")
        else:
            logger.warning(f"✗ Device not found: {self.address}")

        return device

    def _notification_handler(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ):
        """Handle incoming BLE notifications."""
        timestamp = datetime.now().isoformat()

        # Log raw data
        hex_data = data.hex()
        log_line = f"{timestamp} | {hex_data}\n"

        if self._log_file:
            self._log_file.write(log_line)
            self._log_file.flush()

        # Try to decode the packet
        telemetry = self.decoder.decode(data)

        if telemetry:
            logger.info(
                f"Voltage: {telemetry.get('voltage', 0):.2f}V | "
                f"Current: {telemetry.get('current', 0):.2f}A | "
                f"Battery: {telemetry.get('battery_percent', 0):.1f}% | "
                f"Charging: {telemetry.get('is_charging', False)}"
            )

            # Call registered callbacks
            for callback in self._callbacks:
                try:
                    callback(telemetry)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
        else:
            # Log raw data if decoding fails
            logger.debug(f"Raw data ({len(data)} bytes): {hex_data}")

    async def connect(self):
        """Connect to the device."""
        logger.info(f"Connecting to {self.address}...")

        self.client = BleakClient(self.address)
        await self.client.connect()

        if not self.client.is_connected:
            raise ConnectionError(f"Failed to connect to {self.address}")

        logger.info("✓ Connected!")
        return True

    async def subscribe(self):
        """Subscribe to telemetry notifications."""
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected to device")

        # Find the notify characteristic
        notify_char = None
        for service in self.client.services:
            for char in service.characteristics:
                if "ffe1" in str(char.uuid).lower():
                    notify_char = char
                    break
                if "notify" in char.properties:
                    # Fallback to any notify characteristic
                    if not notify_char:
                        notify_char = char

        if not notify_char:
            raise RuntimeError("No notify characteristic found")

        logger.info(f"Subscribing to notifications on {notify_char.uuid}...")

        await self.client.start_notify(
            notify_char.uuid, self._notification_handler
        )

        logger.info("✓ Subscribed to notifications")
        return notify_char.uuid

    async def send_command(self, command: bytes):
        """Send a command to the device."""
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected to device")

        # Find the write characteristic
        write_char = None
        for service in self.client.services:
            for char in service.characteristics:
                if "ffe1" in str(char.uuid).lower():
                    write_char = char
                    break
                if "write" in char.properties:
                    if not write_char:
                        write_char = char

        if not write_char:
            logger.warning("No write characteristic found")
            return False

        await self.client.write_gatt_char(write_char.uuid, command)
        logger.debug(f"Sent command: {command.hex()}")
        return True

    async def disconnect(self):
        """Disconnect from the device."""
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            logger.info("✓ Disconnected")

    async def run(self, duration: float | None = None):
        """
        Main run loop - connect, subscribe, and capture data.

        Args:
            duration: How long to run in seconds. None = run forever.
        """
        self.running = True

        # Open log file
        self._log_file = open(LOG_FILE, "a")
        logger.info(f"Logging data to: {LOG_FILE}")

        try:
            # Find device first
            device = await self.find_device()
            if not device:
                return

            # Connect
            await self.connect()

            # Subscribe to notifications
            await self.subscribe()

            # Optionally send a poll command to request data
            # await self.send_command(bytes([0x5A, 0x5A]))

            logger.info("\nListening for data... (Ctrl+C to stop)\n")

            # Run until stopped or duration elapsed
            start_time = asyncio.get_event_loop().time()
            while self.running:
                await asyncio.sleep(0.1)
                if duration:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= duration:
                        break

        except asyncio.CancelledError:
            logger.info("Cancelled")
        except Exception as e:
            logger.error(f"Error: {e}")
            raise
        finally:
            await self.disconnect()
            if self._log_file:
                self._log_file.close()

    def stop(self):
        """Stop the run loop."""
        self.running = False


async def main():
    """Main entry point."""
    client = ShermanSClient()

    # Add a simple callback to print data
    def print_telemetry(data):
        print(f"  → Temperature: {data.get('temperature', 'N/A')}°C")

    client.add_callback(print_telemetry)

    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("\nStopping...")
        client.stop()


if __name__ == "__main__":
    asyncio.run(main())
