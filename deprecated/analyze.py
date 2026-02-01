#!/usr/bin/env python3
"""
Analyze captured BLE data from Sherman S to decode the protocol.
"""

import struct
from pathlib import Path


def analyze_packets(log_file: str):
    """Analyze captured packets from the log file."""
    log_path = Path(log_file)
    if not log_path.exists():
        print(f"Log file not found: {log_file}")
        return

    packets = []
    with open(log_path) as f:
        for line in f:
            if " | " in line:
                parts = line.strip().split(" | ")
                if len(parts) == 2:
                    timestamp, hex_data = parts
                    packets.append((timestamp, hex_data))

    print(f"Loaded {len(packets)} packets\n")
    print("=" * 70)

    # Group similar packet patterns
    patterns = {}
    for ts, hex_data in packets:
        # Look at first 4 bytes as pattern identifier
        prefix = hex_data[:8] if len(hex_data) >= 8 else hex_data
        if prefix not in patterns:
            patterns[prefix] = []
        patterns[prefix].append((ts, hex_data))

    print(f"Found {len(patterns)} unique packet prefixes:\n")

    for prefix, packet_list in sorted(patterns.items(), key=lambda x: -len(x[1])):
        print(f"Prefix {prefix}: {len(packet_list)} packets")
        # Show first packet
        hex_data = packet_list[0][1]
        data = bytes.fromhex(hex_data)
        print(f"  Sample: {hex_data}")
        print(f"  Length: {len(data)} bytes")

        # Try different decodings
        if len(data) >= 20:
            # Standard Veteran format (55 AA header)
            if data[0] == 0x55 and data[1] == 0xAA:
                print("  → Standard Veteran 0x55AA header!")
                decode_veteran_packet(data)

            # Try dc5a format
            elif data[0] == 0xDC and data[1] == 0x5A:
                print("  → DC5A header detected")
                decode_dc5a_packet(data)

            # Alternative format - try as raw data
            else:
                print("  → Unknown format, trying raw decode...")
                try_raw_decode(data)

        print()


def decode_veteran_packet(data: bytes):
    """Decode standard Veteran packet format."""
    voltage = struct.unpack(">H", data[2:4])[0] / 100.0
    speed = struct.unpack(">h", data[4:6])[0] / 100.0 * 3.6
    trip = struct.unpack(">I", data[6:10])[0] / 1000.0
    current = struct.unpack(">h", data[10:12])[0] / 100.0
    temp = struct.unpack(">H", data[12:14])[0] / 10.0

    print(f"    Voltage: {voltage:.2f}V")
    print(f"    Speed: {speed:.2f} km/h")
    print(f"    Trip: {trip:.3f} km")
    print(f"    Current: {current:.2f}A")
    print(f"    Temperature: {temp:.1f}°C")


def decode_dc5a_packet(data: bytes):
    """Try to decode DC5A format packet."""
    # Looks like it might be a framing/escape sequence
    # Let's analyze the structure

    # DC 5A might be an escape sequence or inverted header
    # 5A DC could be the actual data

    # Try different interpretations
    print("    Byte analysis:")

    # Bytes 2-3 (after DC 5A) - might be part of header or data
    b2_3 = struct.unpack(">H", data[2:4])[0]
    print(f"    Bytes 2-3: 0x{b2_3:04X} = {b2_3}")

    # Bytes 4-5
    b4_5 = struct.unpack(">H", data[4:6])[0]
    print(f"    Bytes 4-5: 0x{b4_5:04X} = {b4_5}")

    # Let's try assuming DC5A is header and data starts at byte 2
    # Voltage might be at offset 2-3, scaled differently
    possible_voltage = b2_3 / 100.0
    print(f"    If voltage at 2-3 (/100): {possible_voltage:.2f}V")

    # Try bytes 4-5 as voltage
    possible_voltage2 = struct.unpack(">H", data[4:6])[0] / 100.0
    print(f"    If voltage at 4-5 (/100): {possible_voltage2:.2f}V")

    # The data looks like it might be split across multiple 20-byte frames
    # Let's look at the whole structure
    print(f"    Full data: {data.hex()}")


def try_raw_decode(data: bytes):
    """Try raw interpretation without known header."""
    print(f"    Bytes 0-1: 0x{data[0]:02X} 0x{data[1]:02X}")

    # Try to find meaningful voltage values
    # Sherman S is 84V nominal (100.8V max)
    # Look for values around 8000-10080 (divide by 100)

    for i in range(0, min(len(data) - 1, 18), 2):
        val_be = struct.unpack(">H", data[i : i + 2])[0]
        val_le = struct.unpack("<H", data[i : i + 2])[0]

        # Check if it's in voltage range (67-101V = 6700-10100)
        if 6700 <= val_be <= 10100:
            print(f"    Bytes {i}-{i+1}: {val_be/100:.2f}V (big-endian)")
        if 6700 <= val_le <= 10100:
            print(f"    Bytes {i}-{i+1}: {val_le/100:.2f}V (little-endian)")


def analyze_sample_packet():
    """Analyze a specific packet in detail."""
    # Sample from log: dc5a5c3523a90000ed4a0000a69401ca00000e40
    sample = bytes.fromhex("dc5a5c3523a90000ed4a0000a69401ca00000e40")

    print("\n" + "=" * 70)
    print("Detailed analysis of sample packet")
    print("=" * 70)
    print(f"Raw hex: {sample.hex()}")
    print(f"Length: {len(sample)} bytes\n")

    print("Byte-by-byte analysis:")
    for i in range(len(sample)):
        print(f"  [{i:2d}] 0x{sample[i]:02X} = {sample[i]:3d} = '{chr(sample[i]) if 32 <= sample[i] < 127 else '.'}'")

    print("\n2-byte value analysis (big-endian):")
    for i in range(0, len(sample) - 1, 2):
        val = struct.unpack(">H", sample[i : i + 2])[0]
        signed_val = struct.unpack(">h", sample[i : i + 2])[0]
        print(f"  [{i:2d}-{i+1:2d}] 0x{val:04X} = {val:5d} (signed: {signed_val:6d})")

    print("\n4-byte value analysis (big-endian):")
    for i in range(0, len(sample) - 3, 4):
        val = struct.unpack(">I", sample[i : i + 4])[0]
        print(f"  [{i:2d}-{i+3:2d}] 0x{val:08X} = {val}")

    # The bytes 4-5 (23a9 = 9129) could be voltage if scaled differently
    # 9129 / 100 = 91.29V - that's reasonable for Sherman S charging!
    print("\nPossible interpretations:")
    print(f"  Bytes 4-5 as voltage: {struct.unpack('>H', sample[4:6])[0] / 100:.2f}V")
    print(f"  Bytes 10-11 as current: {struct.unpack('>h', sample[10:12])[0] / 100:.2f}A")
    print(f"  Bytes 12-13 as temp: {struct.unpack('>H', sample[12:14])[0] / 10:.1f}°C")


if __name__ == "__main__":
    import sys

    log_file = sys.argv[1] if len(sys.argv) > 1 else "/home/philg/working/euc-dump/battery_data.log"

    analyze_packets(log_file)
    analyze_sample_packet()
