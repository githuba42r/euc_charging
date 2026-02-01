#!/usr/bin/env python3
"""
Raw packet value monitor - shows all byte pair values to help identify current location.
Vary the charger current and watch which values change proportionally.
"""

import asyncio
import os
from bleak import BleakClient, BleakScanner

MAC = "88:25:83:F3:5D:30"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"


class RawMonitor:
    def __init__(self):
        self.last_dc5a = None
        self.last_0e10 = None
        self.last_00_type_00 = None
        self.last_00_type_04 = None
        self.last_13byte = None
        
    def handle_packet(self, sender, data: bytearray):
        data = bytes(data)
        
        # DC5A telemetry packet
        if len(data) >= 20 and data[0:3] == bytes([0xdc, 0x5a, 0x5c]):
            self.last_dc5a = data
            
        # 0E10 packet
        elif len(data) >= 20 and data[0:2] == bytes([0x0e, 0x10]):
            self.last_0e10 = data
            
        # 00 00 type 00 packet (20 bytes)
        elif len(data) == 20 and data[0:7] == bytes([0, 0, 0, 0, 0, 0, 0]):
            self.last_00_type_00 = data
            
        # 00 00 type 04 packet (20 bytes)
        elif len(data) == 20 and data[0:6] == bytes([0, 0, 0, 0, 0, 0]) and data[6] == 4:
            self.last_00_type_04 = data
            
        # 13-byte continuation packet
        elif len(data) == 13:
            self.last_13byte = data
        
        self.display()
    
    def display(self):
        os.system('clear')
        print("=" * 100)
        print("RAW PACKET MONITOR - Watch for values that change with charger current")
        print("=" * 100)
        
        # DC5A packet
        if self.last_dc5a:
            p = self.last_dc5a
            voltage = ((p[4] << 8) | p[5]) / 100
            phase = ((p[16] << 8) | p[17]) / 100
            temp = ((p[18] << 8) | p[19]) / 100
            print(f"\nDC5A: V={voltage:.2f}V  phase={phase:.2f}A  T={temp:.1f}°C")
        
        # 0E10 packet - show all bytes
        if self.last_0e10:
            p = self.last_0e10
            vals = []
            for i in range(2, 18, 2):
                val = (p[i] << 8) | p[i + 1]
                vals.append(f"{val:5d}")
            print(f"\n0E10: {' '.join(vals)}")
        
        # 00 00 type 00 packet
        if self.last_00_type_00:
            p = self.last_00_type_00
            vals = []
            for i in range(7, 19, 2):
                val = (p[i] << 8) | p[i + 1]
                vals.append(f"[{i}]={val:5d}")
            print(f"\n00 type 00: {' '.join(vals)}")
        
        # 00 00 type 04 packet
        if self.last_00_type_04:
            p = self.last_00_type_04
            vals = []
            for i in range(7, 19, 2):
                val = (p[i] << 8) | p[i + 1]
                vals.append(f"[{i}]={val:5d}")
            print(f"\n00 type 04: {' '.join(vals)}")
        
        # 13-byte packet
        if self.last_13byte:
            p = self.last_13byte
            vals = []
            for i in range(0, 12, 2):
                val = (p[i] << 8) | p[i + 1]
                vals.append(f"[{i}]={val:5d}")
            print(f"\n13-byte:   {' '.join(vals)}")
        
        print("\n" + "=" * 100)
        print("Vary charger current and watch which value changes proportionally!")


async def main():
    monitor = RawMonitor()
    
    print("Scanning for device...")
    device = await BleakScanner.find_device_by_address(MAC, timeout=10.0)
    if not device:
        print(f"Device {MAC} not found!")
        return
    
    print(f"Connecting to {device.name}...")
    async with BleakClient(device) as client:
        print("Connected! Starting raw monitor...")
        await client.start_notify(CHAR_UUID, monitor.handle_packet)
        
        try:
            while True:
                await asyncio.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            await client.stop_notify(CHAR_UUID)


if __name__ == "__main__":
    asyncio.run(main())