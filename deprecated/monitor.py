#!/usr/bin/env python3
"""
Leaperkim Sherman S - Live Monitor
Displays voltage, current, and temperature in real-time.
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

from decoder import ShermanSDecoder

# Target device
TARGET_MAC = "88:25:83:F3:5D:30"

# Sherman S BLE UUIDs
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"


class LiveMonitor:
    """Real-time EUC monitor with clear display."""

    def __init__(self, address: str = TARGET_MAC):
        self.address = address
        self.decoder = ShermanSDecoder()
        self.running = False

        # Latest values
        self.voltage = 0.0
        self.phase_current = 0.0      # Motor current (0 when stationary)
        self.charging_current = 0.0    # Charging current from BMS
        self.battery = 0.0
        self.temperature = 0.0
        self.is_charging = False
        self.charge_mode = 0
        self.last_update = None
        self.packet_count = 0
        self.current_packet_count = 0

    def _notification_handler(self, characteristic, data: bytearray):
        """Handle incoming BLE notifications."""
        self.packet_count += 1

        # Decode the packet
        telemetry = self.decoder.decode(data)

        if telemetry:
            self.last_update = datetime.now()
            frame_type = telemetry.get('frame_type', '')

            if frame_type == 'charging_current':
                # Dedicated charging current packet
                self.charging_current = telemetry.get('charging_current', 0.0)
                self.current_packet_count += 1
            elif frame_type == 'telemetry':
                # Full telemetry frame
                if telemetry.get('voltage', 0) > 0:
                    self.voltage = telemetry['voltage']
                if 'current' in telemetry:
                    self.phase_current = telemetry['current']
                if 'charging_current' in telemetry:
                    self.charging_current = telemetry['charging_current']
                if telemetry.get('battery_percent', 0) > 0:
                    self.battery = telemetry['battery_percent']
                if 'temperature' in telemetry:
                    self.temperature = telemetry['temperature']
                if 'is_charging' in telemetry:
                    self.is_charging = telemetry['is_charging']
                if 'charge_mode' in telemetry:
                    self.charge_mode = telemetry['charge_mode']

    def display(self):
        """Display current values."""
        # Clear screen and move cursor to top
        print("\033[2J\033[H", end="")

        print("=" * 60)
        print("  SHERMAN S - LIVE MONITOR")
        print("=" * 60)
        print()

        # Charging indicator
        if self.charge_mode > 0 or self.charging_current > 0:
            status = "⚡ CHARGING"
        elif self.phase_current > 0:
            status = "🔋 RIDING"
        else:
            status = "⏸️  IDLE"

        print(f"  Status:          {status}")
        print()
        print(f"  Voltage:         {self.voltage:>8.2f} V")
        print(f"  Charging Current:{self.charging_current:>8.2f} A")
        print(f"  Phase Current:   {self.phase_current:>8.2f} A")
        print(f"  Battery:         {self.battery:>8.1f} %")
        print(f"  Temperature:     {self.temperature:>8.1f} °C")
        print()

        # Power calculation (using charging current when charging)
        current_for_power = self.charging_current if self.charging_current > 0 else abs(self.phase_current)
        power = self.voltage * current_for_power
        print(f"  Power:           {power:>8.1f} W")
        print()

        # Update time
        if self.last_update:
            print(f"  Last update:     {self.last_update.strftime('%H:%M:%S')}")
        print(f"  Packets:         {self.packet_count} total, {self.current_packet_count} current")
        print()
        print("=" * 60)
        print("  Press Ctrl+C to stop")
        print("=" * 60)

    async def run(self, refresh_rate: float = 1.0):
        """Main run loop."""
        self.running = True

        print("Scanning for Sherman S...")
        device = await BleakScanner.find_device_by_address(
            self.address, timeout=30.0
        )

        if not device:
            print(f"Device not found: {self.address}")
            return

        print(f"Found: {device.name} ({device.address})")
        print("Connecting...")

        async with BleakClient(self.address) as client:
            print("Connected! Subscribing to notifications...")

            # Subscribe to notifications
            await client.start_notify(NOTIFY_UUID, self._notification_handler)

            print("Subscribed! Starting monitor...\n")
            await asyncio.sleep(1)  # Wait for initial data

            try:
                while self.running:
                    self.display()
                    await asyncio.sleep(refresh_rate)
            except asyncio.CancelledError:
                pass
            finally:
                await client.stop_notify(NOTIFY_UUID)

        print("\nDisconnected.")

    def stop(self):
        """Stop the monitor."""
        self.running = False


async def main():
    """Main entry point."""
    monitor = LiveMonitor()

    try:
        await monitor.run(refresh_rate=0.5)
    except KeyboardInterrupt:
        monitor.stop()
        print("\n\nMonitor stopped.")


if __name__ == "__main__":
    asyncio.run(main())
