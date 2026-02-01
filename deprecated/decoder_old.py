#!/usr/bin/env python3
"""
Leaperkim Sherman S (LK3336) - Protocol Decoder
Decodes telemetry data from actual captured BLE packets.

This is based on live reverse engineering of the Sherman S protocol,
which differs from older Veteran/Sherman models.
"""

import struct
from dataclasses import dataclass, field
from typing import Any
from collections import deque


@dataclass
class ShermanSTelemetry:
    """Telemetry data from Sherman S."""
    voltage: float = 0.0          # Volts
    speed: float = 0.0            # km/h
    trip_distance: float = 0.0    # km
    current: float = 0.0          # Amps (positive = charging)
    temperature: float = 0.0      # Celsius
    total_distance: float = 0.0   # km
    battery_percent: float = 0.0  # 0-100%
    is_charging: bool = False
    mode: int = 0
    raw_data: bytes = field(default_factory=bytes)


class ShermanSDecoder:
    """
    Decoder for Leaperkim Sherman S (LK3336) BLE packets.

    Based on actual captured data from the device, the protocol uses:
    - Service UUID: ffe0
    - Characteristic UUID: ffe1 (read/write/notify)

    Packet format (discovered from live capture):
    The device sends continuous data that may span multiple 20-byte BLE frames.

    Primary telemetry frame (DC 5A header):
    - Bytes 0-1: 0xDC 0x5A (header)
    - Bytes 2-3: Unknown (possibly frame type/counter)
    - Bytes 4-5: Voltage (uint16 BE, /100 for volts)
    - Bytes 6-7: Speed? (uint16 BE)
    - Bytes 8-9: Unknown
    - Bytes 10-11: Current? (int16 BE)
    - ...

    Secondary BMS frame (0B xx header):
    - Contains cell voltages and other BMS data
    """

    # Sherman S battery configuration (100.8V system, 24s)
    # Based on seeing 91.29V during charging
    MIN_VOLTAGE = 72.0   # ~3.0V per cell for 24s
    MAX_VOLTAGE = 100.8  # 4.2V per cell for 24s
    NOMINAL_VOLTAGE = 100.8

    # Known packet headers
    HEADER_TELEMETRY = bytes([0xDC, 0x5A])
    HEADER_BMS = 0x0B

    def __init__(self):
        self.last_telemetry = ShermanSTelemetry()
        self.packet_count = 0
        self.error_count = 0
        self.frame_buffer = bytearray()
        self.recent_packets = deque(maxlen=10)

    def decode(self, data: bytes | bytearray) -> dict[str, Any] | None:
        """
        Decode a BLE packet into telemetry data.

        Args:
            data: Raw bytes from BLE notification

        Returns:
            Dictionary with telemetry values, or None if not a telemetry packet
        """
        if not data or len(data) < 2:
            return None

        self.recent_packets.append(bytes(data))

        # Check for DC5A telemetry header
        if data[0] == 0xDC and data[1] == 0x5A:
            return self._decode_telemetry_frame(data)

        # Check for BMS data header (0x0B followed by cell data)
        if data[0] == 0x0B and len(data) >= 20:
            return self._decode_bms_frame(data)

        # Unknown packet type - log for analysis
        self.error_count += 1
        return None

    def _decode_telemetry_frame(self, data: bytes) -> dict[str, Any] | None:
        """Decode primary telemetry frame with DC5A header."""
        if len(data) < 20:
            return None

        try:
            # Bytes 4-5: Voltage (confirmed from capture: 0x23A9 = 91.29V)
            voltage_raw = struct.unpack(">H", data[4:6])[0]
            voltage = voltage_raw / 100.0

            # Bytes 6-7: Could be speed (need more data while riding)
            speed_raw = struct.unpack(">h", data[6:8])[0]
            speed = speed_raw / 100.0  # Tentative

            # Bytes 8-9: ED4A - possibly related to distance or other data
            # Need more analysis

            # Bytes 10-11: Could be current
            current_raw = struct.unpack(">h", data[10:12])[0]
            current = current_raw / 100.0

            # Bytes 12-13: Temperature or other data
            temp_raw = struct.unpack(">H", data[12:14])[0]
            # The value 0xA694 = 42644 is too high for temp/100
            # Maybe different scale or meaning
            temperature = temp_raw / 340.0 + 36.53  # MPU6050-style?
            if temperature > 100 or temperature < -40:
                temperature = 25.0  # Default if out of range

            # Bytes 14-15: 0x01CA = 458 - could be power or other
            power_raw = struct.unpack(">H", data[14:16])[0]

            # Bytes 18-19: 0x0E40 = 3648 - mode/status/counter?
            status = struct.unpack(">H", data[18:20])[0]

            # Calculate battery percentage from voltage
            battery_percent = self._calculate_battery_percent(voltage)

            # Determine charging state
            # During charging, current should be positive or voltage should be high
            is_charging = voltage > 90.0  # Simplified - charging if voltage > 90V

            self.packet_count += 1

            result = {
                "voltage": voltage,
                "speed": speed,
                "current": current,
                "temperature": temperature,
                "battery_percent": battery_percent,
                "is_charging": is_charging,
                "power": power_raw,
                "status": status,
                "raw_data": bytes(data[:20]),
                "frame_type": "telemetry",
            }

            # Update last known telemetry
            self.last_telemetry.voltage = voltage
            self.last_telemetry.battery_percent = battery_percent
            self.last_telemetry.is_charging = is_charging

            return result

        except struct.error:
            self.error_count += 1
            return None

    def _decode_bms_frame(self, data: bytes) -> dict[str, Any] | None:
        """
        Decode BMS data frame.

        These frames contain current and cell voltage data.
        Format: 0B AC 00 00 02 26 02 4E 0B C7 00 02 1B 69 00 00 00 6F 00 00
        
        Bytes 0-1: Current in raw units, divide by 1245 for amps
                   0x0BAC (2988) / 1245 = 2.40A charging
                   Values decrease as charge tapers: 0BAC, 0BAB, 0BAA...
        
        Sign convention: negative = charging (EUC World style)
        """
        if len(data) < 20:
            return None

        try:
            # Bytes 0-1: Current in raw units (big-endian)
            # Divide by 1245 to get amps, negate for EUC World convention
            current_raw = struct.unpack(">H", data[0:2])[0]
            current = -(current_raw / 1245.0)

            # Byte 1 value for reference
            cell_group = data[1]

            # Try to extract cell voltages
            # Looking at: 0bab00000226024e0bc700021b690000006f0000
            # Bytes 4-5: 0226 = 550 -> 2.26V (too low for LiPo)
            # Bytes 6-7: 024e = 590 -> 5.90V (too high)
            # Maybe: 0x0226 = 550 + 3000 offset? = 3.55V

            # Alternative: these might be cell voltages in mV with offset
            # 0xBC7 = 3015 -> 3.015V per cell
            # This seems more reasonable

            cell_voltages = []
            # Try reading potential cell voltage positions
            for i in range(4, min(len(data) - 1, 18), 2):
                val = struct.unpack(">H", data[i:i+2])[0]
                # If value is in range 2500-4500, treat as cell mV
                if 2500 <= val <= 4500:
                    cell_voltages.append(val / 1000.0)

            self.packet_count += 1

            # Update last telemetry with current from BMS
            self.last_telemetry.current = current
            self.last_telemetry.is_charging = current < 0  # Negative = charging in our convention

            return {
                "frame_type": "bms",
                "current": current,
                "cell_group": cell_group,
                "cell_voltages": cell_voltages,
                "raw_data": bytes(data[:20]),
            }

        except struct.error:
            self.error_count += 1
            return None

    def _calculate_battery_percent(self, voltage: float) -> float:
        """Calculate battery percentage from voltage."""
        if voltage <= self.MIN_VOLTAGE:
            return 0.0
        if voltage >= self.MAX_VOLTAGE:
            return 100.0

        percent = ((voltage - self.MIN_VOLTAGE) /
                   (self.MAX_VOLTAGE - self.MIN_VOLTAGE)) * 100.0
        return round(percent, 1)

    def decode_hex(self, hex_string: str) -> dict[str, Any] | None:
        """Decode a hex string packet."""
        try:
            data = bytes.fromhex(hex_string.strip())
            return self.decode(data)
        except ValueError:
            return None

    def get_last_telemetry(self) -> ShermanSTelemetry:
        """Get the last decoded telemetry."""
        return self.last_telemetry

    @property
    def stats(self) -> dict[str, int]:
        """Return decoding statistics."""
        return {
            "packets_decoded": self.packet_count,
            "errors": self.error_count,
        }


def test_decoder():
    """Test the decoder with actual captured data."""
    decoder = ShermanSDecoder()

    # Actual captured packets from Sherman S
    test_packets = [
        # DC5A telemetry packet
        "dc5a5c3523a90000ed4a0000a69401ca00000e40",
        "dc5a5c2f23a90000ed4a0000a69401ca00000e41",
        "dc5a5c4523a90000ed4a0000a69401ca00000e42",
        # BMS packets
        "0bac00000226024e0bc700021b690000006f0000",
        "0bab00000226024e0bc700021b6d0000006f0000",
        "0ba900000226024e0bc700021b6b0000006f0000",
    ]

    print("Sherman S (LK3336) Decoder Test")
    print("=" * 60)

    for hex_data in test_packets:
        print(f"\nPacket: {hex_data}")

        result = decoder.decode_hex(hex_data)
        if result:
            frame_type = result.get("frame_type", "unknown")
            print(f"  Frame type: {frame_type}")

            if frame_type == "telemetry":
                print(f"  Voltage: {result['voltage']:.2f}V")
                print(f"  Battery: {result['battery_percent']:.1f}%")
            elif frame_type == "bms":
                print(f"  Current: {result['current']:.2f}A (charging)")
                print(f"  Cell group: 0x{result['cell_group']:02X}")
                if result.get("cell_voltages"):
                    print(f"  Cell voltages: {result['cell_voltages']}")
        else:
            print("  Failed to decode")

    # Show combined telemetry
    telem = decoder.get_last_telemetry()
    print(f"\n--- Combined Telemetry ---")
    print(f"  Voltage: {telem.voltage:.2f}V")
    print(f"  Battery: {telem.battery_percent:.1f}%")
    print(f"  Current: {telem.current:.2f}A")
    print(f"  Charging: {telem.is_charging}")

    print(f"\n{decoder.stats}")


def analyze_log_file(log_path: str):
    """Analyze captured log file."""
    decoder = ShermanSDecoder()
    voltages = []
    currents = []

    with open(log_path) as f:
        for line in f:
            if " | " in line:
                parts = line.strip().split(" | ")
                if len(parts) == 2:
                    _, hex_data = parts
                    result = decoder.decode_hex(hex_data)
                    if result:
                        if result.get("frame_type") == "telemetry":
                            voltages.append(result["voltage"])
                        elif result.get("frame_type") == "bms":
                            currents.append(result["current"])

    print("\nLog File Analysis:")
    print("=" * 50)
    
    if voltages:
        print(f"\nVoltage Statistics:")
        print(f"  Min: {min(voltages):.2f}V")
        print(f"  Max: {max(voltages):.2f}V")
        print(f"  Avg: {sum(voltages)/len(voltages):.2f}V")
        print(f"  Samples: {len(voltages)}")

    if currents:
        print(f"\nCurrent Statistics (charging):")
        print(f"  Min: {min(currents):.2f}A")
        print(f"  Max: {max(currents):.2f}A")
        print(f"  Avg: {sum(currents)/len(currents):.2f}A")
        print(f"  Samples: {len(currents)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--log":
        log_file = sys.argv[2] if len(sys.argv) > 2 else "/home/philg/working/euc-dump/battery_data.log"
        analyze_log_file(log_file)
    else:
        test_decoder()
