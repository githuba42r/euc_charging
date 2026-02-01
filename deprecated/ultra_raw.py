#!/usr/bin/env python3
"""
Ultra raw packet dump - shows EVERY packet with ALL bytes in both hex and decimal.
No filtering, no interpretation - just raw data.
"""

import asyncio
import sys
from datetime import datetime
from bleak import BleakClient, BleakScanner

MAC = "88:25:83:F3:5D:30"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Keep last 10 unique packets by first 4 bytes
last_packets = {}
packet_count = 0

def handle_packet(sender, data: bytearray):
    global last_packets, packet_count
    packet_count += 1
    
    data = bytes(data)
    packet_len = len(data)
    
    # Use first 4 bytes + length as key
    key = (data[0:4].hex(), packet_len)
    
    # Store with timestamp
    last_packets[key] = (data, datetime.now())
    
    # Every 20 packets, display all unique packet types
    if packet_count % 20 == 0:
        display()

def display():
    print("\033[2J\033[H")  # Clear screen
    print("=" * 120)
    print(f"ULTRA RAW MONITOR - All packet types (packet #{packet_count})")
    print("=" * 120)
    
    for key, (data, ts) in sorted(last_packets.items()):
        prefix, plen = key
        
        # Show hex dump
        hex_str = data.hex(' ')
        
        # Show word values (big-endian) for even-length packets
        if plen % 2 == 0:
            words_be = []
            words_le = []
            for i in range(0, plen, 2):
                be = (data[i] << 8) | data[i + 1]
                le = data[i] | (data[i + 1] << 8)
                words_be.append(f"{be:5d}")
                words_le.append(f"{le:5d}")
            
            print(f"\n[{plen:2d}B] {prefix}...")
            print(f"  HEX: {hex_str}")
            print(f"  BE:  {' '.join(words_be)}")
            print(f"  LE:  {' '.join(words_le)}")
        else:
            # Odd length - just show hex and individual bytes
            bytes_dec = [f"{b:3d}" for b in data]
            print(f"\n[{plen:2d}B] {prefix}...")
            print(f"  HEX: {hex_str}")
            print(f"  DEC: {' '.join(bytes_dec)}")
    
    print("\n" + "=" * 120)
    print("Vary charger current. Watch for ANY value that changes proportionally!")
    print("BE = Big Endian, LE = Little Endian word interpretation")


async def main():
    print("Scanning for device...")
    device = await BleakScanner.find_device_by_address(MAC, timeout=10.0)
    if not device:
        print(f"Device {MAC} not found!")
        return
    
    print(f"Connecting to {device.name}...")
    async with BleakClient(device) as client:
        print("Connected! Starting ultra raw monitor...")
        print("Collecting packets...")
        await client.start_notify(CHAR_UUID, handle_packet)
        
        try:
            while True:
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            await client.stop_notify(CHAR_UUID)


if __name__ == "__main__":
    asyncio.run(main())
