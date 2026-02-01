#!/usr/bin/env python3
"""
Leaperkim Sherman S (LK3336) - Protocol Decoder
Based on WheelLog/Wheellog.Android VeteranAdapter.java

The Sherman S uses the Veteran protocol with DC5A5C header.
Packets must be assembled across multiple BLE notifications.
"""

import struct
from dataclasses import dataclass, field
from typing import Any
from collections import deque
from enum import Enum


class UnpackerState(Enum):
    UNKNOWN = 0
    LENSEARCH = 1
    COLLECTING = 2
    DONE = 3


@dataclass
class ShermanSTelemetry:
    """Telemetry data from Sherman S."""
    voltage: float = 0.0          # Volts
    speed: float = 0.0            # km/h
    trip_distance: float = 0.0    # km
    total_distance: float = 0.0   # km
    phase_current: float = 0.0    # Amps (motor current - used as charging current)
    temperature: float = 0.0      # Celsius
    battery_percent: float = 0.0  # 0-100%
    is_charging: bool = False
    charge_mode: int = 0          # 0 = not charging, 1+ = charging
    pitch_angle: float = 0.0      # degrees
    version: str = ""
    pedals_mode: int = 0
    auto_off_sec: int = 0
    speed_alert: int = 0
    speed_tiltback: int = 0


class VeteranUnpacker:
    """
    Accumulates BLE packets to assemble complete Veteran protocol frames.

    Based on WheelLog VeteranAdapter.veteranUnpacker.

    Veteran protocol:
    - Header: DC 5A 5C (3 bytes)
    - Length byte after header
    - Data payload
    - Validation at specific offsets
    """

    def __init__(self):
        self.buffer = bytearray()
        self.old1 = 0
        self.old2 = 0
        self.length = 0
        self.state = UnpackerState.UNKNOWN
        self.using_crc = False

    def reset(self):
        """Reset unpacker state."""
        self.old1 = 0
        self.old2 = 0
        self.state = UnpackerState.UNKNOWN

    def get_buffer(self) -> bytes:
        """Return the accumulated buffer."""
        return bytes(self.buffer)

    def add_char(self, c: int) -> bool:
        """
        Add a byte to the unpacker.

        Returns True when a complete frame is ready.
        """
        if self.state == UnpackerState.COLLECTING:
            bsize = len(self.buffer)

            # Validation checks from WheelLog
            # Check specific byte positions for expected values
            if ((bsize == 22 and c != 0x00) or
                (bsize == 30 and c not in (0x00, 0x07)) or
                (bsize == 23 and (c & 0xFE) != 0x00)):
                self.state = UnpackerState.DONE
                self.reset()
                return False

            self.buffer.append(c)

            if bsize == self.length + 3:
                self.state = UnpackerState.DONE
                self.reset()

                # Check for CRC32 format (newer wheels)
                if self.length > 38 or self.using_crc:
                    # CRC32 validation would go here
                    # For now, accept without CRC check
                    pass

                return True  # Frame complete!

        elif self.state == UnpackerState.LENSEARCH:
            self.buffer.append(c)
            self.length = c & 0xFF
            self.state = UnpackerState.COLLECTING
            self.old2 = self.old1
            self.old1 = c

        else:  # UNKNOWN state
            # Looking for DC 5A 5C header sequence
            if c == 0x5C and self.old1 == 0x5A and self.old2 == 0xDC:
                # Found header!
                self.buffer = bytearray([0xDC, 0x5A, 0x5C])
                self.state = UnpackerState.LENSEARCH
            elif c == 0x5A and self.old1 == 0xDC:
                self.old2 = self.old1
            else:
                self.old2 = 0

            self.old1 = c

        return False

    def add_data(self, data: bytes) -> list[bytes]:
        """
        Add multiple bytes and return any complete frames.

        Args:
            data: Raw bytes from BLE notification

        Returns:
            List of complete frame buffers (may be empty or have multiple)
        """
        frames = []
        for byte in data:
            if self.add_char(byte):
                frames.append(self.get_buffer())
        return frames


class ShermanSDecoder:
    """
    Decoder for Leaperkim Sherman S (LK3336) BLE packets.

    Based on WheelLog VeteranAdapter.java decode() method.

    Protocol (Veteran format):
    - Bytes 0-2: DC 5A 5C header
    - Byte 3: Length
    - Bytes 4-5: Voltage (uint16 BE, raw value = centivolts)
    - Bytes 6-7: Speed (int16 BE, multiply by 10 for raw units)
    - Bytes 8-11: Trip distance (uint32 reverse BE)
    - Bytes 12-15: Total distance (uint32 reverse BE)
    - Bytes 16-17: Phase current (int16 BE, multiply by 10 = milliamps)
    - Bytes 18-19: Temperature (int16 BE, centi-degrees)
    - Bytes 20-21: Auto-off timer (seconds)
    - Bytes 22-23: Charge mode (0 = not charging)
    - Bytes 24-25: Speed alert threshold
    - Bytes 26-27: Speed tiltback threshold
    - Bytes 28-29: Version (encoded as major*1000 + minor*100 + patch)
    - Bytes 30-31: Pedals mode
    - Bytes 32-33: Pitch angle (int16 BE, centi-degrees)
    - Bytes 34-35: HW PWM

    Charging Current Packet (discovered from live capture):
    - Pattern: 00 00 00 00 00 00 [00/04] 00 XX XX FF FF FF FF FF 32 EE
    - Bytes 8-9: Charging current (uint16 BE, divide by 1245 for amps)
    """

    # Sherman S battery configuration
    # 20s pack (20 cells in series), 84V nominal, 100.8V max
    MIN_VOLTAGE = 72.0   # ~3.6V per cell minimum
    MAX_VOLTAGE = 100.8  # 4.2V per cell maximum (20s * 5.04V)
    CELLS = 20

    # NOTE: Charging current is NOT available in the BLE protocol
    # EUC World may use proprietary extensions not in WheelLog

    def __init__(self):
        self.unpacker = VeteranUnpacker()
        self.last_telemetry = ShermanSTelemetry()
        self.packet_count = 0
        self.error_count = 0
        self.mVer = 0  # Major firmware version
        self.recent_raw = deque(maxlen=10)

    def decode(self, data: bytes | bytearray) -> dict[str, Any] | None:
        """
        Decode BLE notification data.

        Data may be a fragment. The unpacker accumulates bytes until
        a complete frame is ready.

        Args:
            data: Raw bytes from BLE notification

        Returns:
            Dictionary with telemetry values when frame complete, else None
        """
        if not data:
            return None

        self.recent_raw.append(bytes(data))

        # Feed data to unpacker for telemetry frames
        frames = self.unpacker.add_data(data)

        # Process any complete frames
        for frame in frames:
            result = self._decode_frame(frame)
            if result:
                return result

        return None

    def _decode_frame(self, buff: bytes) -> dict[str, Any] | None:
        """
        Decode a complete assembled frame.

        Based on WheelLog VeteranAdapter.java decode().
        """
        if len(buff) < 36:
            self.error_count += 1
            return None

        try:
            # Voltage: bytes 4-5, divide by 100 for volts
            voltage = struct.unpack(">H", buff[4:6])[0]
            voltage_v = voltage / 100.0

            # Speed: bytes 6-7, signed, multiply by 10 for raw units
            speed = struct.unpack(">h", buff[6:8])[0] * 10
            speed_kmh = speed / 1000.0  # Convert to km/h (approximate)

            # Trip distance: bytes 8-11 (reversed big-endian int32)
            distance = self._int_from_bytes_rev_be(buff, 8)
            distance_km = distance / 1000.0

            # Total distance: bytes 12-15 (reversed big-endian int32)
            total_distance = self._int_from_bytes_rev_be(buff, 12)
            total_distance_km = total_distance / 1000.0

            # Phase current: bytes 16-17, signed, multiply by 10
            # This is motor current but represents charging current when stationary
            phase_current_raw = struct.unpack(">h", buff[16:18])[0] * 10
            phase_current_a = phase_current_raw / 1000.0  # Convert to amps

            # Temperature: bytes 18-19, signed, divide by 100
            temperature = struct.unpack(">h", buff[18:20])[0]
            temperature_c = temperature / 100.0

            # Auto-off timer: bytes 20-21
            auto_off_sec = struct.unpack(">H", buff[20:22])[0]

            # Charge mode: bytes 22-23 (0 = not charging)
            charge_mode = struct.unpack(">H", buff[22:24])[0]

            # Speed alert: bytes 24-25
            speed_alert = struct.unpack(">H", buff[24:26])[0] * 10

            # Speed tiltback: bytes 26-27
            speed_tiltback = struct.unpack(">H", buff[26:28])[0] * 10

            # Version: bytes 28-29 (encoded)
            ver = struct.unpack(">H", buff[28:30])[0]
            self.mVer = ver // 1000
            version = f"{ver // 1000:03d}.{(ver % 1000) // 100}.{ver % 100:02d}"

            # Pedals mode: bytes 30-31
            pedals_mode = struct.unpack(">H", buff[30:32])[0]

            # Pitch angle: bytes 32-33
            pitch_angle = struct.unpack(">h", buff[32:34])[0]
            pitch_angle_deg = pitch_angle / 100.0

            # Calculate battery percentage
            battery_percent = self._calculate_battery_percent(voltage_v)

            # Determine charging state
            is_charging = charge_mode > 0

            self.packet_count += 1

            # Update telemetry object
            self.last_telemetry.voltage = voltage_v
            self.last_telemetry.speed = speed_kmh
            self.last_telemetry.trip_distance = distance_km
            self.last_telemetry.total_distance = total_distance_km
            self.last_telemetry.phase_current = phase_current_a
            self.last_telemetry.temperature = temperature_c
            self.last_telemetry.battery_percent = battery_percent
            self.last_telemetry.is_charging = is_charging
            self.last_telemetry.charge_mode = charge_mode
            self.last_telemetry.version = version
            self.last_telemetry.pedals_mode = pedals_mode
            self.last_telemetry.pitch_angle = pitch_angle_deg
            self.last_telemetry.auto_off_sec = auto_off_sec

            return {
                "voltage": voltage_v,
                "speed": speed_kmh,
                "trip_distance": distance_km,
                "total_distance": total_distance_km,
                "current": phase_current_a,  # Charging current when stationary
                "temperature": temperature_c,
                "battery_percent": battery_percent,
                "is_charging": is_charging,
                "charge_mode": charge_mode,
                "version": version,
                "pedals_mode": pedals_mode,
                "pitch_angle": pitch_angle_deg,
                "auto_off_sec": auto_off_sec,
                "speed_alert": speed_alert,
                "speed_tiltback": speed_tiltback,
                "frame_type": "telemetry",
                "raw_frame": buff.hex(),
            }

        except (struct.error, IndexError) as e:
            self.error_count += 1
            return None

    def _int_from_bytes_rev_be(self, data: bytes, offset: int) -> int:
        """
        Read a 32-bit integer in "reversed big-endian" format.

        This is how WheelLog reads distance values from Veteran wheels.
        The bytes are arranged as: [high word big-endian][low word big-endian]
        """
        high = struct.unpack(">H", data[offset:offset+2])[0]
        low = struct.unpack(">H", data[offset+2:offset+4])[0]
        return (high << 16) | low

    def _calculate_battery_percent(self, voltage: float) -> float:
        """
        Calculate battery percentage from voltage.

        For Sherman S (mVer < 4):
        - Uses better percents algorithm from WheelLog
        """
        voltage_raw = int(voltage * 100)  # Convert back to raw format

        # Sherman S battery percentage (from WheelLog)
        # This is for 24s pack (100.8V max)
        if voltage_raw > 10020:  # 100.2V
            return 100.0
        elif voltage_raw > 8160:  # 81.6V
            return round((voltage_raw - 8070) / 19.5, 1)
        elif voltage_raw > 7935:  # 79.35V
            return round((voltage_raw - 7935) / 48.75, 1)
        else:
            return 0.0

    def get_status(self) -> dict:
        """Get current decoder status."""
        return {
            "packet_count": self.packet_count,
            "error_count": self.error_count,
            "firmware_version": self.mVer,
            "last_telemetry": self.last_telemetry,
        }


# Test with sample data
if __name__ == "__main__":
    # Test data from WheelLog VeteranAdapterTest.kt (Sherman S)
    # byteArray1 = "DC5A5C22266200000084000017A2000000000C38".hexToByteArray()
    # byteArray2 = "0B03000000C600E40BBD0003188B0000006F".hexToByteArray()

    test_data1 = bytes.fromhex("DC5A5C22266200000084000017A2000000000C38")
    test_data2 = bytes.fromhex("0B03000000C600E40BBD0003188B0000006F")

    decoder = ShermanSDecoder()

    print("Testing Sherman S decoder with WheelLog test data:")
    print("=" * 60)

    result1 = decoder.decode(test_data1)
    print(f"After packet 1: {result1}")

    result2 = decoder.decode(test_data2)
    print(f"After packet 2: {result2}")

    if result2:
        print("\nDecoded values:")
        print(f"  Voltage: {result2['voltage']:.2f}V")
        print(f"  Current: {result2['current']:.2f}A")
        print(f"  Temperature: {result2['temperature']:.1f}°C")
        print(f"  Battery: {result2['battery_percent']:.1f}%")
        print(f"  Charging: {result2['is_charging']}")
        print(f"  Version: {result2['version']}")
