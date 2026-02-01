#!/usr/bin/env python3
"""
Leaperkim Sherman S - Bluetooth LE Discovery
Discovers the EUC device and enumerates all services/characteristics.
"""

import asyncio
from bleak import BleakScanner, BleakClient

# Target device configuration
TARGET_MAC = "88:25:83:F3:5D:30"
TARGET_NAMES = ["LK3336", "Sherman S", "Veteran", "Sherman"]

# Known UUIDs (discovered from device)
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"


def matches_target(address: str, name: str | None) -> bool:
    """Check if device matches our target EUC."""
    # Match by MAC address (case-insensitive)
    if address.lower().replace(":", "") == TARGET_MAC.lower().replace(":", ""):
        return True
    # Match by device name
    if name and any(n in name for n in TARGET_NAMES):
        return True
    return False


async def discover_device():
    """Scan for and discover the EUC device."""
    print("Leaperkim Sherman S - Bluetooth LE Discovery")
    print("=" * 45)
    print(f"\nTarget Device: {TARGET_MAC}")
    print(f"Also matching names: {', '.join(TARGET_NAMES)}")
    print("\nScanning for devices...\n")

    target_device = None

    def detection_callback(device, advertisement_data):
        nonlocal target_device
        if target_device:
            return  # Already found target
        name = device.name or advertisement_data.local_name or "(unknown)"
        print(f"Found: {name} ({device.address}) RSSI: {advertisement_data.rssi}")

        if matches_target(device.address, name):
            print(f"\n✓ TARGET DEVICE FOUND!")
            print(f"  MAC Address: {device.address}")
            print(f"  Device Name: {name}")
            print(f"  RSSI: {advertisement_data.rssi} dBm")
            if advertisement_data.service_uuids:
                print(f"  Service UUIDs: {advertisement_data.service_uuids}")
            target_device = device

    scanner = BleakScanner(detection_callback=detection_callback)

    # Scan for up to 30 seconds
    await scanner.start()
    for _ in range(30):
        if target_device:
            break
        await asyncio.sleep(1)
    await scanner.stop()

    if not target_device:
        print("\n⚠ Target device not found after 30 seconds.")
        print("\nTroubleshooting:")
        print(f"  1. Make sure {TARGET_MAC} is powered on")
        print("  2. Make sure it's in Bluetooth range (< 10m)")
        print("  3. Try manually: bluetoothctl -> scan on")
        return None

    return target_device


async def enumerate_services(device):
    """Connect to device and enumerate all services/characteristics."""
    print(f"\nConnecting to {device.address}...")

    async with BleakClient(device.address) as client:
        print(f"✓ Connected: {client.is_connected}\n")

        print("Discovering services and characteristics...\n")
        print("=" * 60)

        for service in client.services:
            print(f"\nService: {service.uuid}")
            if service.description:
                print(f"  Description: {service.description}")

            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  ├─ Characteristic: {char.uuid}")
                print(f"  │    Properties: {props}")
                if char.description:
                    print(f"  │    Description: {char.description}")

                # Try to read value if readable
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        hex_val = value.hex() if value else "empty"
                        print(f"  │    Value (hex): {hex_val}")
                    except Exception as e:
                        print(f"  │    Read error: {e}")

                # List descriptors
                for desc in char.descriptors:
                    print(f"  │  └─ Descriptor: {desc.uuid}")

        print("\n" + "=" * 60)
        print("✓ Service discovery complete!")

        # Check for expected Sherman S characteristics
        print("\n--- Sherman S Protocol Check ---")
        has_ffe0 = any("ffe0" in str(s.uuid).lower() for s in client.services)
        print(f"Service ffe0: {'✓ Found' if has_ffe0 else '✗ Not found'}")

        for service in client.services:
            for char in service.characteristics:
                if "ffe1" in str(char.uuid).lower():
                    print(f"Data char ffe1: ✓ Found ({char.uuid})")
                    print(f"  Properties: {', '.join(char.properties)}")

    print("\n✓ Disconnected")


async def main():
    """Main entry point."""
    device = await discover_device()
    if device:
        await enumerate_services(device)


if __name__ == "__main__":
    asyncio.run(main())
