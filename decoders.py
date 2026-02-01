"""Protocol decoders for EUC devices.

Supports automatic protocol detection for all major EUC brands:
- KingSong
- Gotway/Begode
- Veteran/Leaperkim
- InMotion (V1 and V2 protocols)
- Ninebot (Standard and Z series)
"""

from __future__ import annotations

import logging
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .const import CELL_CONFIG, WheelBrand

_LOGGER = logging.getLogger(__name__)


@dataclass
class EucTelemetry:
    """Common telemetry data for all EUCs."""
    voltage: float = 0.0          # Volts
    speed: float = 0.0            # km/h
    trip_distance: float = 0.0    # km
    total_distance: float = 0.0   # km
    current: float = 0.0          # Amps (phase current for most wheels)
    temperature: float = 0.0      # Celsius
    battery_percent: float = 0.0  # 0-100%
    is_charging: bool = False
    charge_mode: int = 0
    pitch_angle: float = 0.0
    roll_angle: float = 0.0
    version: str = ""
    model: str = ""
    manufacturer: str = "Unknown"
    system_voltage: float = 0.0   # Nominal/Max voltage (e.g. 100.8V)
    pwm: float = 0.0              # PWM percentage
    battery_current: float = 0.0  # Battery current (for BMS-equipped wheels)
    

class EucDecoder(ABC):
    """Base class for EUC protocol decoders."""

    def __init__(self) -> None:
        self.last_telemetry = EucTelemetry()
        self.packet_count = 0
        self.error_count = 0

    @abstractmethod
    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode a packet and return dictionary of values if complete frame."""
        pass

    def get_keepalive_packet(self) -> Optional[bytes]:
        """Return keepalive packet for bidirectional protocols (InMotion, Ninebot).
        
        Returns None for passive protocols (KingSong, Gotway, Veteran).
        """
        return None

    @property
    def name(self) -> str:
        """Return the name of the decoder."""
        return self.__class__.__name__
    
    @property
    def brand(self) -> WheelBrand:
        """Return the brand this decoder supports."""
        return WheelBrand.UNKNOWN

    def calculate_battery_percent(
        self, 
        voltage: float, 
        system_voltage: float,
        use_better_percents: bool = True
    ) -> float:
        """Calculate battery percentage based on voltage and system configuration.
        
        Args:
            voltage: Current battery voltage
            system_voltage: Max/nominal system voltage (e.g., 100.8 for 24S)
            use_better_percents: Use non-linear curve for more accurate readings
        """
        if system_voltage <= 0:
            return 0.0
        
        # Determine cell configuration
        cell_config = None
        for config_name, config in CELL_CONFIG.items():
            if abs(system_voltage - config["max_voltage"]) < 1.0:
                cell_config = config
                break
        
        if not cell_config:
            # Fallback to simple linear calculation
            return max(0.0, min(100.0, (voltage / system_voltage) * 100.0))
        
        if not use_better_percents:
            # Simple linear calculation
            max_v = cell_config["max_voltage"]
            min_v = cell_config["cells"] * 3.0  # 3.0V per cell is considered empty
            return max(0.0, min(100.0, ((voltage - min_v) / (max_v - min_v)) * 100.0))
        
        # Better non-linear calculation based on Li-ion discharge curve
        # Based on WheelLog's "better percents" algorithm
        voltage_raw = int(voltage * 100)
        max_voltage_raw = int(cell_config["max_voltage"] * 100)
        cells = cell_config["cells"]
        
        # Thresholds (in centivolts)
        full_threshold = max_voltage_raw - (cells * 6)  # 4.14V per cell
        upper_threshold = cells * 340  # 3.40V per cell
        lower_threshold = cells * 331  # 3.31V per cell
        
        if voltage_raw >= full_threshold:
            return 100.0
        elif voltage_raw > upper_threshold:
            # Linear interpolation between 3.40V and full
            range_v = full_threshold - upper_threshold
            current_v = voltage_raw - upper_threshold
            return round((current_v / range_v) * 100.0, 1)
        elif voltage_raw > lower_threshold:
            # Slower discharge region
            range_v = upper_threshold - lower_threshold
            current_v = voltage_raw - lower_threshold
            return round((current_v / range_v) * 20.0, 1)  # Only 20% in this region
        else:
            return 0.0


class UnpackerState(Enum):
    """State of the protocol unpacker."""
    UNKNOWN = 0
    LENSEARCH = 1
    COLLECTING = 2
    DONE = 3


class VeteranUnpacker:
    """Accumulates BLE packets to assemble complete Veteran protocol frames.
    
    Frame format: DC 5A 5C [len] [data...]
    """

    def __init__(self) -> None:
        """Initialize the unpacker."""
        self.buffer = bytearray()
        self.old1 = 0
        self.old2 = 0
        self.length = 0
        self.state = UnpackerState.UNKNOWN

    def reset(self) -> None:
        """Reset unpacker state."""
        self.old1 = 0
        self.old2 = 0
        self.state = UnpackerState.UNKNOWN

    def get_buffer(self) -> bytes:
        """Return the accumulated buffer."""
        return bytes(self.buffer)

    def add_char(self, c: int) -> bool:
        """Add a byte to the unpacker. Returns True when a complete frame is ready."""
        if self.state == UnpackerState.COLLECTING:
            bsize = len(self.buffer)

            # Validation checks from WheelLog
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
                return True

        elif self.state == UnpackerState.LENSEARCH:
            self.buffer.append(c)
            self.length = c & 0xFF
            self.state = UnpackerState.COLLECTING
            self.old2 = self.old1
            self.old1 = c

        else:  # UNKNOWN state
            # Looking for DC 5A 5C header sequence
            if c == 0x5C and self.old1 == 0x5A and self.old2 == 0xDC:
                self.buffer = bytearray([0xDC, 0x5A, 0x5C])
                self.state = UnpackerState.LENSEARCH
            elif c == 0x5A and self.old1 == 0xDC:
                self.old2 = self.old1
            else:
                self.old2 = 0

            self.old1 = c

        return False

    def add_data(self, data: bytes) -> list[bytes]:
        """Add multiple bytes and return any complete frames."""
        frames = []
        for byte in data:
            if self.add_char(byte):
                frames.append(self.get_buffer())
        return frames


class KingSongUnpacker:
    """Unpacker for KingSong protocol.
    
    Frame format: AA 55 [18 bytes data] 5A 5A 5A 5A
    Fixed 20-byte packets with 4-byte footer.
    """

    FRAME_SIZE = 20
    HEADER = bytes([0xAA, 0x55])
    FOOTER = bytes([0x5A, 0x5A, 0x5A, 0x5A])

    def __init__(self) -> None:
        self.buffer = bytearray()

    def add_data(self, data: bytes) -> list[bytes]:
        """Add data and return complete frames."""
        self.buffer.extend(data)
        frames = []
        
        while len(self.buffer) >= self.FRAME_SIZE:
            # Look for header
            if self.buffer[:2] == self.HEADER:
                if len(self.buffer) >= self.FRAME_SIZE:
                    frame = bytes(self.buffer[:self.FRAME_SIZE])
                    # Verify footer
                    if frame[-4:] == self.FOOTER:
                        frames.append(frame)
                        self.buffer = self.buffer[self.FRAME_SIZE:]
                    else:
                        # Invalid frame, skip header
                        self.buffer = self.buffer[2:]
                else:
                    # Wait for more data
                    break
            else:
                # Skip one byte and keep looking
                self.buffer = self.buffer[1:]
        
        return frames


class GotwayUnpacker:
    """Unpacker for Gotway/Begode protocol.
    
    Frame format: 55 AA [18 bytes data] 5A 5A 5A 5A
    Fixed 20-byte packets with 4-byte footer.
    """

    FRAME_SIZE = 20
    HEADER = bytes([0x55, 0xAA])
    FOOTER = bytes([0x5A, 0x5A, 0x5A, 0x5A])

    def __init__(self) -> None:
        self.buffer = bytearray()

    def add_data(self, data: bytes) -> list[bytes]:
        """Add data and return complete frames."""
        self.buffer.extend(data)
        frames = []
        
        while len(self.buffer) >= self.FRAME_SIZE:
            # Look for header
            if self.buffer[:2] == self.HEADER:
                if len(self.buffer) >= self.FRAME_SIZE:
                    frame = bytes(self.buffer[:self.FRAME_SIZE])
                    # Verify footer
                    if frame[-4:] == self.FOOTER:
                        frames.append(frame)
                        self.buffer = self.buffer[self.FRAME_SIZE:]
                    else:
                        # Invalid frame, skip header
                        self.buffer = self.buffer[2:]
                else:
                    # Wait for more data
                    break
            else:
                # Skip one byte and keep looking
                self.buffer = self.buffer[1:]
        
        return frames


class VeteranDecoder(EucDecoder):
    """Decoder for Veteran/Leaperkim wheels.
    
    Supports: Sherman, Sherman S, Abrams, Patton, Lynx, Sherman L, Oryx, and Nosfet models.
    """

    # Model detection based on version field
    MODEL_MAP = {
        0: "Sherman",
        1: "Sherman",
        2: "Abrams",
        3: "Sherman S",
        4: "Patton",
        5: "Lynx",
        6: "Sherman L",
        7: "Patton S",
        8: "Oryx",
        42: "Nosfet Apex",
        43: "Nosfet Aero",
    }

    # Voltage configurations by model
    VOLTAGE_MAP = {
        "Sherman": 100.8,      # 24S
        "Sherman S": 100.8,    # 24S
        "Abrams": 100.8,       # 24S
        "Patton": 126.0,       # 30S
        "Patton S": 126.0,     # 30S
        "Lynx": 151.2,         # 36S
        "Sherman L": 151.2,    # 36S
        "Oryx": 176.4,         # 42S
        "Nosfet Apex": 151.2,  # 36S
        "Nosfet Aero": 126.0,  # 30S
    }

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = VeteranUnpacker()
        self.model_version = 0
        self.detected_model = "Sherman S"  # Default

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.VETERAN

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode BLE notification data."""
        if not data:
            return None

        frames = self.unpacker.add_data(data)
        result = None
        
        for frame in frames:
            decoded = self._decode_frame(frame)
            if decoded:
                result = decoded
                
        return result

    def _decode_frame(self, buff: bytes) -> Optional[dict[str, Any]]:
        """Decode a complete assembled frame."""
        if len(buff) < 36:
            self.error_count += 1
            return None

        try:
            voltage = struct.unpack(">H", buff[4:6])[0] / 100.0
            speed = (struct.unpack(">h", buff[6:8])[0] * 10) / 1000.0
            distance = self._int_from_bytes_rev_be(buff, 8) / 1000.0
            total_distance = self._int_from_bytes_rev_be(buff, 12) / 1000.0
            current = (struct.unpack(">h", buff[16:18])[0] * 10) / 1000.0
            temperature = struct.unpack(">h", buff[18:20])[0] / 100.0
            
            # Other fields
            auto_off_sec = struct.unpack(">H", buff[20:22])[0]
            charge_mode = struct.unpack(">H", buff[22:24])[0]
            
            # Version and model detection
            ver = struct.unpack(">H", buff[28:30])[0]
            version_str = f"{ver // 1000:03d}.{(ver % 1000) // 100}.{ver % 100:02d}"
            model_ver = ver // 1000
            
            # Detect model
            if model_ver != self.model_version:
                self.model_version = model_ver
                self.detected_model = self.MODEL_MAP.get(model_ver, "Sherman S")
            
            model = self.detected_model
            system_voltage = self.VOLTAGE_MAP.get(model, 100.8)
            
            # Pitch angle (if available)
            pitch_angle = 0.0
            if len(buff) >= 34:
                pitch_angle = struct.unpack(">h", buff[32:34])[0] / 100.0
            
            battery_percent = self.calculate_battery_percent(voltage, system_voltage)
            is_charging = charge_mode > 0

            self.packet_count += 1
            
            self.last_telemetry.voltage = voltage
            self.last_telemetry.speed = speed
            self.last_telemetry.trip_distance = distance
            self.last_telemetry.total_distance = total_distance
            self.last_telemetry.current = current
            self.last_telemetry.temperature = temperature
            self.last_telemetry.battery_percent = battery_percent
            self.last_telemetry.is_charging = is_charging
            self.last_telemetry.charge_mode = charge_mode
            self.last_telemetry.version = version_str
            self.last_telemetry.model = model
            self.last_telemetry.manufacturer = "Leaperkim" if model.startswith("Sherman") else "Veteran"
            self.last_telemetry.system_voltage = system_voltage
            self.last_telemetry.pitch_angle = pitch_angle

            return {
                "voltage": voltage,
                "speed": speed,
                "trip_distance": distance,
                "total_distance": total_distance,
                "current": current,
                "temperature": temperature,
                "battery_percent": battery_percent,
                "is_charging": is_charging,
                "charge_mode": charge_mode,
                "version": version_str,
                "model": model,
                "manufacturer": self.last_telemetry.manufacturer,
                "system_voltage": system_voltage,
                "auto_off_sec": auto_off_sec,
                "pitch_angle": pitch_angle,
            }

        except (struct.error, IndexError) as e:
            _LOGGER.debug(f"Veteran decode error: {e}")
            self.error_count += 1
            return None

    def _int_from_bytes_rev_be(self, data: bytes, offset: int) -> int:
        """Read a 32-bit integer in 'reversed big-endian' format."""
        low = struct.unpack(">H", data[offset:offset+2])[0]
        high = struct.unpack(">H", data[offset+2:offset+4])[0]
        return (high << 16) | low


class KingSongDecoder(EucDecoder):
    """Decoder for KingSong wheels.
    
    Supports all KingSong models with automatic voltage detection.
    """

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = KingSongUnpacker()
        self.system_voltage = 67.2  # Default 16S
        self.model_name = "KingSong"

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.KINGSONG

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode BLE notification data."""
        if not data:
            return None

        frames = self.unpacker.add_data(data)
        result = None
        
        for frame in frames:
            decoded = self._decode_frame(frame)
            if decoded:
                result = decoded
                
        return result

    def _decode_frame(self, buff: bytes) -> Optional[dict[str, Any]]:
        """Decode a complete frame."""
        if len(buff) < 20:
            self.error_count += 1
            return None

        try:
            frame_type = buff[18] if len(buff) > 18 else 0
            
            # Live data frame (0xA9)
            if frame_type == 0xA9:
                voltage = struct.unpack(">H", buff[2:4])[0] / 100.0
                speed = struct.unpack(">H", buff[4:6])[0] * 3.6  # Convert to km/h
                total_distance = struct.unpack(">I", buff[6:10])[0] / 1000.0
                current = struct.unpack(">h", buff[10:12])[0] / 100.0
                temperature = struct.unpack(">h", buff[12:14])[0] / 340.0 + 36.53  # MPU6050 formula
                
                # Auto-detect system voltage
                self._detect_voltage(voltage)
                
                battery_percent = self.calculate_battery_percent(voltage, self.system_voltage)
                
                # KingSong doesn't directly report charging, infer from current
                is_charging = current < -0.5  # Negative current = charging
                
                self.packet_count += 1
                
                self.last_telemetry.voltage = voltage
                self.last_telemetry.speed = speed
                self.last_telemetry.total_distance = total_distance
                self.last_telemetry.current = current
                self.last_telemetry.temperature = temperature
                self.last_telemetry.battery_percent = battery_percent
                self.last_telemetry.is_charging = is_charging
                self.last_telemetry.model = self.model_name
                self.last_telemetry.manufacturer = "KingSong"
                self.last_telemetry.system_voltage = self.system_voltage

                return {
                    "voltage": voltage,
                    "speed": speed,
                    "total_distance": total_distance,
                    "current": current,
                    "temperature": temperature,
                    "battery_percent": battery_percent,
                    "is_charging": is_charging,
                    "model": self.model_name,
                    "manufacturer": "KingSong",
                    "system_voltage": self.system_voltage,
                }
            
            # Model/Name frame (0xBB) - could parse model name here
            elif frame_type == 0xBB:
                # Model name parsing could be added here
                pass

        except (struct.error, IndexError) as e:
            _LOGGER.debug(f"KingSong decode error: {e}")
            self.error_count += 1
            return None

        return None

    def _detect_voltage(self, voltage: float) -> None:
        """Auto-detect system voltage based on measured voltage."""
        # Check against known configurations
        if voltage > 90.0:
            if voltage > 140.0:
                if voltage > 165.0:
                    self.system_voltage = 176.4  # 42S
                else:
                    self.system_voltage = 151.2  # 36S
            elif voltage > 115.0:
                self.system_voltage = 126.0  # 30S
            else:
                self.system_voltage = 100.8  # 24S
        elif voltage > 75.0:
            self.system_voltage = 84.0  # 20S
        else:
            self.system_voltage = 67.2  # 16S


class GotwayDecoder(EucDecoder):
    """Decoder for Gotway/Begode wheels.
    
    Supports all Gotway/Begode models with automatic voltage detection.
    """

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = GotwayUnpacker()
        self.system_voltage = 84.0  # Default 20S
        self.model_name = "Gotway"

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.GOTWAY

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode BLE notification data."""
        if not data:
            return None

        frames = self.unpacker.add_data(data)
        result = None
        
        for frame in frames:
            decoded = self._decode_frame(frame)
            if decoded:
                result = decoded
                
        return result

    def _decode_frame(self, buff: bytes) -> Optional[dict[str, Any]]:
        """Decode a complete frame."""
        if len(buff) < 20:
            self.error_count += 1
            return None

        try:
            frame_type = buff[18] if len(buff) > 18 else 0
            
            # Live data frame (0x00)
            if frame_type == 0x00:
                voltage = struct.unpack(">H", buff[2:4])[0] / 100.0
                speed = struct.unpack(">h", buff[4:6])[0] * 3.6 * 0.875  # Apply scaler
                current = struct.unpack(">h", buff[10:12])[0] / 100.0
                temperature = struct.unpack(">h", buff[12:14])[0] / 340.0 + 36.53  # MPU6050
                
                # Distance varies by firmware
                total_distance = struct.unpack(">I", buff[8:12])[0] * 0.875 / 1000.0
                
                # PWM
                pwm = abs(struct.unpack(">h", buff[14:16])[0]) / 10.0
                
                # Auto-detect system voltage
                self._detect_voltage(voltage)
                
                battery_percent = self.calculate_battery_percent(voltage, self.system_voltage)
                
                # Infer charging from current
                is_charging = current < -0.5
                
                self.packet_count += 1
                
                self.last_telemetry.voltage = voltage
                self.last_telemetry.speed = speed
                self.last_telemetry.total_distance = total_distance
                self.last_telemetry.current = current
                self.last_telemetry.temperature = temperature
                self.last_telemetry.battery_percent = battery_percent
                self.last_telemetry.is_charging = is_charging
                self.last_telemetry.pwm = pwm
                self.last_telemetry.model = self.model_name
                self.last_telemetry.manufacturer = "Begode"
                self.last_telemetry.system_voltage = self.system_voltage

                return {
                    "voltage": voltage,
                    "speed": speed,
                    "total_distance": total_distance,
                    "current": current,
                    "temperature": temperature,
                    "battery_percent": battery_percent,
                    "is_charging": is_charging,
                    "pwm": pwm,
                    "model": self.model_name,
                    "manufacturer": "Begode",
                    "system_voltage": self.system_voltage,
                }

        except (struct.error, IndexError) as e:
            _LOGGER.debug(f"Gotway decode error: {e}")
            self.error_count += 1
            return None

        return None

    def _detect_voltage(self, voltage: float) -> None:
        """Auto-detect system voltage based on measured voltage."""
        if voltage > 115.0:
            if voltage > 140.0:
                self.system_voltage = 151.2  # 36S
            else:
                self.system_voltage = 126.0  # 30S
        elif voltage > 90.0:
            self.system_voltage = 100.8  # 24S
        elif voltage > 75.0:
            self.system_voltage = 84.0  # 20S
        else:
            self.system_voltage = 67.2  # 16S


# Placeholder decoders for InMotion and Ninebot
# These require more complex protocol handling with requests/responses

class InMotionUnpacker:
    """Unpacker for InMotion V1 protocol CAN-style frames.
    
    Frame format: AA AA [len] [data...] [checksum] [checksum]
    Special escape: A5 -> escaped
    """

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.state = UnpackerState.UNKNOWN
        self.length = 0
        self.escape_next = False

    def add_char(self, c: int) -> bool:
        """Add a character to the buffer. Returns True when frame is complete."""
        if self.state == UnpackerState.UNKNOWN:
            if c == 0xAA:
                self.buffer.clear()
                self.buffer.append(c)
                self.state = UnpackerState.LENSEARCH
            return False
        
        elif self.state == UnpackerState.LENSEARCH:
            self.buffer.append(c)
            if len(self.buffer) == 2:
                if c == 0xAA:
                    # Valid header AA AA
                    self.state = UnpackerState.LENSEARCH
                else:
                    # Invalid, reset
                    self.state = UnpackerState.UNKNOWN
            elif len(self.buffer) == 3:
                # This is the length byte
                self.length = c
                self.state = UnpackerState.COLLECTING
            return False
        
        elif self.state == UnpackerState.COLLECTING:
            # Check for escape sequence (A5)
            if c == 0xA5 and not self.escape_next:
                self.escape_next = True
                return False
            
            if self.escape_next:
                # Un-escape the data
                self.buffer.append(c)
                self.escape_next = False
            else:
                self.buffer.append(c)
            
            # Frame complete when we have: header(2) + len(1) + data(len) + checksum(2)
            expected_length = 2 + 1 + self.length + 2
            if len(self.buffer) >= expected_length:
                self.state = UnpackerState.DONE
                return True
            return False
        
        return False

    def get_frame(self) -> Optional[bytes]:
        """Get the complete frame if available."""
        if self.state == UnpackerState.DONE:
            frame = bytes(self.buffer)
            self.buffer.clear()
            self.state = UnpackerState.UNKNOWN
            return frame
        return None


class InMotionDecoder(EucDecoder):
    """Decoder for InMotion wheels (V1 protocol).
    
    Protocol: CAN-style framing with AA AA header
    - Requires bidirectional communication (request/response)
    - Uses data escaping with A5
    - Includes checksum validation
    - Requires password authentication on some models
    """

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = InMotionUnpacker()
        self.system_voltage = 84.0  # Default 20S, will be detected
        self.password_sent = False

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.INMOTION

    def get_keepalive_packet(self) -> Optional[bytes]:
        """Return keepalive/request packet for InMotion V1."""
        # Request live data: AA AA 09 01 01 01 01 01 01 01 01 01 [checksum]
        # Simplified request for live data
        return bytes([0xAA, 0xAA, 0x09, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00])

    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate InMotion checksum (sum of all bytes)."""
        return sum(data) & 0xFFFF

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode InMotion V1 protocol data."""
        self.packet_count += 1
        
        # Feed data into unpacker
        for byte in data:
            if self.unpacker.add_char(byte):
                frame = self.unpacker.get_frame()
                if frame:
                    return self._parse_frame(frame)
        
        return None

    def _parse_frame(self, frame: bytes) -> Optional[dict[str, Any]]:
        """Parse a complete InMotion V1 frame."""
        if len(frame) < 5:
            return None
        
        # Verify header
        if frame[0] != 0xAA or frame[1] != 0xAA:
            _LOGGER.warning("Invalid InMotion frame header: %s", frame[:2].hex())
            self.error_count += 1
            return None
        
        length = frame[2]
        if len(frame) < 3 + length + 2:
            return None
        
        # Extract checksum (last 2 bytes)
        payload = frame[2:2+length+1]  # length byte + data
        checksum_received = struct.unpack(">H", frame[-2:])[0]
        checksum_calculated = self._calculate_checksum(payload)
        
        if checksum_received != checksum_calculated:
            _LOGGER.warning("InMotion checksum mismatch: expected %04x, got %04x", checksum_calculated, checksum_received)
            self.error_count += 1
            return None
        
        # Parse data based on message type (first data byte after length)
        msg_type = frame[3] if len(frame) > 3 else 0
        
        if msg_type == 0x01:  # Live data response
            return self._parse_live_data(frame[3:])
        
        return None

    def _parse_live_data(self, data: bytes) -> Optional[dict[str, Any]]:
        """Parse InMotion live data message."""
        if len(data) < 30:
            return None
        
        try:
            # InMotion V1 live data structure (approximate, needs verification)
            voltage = struct.unpack(">H", data[1:3])[0] / 100.0
            speed = struct.unpack(">h", data[3:5])[0] / 100.0
            trip_distance = struct.unpack(">I", data[5:9])[0] / 1000.0
            total_distance = struct.unpack(">I", data[9:13])[0] / 1000.0
            current = struct.unpack(">h", data[13:15])[0] / 100.0
            temperature = struct.unpack(">h", data[15:17])[0] / 100.0
            
            # Detect system voltage from first packet
            if voltage > 60 and self.system_voltage == 84.0:
                # Auto-detect based on voltage
                if voltage > 150:
                    self.system_voltage = 176.4  # 42S
                elif voltage > 140:
                    self.system_voltage = 151.2  # 36S
                elif voltage > 115:
                    self.system_voltage = 126.0  # 30S
                elif voltage > 95:
                    self.system_voltage = 100.8  # 24S
                elif voltage > 75:
                    self.system_voltage = 84.0   # 20S
                else:
                    self.system_voltage = 67.2   # 16S
            
            battery_percent = self.calculate_battery_percent(voltage, self.system_voltage)
            
            # InMotion charging detection (current > 0 and speed ~= 0)
            is_charging = current > 0.5 and abs(speed) < 1.0
            
            telemetry = {
                "voltage": voltage,
                "speed": speed * 3.6,  # Convert to km/h
                "trip_distance": trip_distance,
                "total_distance": total_distance,
                "current": current,
                "temperature": temperature,
                "battery_percent": battery_percent,
                "is_charging": is_charging,
                "charge_mode": 1 if is_charging else 0,
                "model": "InMotion V1",
                "version": "1.0",
                "manufacturer": "InMotion",
                "system_voltage": self.system_voltage,
            }
            
            self.last_telemetry = EucTelemetry(**telemetry)
            return telemetry
            
        except (struct.error, IndexError) as ex:
            _LOGGER.error("Error parsing InMotion data: %s", ex)
            self.error_count += 1
            return None


class InMotionV2Unpacker:
    """Unpacker for InMotion V2 protocol frames.
    
    Frame format: DC 5A [len] [command] [data...] [checksum]
    Similar to Veteran but with different command structure
    """

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.state = UnpackerState.UNKNOWN
        self.length = 0

    def add_char(self, c: int) -> bool:
        """Add a character to the buffer. Returns True when frame is complete."""
        if self.state == UnpackerState.UNKNOWN:
            if c == 0xDC:
                self.buffer.clear()
                self.buffer.append(c)
                self.state = UnpackerState.LENSEARCH
            return False
        
        elif self.state == UnpackerState.LENSEARCH:
            self.buffer.append(c)
            if len(self.buffer) == 2:
                if c == 0x5A:
                    # Valid header DC 5A
                    self.state = UnpackerState.LENSEARCH
                else:
                    # Invalid, reset
                    self.state = UnpackerState.UNKNOWN
            elif len(self.buffer) == 3:
                # This is the length byte
                self.length = c
                self.state = UnpackerState.COLLECTING
            return False
        
        elif self.state == UnpackerState.COLLECTING:
            self.buffer.append(c)
            # Frame complete when we have: header(2) + len(1) + data(len) + checksum(2)
            expected_length = 2 + 1 + self.length + 2
            if len(self.buffer) >= expected_length:
                self.state = UnpackerState.DONE
                return True
            return False
        
        return False

    def get_frame(self) -> Optional[bytes]:
        """Get the complete frame if available."""
        if self.state == UnpackerState.DONE:
            frame = bytes(self.buffer)
            self.buffer.clear()
            self.state = UnpackerState.UNKNOWN
            return frame
        return None


class InMotionV2Decoder(EucDecoder):
    """Decoder for InMotion wheels (V2 protocol - V11, V12, V13, V14).
    
    Protocol: DC 5A framing (similar to Veteran but different structure)
    - Requires bidirectional communication (request/response)
    - Uses simple checksum validation
    - Newer InMotion models (V11+)
    """

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = InMotionV2Unpacker()
        self.system_voltage = 100.8  # Default 24S, will be detected

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.INMOTION_V2

    def get_keepalive_packet(self) -> Optional[bytes]:
        """Return keepalive/request packet for InMotion V2."""
        # Request live data: DC 5A 05 01 [data] [checksum]
        # Simplified request for live data
        packet = bytearray([0xDC, 0x5A, 0x05, 0x01, 0x00, 0x00, 0x00, 0x00])
        # Add checksum (XOR of all bytes except header)
        checksum = 0
        for b in packet[2:]:
            checksum ^= b
        packet.extend(struct.pack(">H", checksum))
        return bytes(packet)

    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate InMotion V2 checksum (XOR of data bytes)."""
        checksum = 0
        for b in data:
            checksum ^= b
        return checksum

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode InMotion V2 protocol data."""
        self.packet_count += 1
        
        # Feed data into unpacker
        for byte in data:
            if self.unpacker.add_char(byte):
                frame = self.unpacker.get_frame()
                if frame:
                    return self._parse_frame(frame)
        
        return None

    def _parse_frame(self, frame: bytes) -> Optional[dict[str, Any]]:
        """Parse a complete InMotion V2 frame."""
        if len(frame) < 6:
            return None
        
        # Verify header
        if frame[0] != 0xDC or frame[1] != 0x5A:
            _LOGGER.warning("Invalid InMotion V2 frame header: %s", frame[:2].hex())
            self.error_count += 1
            return None
        
        length = frame[2]
        if len(frame) < 3 + length + 2:
            return None
        
        # Extract checksum (last 2 bytes)
        payload = frame[2:2+length+1]  # length byte + data
        checksum_received = struct.unpack(">H", frame[-2:])[0]
        checksum_calculated = self._calculate_checksum(payload)
        
        if checksum_received != checksum_calculated:
            _LOGGER.warning("InMotion V2 checksum mismatch: expected %04x, got %04x", checksum_calculated, checksum_received)
            self.error_count += 1
            return None
        
        # Parse data based on command type
        command = frame[3] if len(frame) > 3 else 0
        
        if command == 0x01:  # Live data response
            return self._parse_live_data(frame[4:])
        
        return None

    def _parse_live_data(self, data: bytes) -> Optional[dict[str, Any]]:
        """Parse InMotion V2 live data message."""
        if len(data) < 40:
            return None
        
        try:
            # InMotion V2 live data structure (based on WheelLog)
            voltage = struct.unpack(">H", data[0:2])[0] / 100.0
            speed = struct.unpack(">h", data[2:4])[0] / 100.0
            trip_distance = struct.unpack(">I", data[4:8])[0] / 1000.0
            total_distance = struct.unpack(">I", data[8:12])[0] / 1000.0
            current = struct.unpack(">h", data[12:14])[0] / 100.0
            temperature = struct.unpack(">h", data[14:16])[0] / 100.0
            
            # Model info (if present in extended packets)
            model = "InMotion V2"
            if len(data) > 20:
                # Try to extract model name
                try:
                    model_bytes = data[20:30]
                    model = model_bytes.decode('ascii', errors='ignore').strip('\x00')
                    if not model:
                        model = "InMotion V2"
                except:
                    pass
            
            # Detect system voltage from first packet
            if voltage > 60 and self.system_voltage == 100.8:
                # Auto-detect based on voltage
                if voltage > 150:
                    self.system_voltage = 176.4  # 42S (V14)
                elif voltage > 140:
                    self.system_voltage = 151.2  # 36S
                elif voltage > 115:
                    self.system_voltage = 126.0  # 30S (V13)
                elif voltage > 95:
                    self.system_voltage = 100.8  # 24S (V11/V12)
                elif voltage > 75:
                    self.system_voltage = 84.0   # 20S
                else:
                    self.system_voltage = 67.2   # 16S
            
            battery_percent = self.calculate_battery_percent(voltage, self.system_voltage)
            
            # InMotion charging detection (current > 0 and speed ~= 0)
            is_charging = current > 0.5 and abs(speed) < 1.0
            
            telemetry = {
                "voltage": voltage,
                "speed": speed * 3.6,  # Convert to km/h
                "trip_distance": trip_distance,
                "total_distance": total_distance,
                "current": current,
                "temperature": temperature,
                "battery_percent": battery_percent,
                "is_charging": is_charging,
                "charge_mode": 1 if is_charging else 0,
                "model": model,
                "version": "2.0",
                "manufacturer": "InMotion",
                "system_voltage": self.system_voltage,
            }
            
            self.last_telemetry = EucTelemetry(**telemetry)
            return telemetry
            
        except (struct.error, IndexError) as ex:
            _LOGGER.error("Error parsing InMotion V2 data: %s", ex)
            self.error_count += 1
            return None




class NinebotEncryption:
    """Encryption helper for Ninebot protocol.
    
    Ninebot uses XOR encryption with a gamma key sequence.
    The key is generated based on the serial number and session.
    """

    def __init__(self) -> None:
        self.gamma_key = bytearray()
        self.key_index = 0

    def init_key(self, serial: str = "N2GUS12345678") -> None:
        """Initialize the gamma key from serial number.
        
        Args:
            serial: Device serial number (default is generic)
        """
        # Generate gamma key from serial
        self.gamma_key = bytearray()
        for i, char in enumerate(serial):
            self.gamma_key.append((ord(char) + i) & 0xFF)
        
        # Extend key to at least 16 bytes
        while len(self.gamma_key) < 16:
            self.gamma_key.append(self.gamma_key[len(self.gamma_key) % len(serial)])
        
        self.key_index = 0

    def encrypt(self, data: bytes | bytearray) -> bytes:
        """Encrypt data using XOR with gamma key."""
        if not self.gamma_key:
            self.init_key()
        
        encrypted = bytearray()
        for byte in data:
            encrypted.append(byte ^ self.gamma_key[self.key_index % len(self.gamma_key)])
            self.key_index = (self.key_index + 1) % len(self.gamma_key)
        
        return bytes(encrypted)

    def decrypt(self, data: bytes | bytearray) -> bytes:
        """Decrypt data using XOR with gamma key (same as encrypt for XOR)."""
        return self.encrypt(data)


class NinebotUnpacker:
    """Unpacker for Ninebot protocol frames.
    
    Frame format: 55 AA [len] [addr] [cmd] [data...] [checksum] [checksum]
    """

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.state = UnpackerState.UNKNOWN
        self.length = 0

    def add_char(self, c: int) -> bool:
        """Add a character to the buffer. Returns True when frame is complete."""
        if self.state == UnpackerState.UNKNOWN:
            if c == 0x55:
                self.buffer.clear()
                self.buffer.append(c)
                self.state = UnpackerState.LENSEARCH
            return False
        
        elif self.state == UnpackerState.LENSEARCH:
            self.buffer.append(c)
            if len(self.buffer) == 2:
                if c == 0xAA:
                    # Valid header 55 AA
                    self.state = UnpackerState.LENSEARCH
                else:
                    # Invalid, reset
                    self.state = UnpackerState.UNKNOWN
            elif len(self.buffer) == 3:
                # This is the length byte
                self.length = c
                self.state = UnpackerState.COLLECTING
            return False
        
        elif self.state == UnpackerState.COLLECTING:
            self.buffer.append(c)
            # Frame complete when we have: header(2) + len(1) + addr(1) + cmd(1) + data(len-2) + checksum(2)
            expected_length = 2 + 1 + self.length + 2
            if len(self.buffer) >= expected_length:
                self.state = UnpackerState.DONE
                return True
            return False
        
        return False

    def get_frame(self) -> Optional[bytes]:
        """Get the complete frame if available."""
        if self.state == UnpackerState.DONE:
            frame = bytes(self.buffer)
            self.buffer.clear()
            self.state = UnpackerState.UNKNOWN
            return frame
        return None


class NinebotDecoder(EucDecoder):
    """Decoder for Ninebot wheels (standard protocol).
    
    Protocol: 55 AA framing with XOR encryption
    - Requires bidirectional communication (request/response)
    - Uses XOR encryption with gamma key
    - Frame structure: 55 AA [len] [addr] [cmd] [data...] [checksum]
    """

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = NinebotUnpacker()
        self.encryption = NinebotEncryption()
        self.system_voltage = 84.0  # Default 20S, will be detected
        self.encryption.init_key()  # Initialize with default key

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.NINEBOT

    def get_keepalive_packet(self) -> Optional[bytes]:
        """Return keepalive/request packet for Ninebot."""
        # Request live data: 55 AA [len] [addr] [cmd] [data] [checksum]
        # Command 0x01 to BMS (addr 0x22) for live data
        packet = bytearray([0x55, 0xAA, 0x03, 0x22, 0x01])
        
        # Calculate checksum (XOR of all bytes after header)
        checksum = 0
        for b in packet[2:]:
            checksum ^= b
        checksum ^= 0xFFFF  # Ninebot uses inverted checksum
        
        packet.extend(struct.pack("<H", checksum))
        
        # Encrypt the data portion (after header and length)
        data_to_encrypt = packet[3:]
        encrypted_data = self.encryption.encrypt(data_to_encrypt)
        
        return bytes(packet[:3]) + encrypted_data

    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate Ninebot checksum (XOR of data bytes, inverted)."""
        checksum = 0
        for b in data:
            checksum ^= b
        return checksum ^ 0xFFFF

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode Ninebot protocol data."""
        self.packet_count += 1
        
        # Feed data into unpacker
        for byte in data:
            if self.unpacker.add_char(byte):
                frame = self.unpacker.get_frame()
                if frame:
                    return self._parse_frame(frame)
        
        return None

    def _parse_frame(self, frame: bytes) -> Optional[dict[str, Any]]:
        """Parse a complete Ninebot frame."""
        if len(frame) < 7:
            return None
        
        # Verify header
        if frame[0] != 0x55 or frame[1] != 0xAA:
            _LOGGER.warning("Invalid Ninebot frame header: %s", frame[:2].hex())
            self.error_count += 1
            return None
        
        length = frame[2]
        if len(frame) < 3 + length + 2:
            return None
        
        # Decrypt the data portion (after length byte)
        encrypted_portion = frame[3:]
        decrypted_portion = self.encryption.decrypt(encrypted_portion)
        
        # Reconstruct frame with decrypted data
        decrypted_frame = frame[:3] + decrypted_portion
        
        # Extract checksum (last 2 bytes)
        addr = decrypted_frame[3]
        cmd = decrypted_frame[4]
        payload = decrypted_frame[2:-2]  # length + addr + cmd + data
        checksum_received = struct.unpack("<H", decrypted_frame[-2:])[0]
        checksum_calculated = self._calculate_checksum(payload)
        
        if checksum_received != checksum_calculated:
            _LOGGER.warning("Ninebot checksum mismatch: expected %04x, got %04x", checksum_calculated, checksum_received)
            self.error_count += 1
            return None
        
        # Parse data based on command
        if addr == 0x22 and cmd == 0x01:  # BMS live data response
            return self._parse_live_data(decrypted_frame[5:-2])
        
        return None

    def _parse_live_data(self, data: bytes) -> Optional[dict[str, Any]]:
        """Parse Ninebot live data message."""
        if len(data) < 30:
            return None
        
        try:
            # Ninebot live data structure (based on WheelLog)
            voltage = struct.unpack("<H", data[0:2])[0] / 100.0
            current = struct.unpack("<h", data[2:4])[0] / 100.0
            speed = struct.unpack("<h", data[4:6])[0] / 100.0
            trip_distance = struct.unpack("<I", data[6:10])[0] / 1000.0
            total_distance = struct.unpack("<I", data[10:14])[0] / 1000.0
            temperature = struct.unpack("<h", data[14:16])[0] / 10.0
            
            # Detect system voltage from first packet
            if voltage > 60 and self.system_voltage == 84.0:
                # Auto-detect based on voltage
                if voltage > 150:
                    self.system_voltage = 176.4  # 42S
                elif voltage > 140:
                    self.system_voltage = 151.2  # 36S
                elif voltage > 115:
                    self.system_voltage = 126.0  # 30S
                elif voltage > 95:
                    self.system_voltage = 100.8  # 24S
                elif voltage > 75:
                    self.system_voltage = 84.0   # 20S
                else:
                    self.system_voltage = 67.2   # 16S
            
            battery_percent = self.calculate_battery_percent(voltage, self.system_voltage)
            
            # Ninebot charging detection
            is_charging = current > 0.5 and abs(speed) < 1.0
            
            telemetry = {
                "voltage": voltage,
                "speed": speed * 3.6,  # Convert to km/h
                "trip_distance": trip_distance,
                "total_distance": total_distance,
                "current": current,
                "temperature": temperature,
                "battery_percent": battery_percent,
                "is_charging": is_charging,
                "charge_mode": 1 if is_charging else 0,
                "model": "Ninebot",
                "version": "1.0",
                "manufacturer": "Ninebot",
                "system_voltage": self.system_voltage,
            }
            
            self.last_telemetry = EucTelemetry(**telemetry)
            return telemetry
            
        except (struct.error, IndexError) as ex:
            _LOGGER.error("Error parsing Ninebot data: %s", ex)
            self.error_count += 1
            return None


class NinebotZUnpacker:
    """Unpacker for Ninebot Z protocol frames.
    
    Frame format: 5A A5 [len] [addr] [cmd] [data...] [checksum] [checksum]
    Similar to standard Ninebot but with different header
    """

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.state = UnpackerState.UNKNOWN
        self.length = 0

    def add_char(self, c: int) -> bool:
        """Add a character to the buffer. Returns True when frame is complete."""
        if self.state == UnpackerState.UNKNOWN:
            if c == 0x5A:
                self.buffer.clear()
                self.buffer.append(c)
                self.state = UnpackerState.LENSEARCH
            return False
        
        elif self.state == UnpackerState.LENSEARCH:
            self.buffer.append(c)
            if len(self.buffer) == 2:
                if c == 0xA5:
                    # Valid header 5A A5
                    self.state = UnpackerState.LENSEARCH
                else:
                    # Invalid, reset
                    self.state = UnpackerState.UNKNOWN
            elif len(self.buffer) == 3:
                # This is the length byte
                self.length = c
                self.state = UnpackerState.COLLECTING
            return False
        
        elif self.state == UnpackerState.COLLECTING:
            self.buffer.append(c)
            # Frame complete when we have: header(2) + len(1) + addr(1) + cmd(1) + data(len-2) + checksum(2)
            expected_length = 2 + 1 + self.length + 2
            if len(self.buffer) >= expected_length:
                self.state = UnpackerState.DONE
                return True
            return False
        
        return False

    def get_frame(self) -> Optional[bytes]:
        """Get the complete frame if available."""
        if self.state == UnpackerState.DONE:
            frame = bytes(self.buffer)
            self.buffer.clear()
            self.state = UnpackerState.UNKNOWN
            return frame
        return None


class NinebotZDecoder(EucDecoder):
    """Decoder for Ninebot Z series wheels (Z6, Z8, Z10).
    
    Protocol: 5A A5 framing with XOR encryption
    - Requires bidirectional communication (request/response)
    - Uses XOR encryption with gamma key (same as standard Ninebot)
    - Frame structure: 5A A5 [len] [addr] [cmd] [data...] [checksum]
    - High-performance models with different frame header
    """

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = NinebotZUnpacker()
        self.encryption = NinebotEncryption()
        self.system_voltage = 126.0  # Default 30S (Z10), will be detected
        self.encryption.init_key()  # Initialize with default key

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.NINEBOT_Z

    def get_keepalive_packet(self) -> Optional[bytes]:
        """Return keepalive/request packet for Ninebot Z."""
        # Request live data: 5A A5 [len] [addr] [cmd] [data] [checksum]
        # Command 0x01 to BMS (addr 0x22) for live data
        packet = bytearray([0x5A, 0xA5, 0x03, 0x22, 0x01])
        
        # Calculate checksum (XOR of all bytes after header)
        checksum = 0
        for b in packet[2:]:
            checksum ^= b
        checksum ^= 0xFFFF  # Ninebot uses inverted checksum
        
        packet.extend(struct.pack("<H", checksum))
        
        # Encrypt the data portion (after header and length)
        data_to_encrypt = packet[3:]
        encrypted_data = self.encryption.encrypt(data_to_encrypt)
        
        return bytes(packet[:3]) + encrypted_data

    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate Ninebot Z checksum (XOR of data bytes, inverted)."""
        checksum = 0
        for b in data:
            checksum ^= b
        return checksum ^ 0xFFFF

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode Ninebot Z protocol data."""
        self.packet_count += 1
        
        # Feed data into unpacker
        for byte in data:
            if self.unpacker.add_char(byte):
                frame = self.unpacker.get_frame()
                if frame:
                    return self._parse_frame(frame)
        
        return None

    def _parse_frame(self, frame: bytes) -> Optional[dict[str, Any]]:
        """Parse a complete Ninebot Z frame."""
        if len(frame) < 7:
            return None
        
        # Verify header
        if frame[0] != 0x5A or frame[1] != 0xA5:
            _LOGGER.warning("Invalid Ninebot Z frame header: %s", frame[:2].hex())
            self.error_count += 1
            return None
        
        length = frame[2]
        if len(frame) < 3 + length + 2:
            return None
        
        # Decrypt the data portion (after length byte)
        encrypted_portion = frame[3:]
        decrypted_portion = self.encryption.decrypt(encrypted_portion)
        
        # Reconstruct frame with decrypted data
        decrypted_frame = frame[:3] + decrypted_portion
        
        # Extract checksum (last 2 bytes)
        addr = decrypted_frame[3]
        cmd = decrypted_frame[4]
        payload = decrypted_frame[2:-2]  # length + addr + cmd + data
        checksum_received = struct.unpack("<H", decrypted_frame[-2:])[0]
        checksum_calculated = self._calculate_checksum(payload)
        
        if checksum_received != checksum_calculated:
            _LOGGER.warning("Ninebot Z checksum mismatch: expected %04x, got %04x", checksum_calculated, checksum_received)
            self.error_count += 1
            return None
        
        # Parse data based on command
        if addr == 0x22 and cmd == 0x01:  # BMS live data response
            return self._parse_live_data(decrypted_frame[5:-2])
        
        return None

    def _parse_live_data(self, data: bytes) -> Optional[dict[str, Any]]:
        """Parse Ninebot Z live data message."""
        if len(data) < 30:
            return None
        
        try:
            # Ninebot Z live data structure (similar to standard but may have extended fields)
            voltage = struct.unpack("<H", data[0:2])[0] / 100.0
            current = struct.unpack("<h", data[2:4])[0] / 100.0
            speed = struct.unpack("<h", data[4:6])[0] / 100.0
            trip_distance = struct.unpack("<I", data[6:10])[0] / 1000.0
            total_distance = struct.unpack("<I", data[10:14])[0] / 1000.0
            temperature = struct.unpack("<h", data[14:16])[0] / 10.0
            
            # Try to extract model name from extended data
            model = "Ninebot Z"
            if len(data) > 20:
                try:
                    model_bytes = data[20:30]
                    model_str = model_bytes.decode('ascii', errors='ignore').strip('\x00')
                    if model_str and any(c.isalnum() for c in model_str):
                        model = f"Ninebot {model_str}"
                except:
                    pass
            
            # Detect system voltage from first packet
            if voltage > 60 and self.system_voltage == 126.0:
                # Auto-detect based on voltage (Z series typically higher voltage)
                if voltage > 150:
                    self.system_voltage = 176.4  # 42S
                elif voltage > 140:
                    self.system_voltage = 151.2  # 36S
                elif voltage > 115:
                    self.system_voltage = 126.0  # 30S (Z10 default)
                elif voltage > 95:
                    self.system_voltage = 100.8  # 24S
                elif voltage > 75:
                    self.system_voltage = 84.0   # 20S (Z6/Z8)
                else:
                    self.system_voltage = 67.2   # 16S
            
            battery_percent = self.calculate_battery_percent(voltage, self.system_voltage)
            
            # Ninebot Z charging detection
            is_charging = current > 0.5 and abs(speed) < 1.0
            
            telemetry = {
                "voltage": voltage,
                "speed": speed * 3.6,  # Convert to km/h
                "trip_distance": trip_distance,
                "total_distance": total_distance,
                "current": current,
                "temperature": temperature,
                "battery_percent": battery_percent,
                "is_charging": is_charging,
                "charge_mode": 1 if is_charging else 0,
                "model": model,
                "version": "Z1.0",
                "manufacturer": "Ninebot",
                "system_voltage": self.system_voltage,
            }
            
            self.last_telemetry = EucTelemetry(**telemetry)
            return telemetry
            
        except (struct.error, IndexError) as ex:
            _LOGGER.error("Error parsing Ninebot Z data: %s", ex)
            self.error_count += 1
            return None


def get_decoder_by_data(data: bytes) -> Optional[EucDecoder]:
    """Factory to create the correct decoder based on initial packet header.
    
    Detects protocol by examining packet headers with minimum length requirements:
    - DC 5A 5C [len]: Veteran/Leaperkim (min 4 bytes)
    - AA 55 [len] [cmd]: KingSong (min 4 bytes, cmd=0xA9 for live data)
    - 55 AA DC 5A: Gotway/Begode (min 4 bytes, distinctive 4-byte header)
    - 55 AA [len] [cmd]: Ninebot (min 4 bytes, encrypted, cmd=0x01-0x04)
    - DC 5A [flags]: InMotion V2 (min 3 bytes, flags=0x11/0x14)
    - AA AA [len] [cmd]: InMotion V1 (min 4 bytes, CAN-style)
    - 5A A5 [len] [cmd]: Ninebot Z (min 4 bytes, Z-series header)
    
    Protocol detection priority (to handle overlapping headers):
    1. Check unique 4-byte headers first (Gotway 55 AA DC 5A)
    2. Check unique 3-byte headers (Veteran DC 5A 5C, Ninebot Z 5A A5)
    3. Disambiguate 2-byte headers (55 AA, AA 55, AA AA, DC 5A) using subsequent bytes
    """
    if len(data) < 2:
        return None
    
    # Priority 1: Unique 4-byte header - Gotway (55 AA DC 5A)
    if len(data) >= 4 and data[0] == 0x55 and data[1] == 0xAA and data[2] == 0xDC and data[3] == 0x5A:
        _LOGGER.debug("Detected Gotway/Begode protocol (55 AA DC 5A header)")
        return GotwayDecoder()
    
    # Priority 2: Unique 3-byte headers
    
    # Check for Veteran (DC 5A 5C)
    if len(data) >= 4 and data[0] == 0xDC and data[1] == 0x5A and data[2] == 0x5C:
        _LOGGER.debug("Detected Veteran/Leaperkim protocol (DC 5A 5C header)")
        return VeteranDecoder()
    
    # Check for Ninebot Z (5A A5)
    if len(data) >= 4 and data[0] == 0x5A and data[1] == 0xA5:
        _LOGGER.debug("Detected Ninebot Z protocol (5A A5 header)")
        return NinebotZDecoder()
    
    # Priority 3: Disambiguate 2-byte headers using subsequent bytes
    
    # Check for KingSong (AA 55 [len] [cmd])
    # KingSong uses cmd=0xA9 for live data, len is typically 0x14-0x18
    if len(data) >= 4 and data[0] == 0xAA and data[1] == 0x55:
        packet_len = data[2]
        cmd = data[3] if len(data) > 3 else 0
        if packet_len >= 0x14 and packet_len <= 0x30 and cmd == 0xA9:
            _LOGGER.debug("Detected KingSong protocol (AA 55, len=%02x, cmd=A9)", packet_len)
            return KingSongDecoder()
        elif packet_len >= 0x14 and packet_len <= 0x30:
            # Likely KingSong even without cmd check
            _LOGGER.debug("Detected KingSong protocol (AA 55, len=%02x)", packet_len)
            return KingSongDecoder()
    
    # Check for InMotion V1 (AA AA [len] [cmd])
    # InMotion V1 uses CAN-style frames, len is typically 0x09-0x0F
    if len(data) >= 4 and data[0] == 0xAA and data[1] == 0xAA:
        packet_len = data[2]
        if packet_len >= 0x09 and packet_len <= 0x20:
            _LOGGER.debug("Detected InMotion V1 protocol (AA AA, len=%02x)", packet_len)
            return InMotionDecoder()
    
    # Check for InMotion V2 (DC 5A [flags])
    # InMotion V2 uses flags byte after DC 5A (not 5C like Veteran)
    if len(data) >= 3 and data[0] == 0xDC and data[1] == 0x5A:
        flags = data[2]
        # Known V2 flags: 0x01-0x1F (not 0x5C which is Veteran)
        if flags != 0x5C and flags <= 0x1F:
            _LOGGER.debug("Detected InMotion V2 protocol (DC 5A, flags=%02x)", flags)
            return InMotionV2Decoder()
    
    # Check for Ninebot standard (55 AA [len] [cmd])
    # Ninebot uses 55 AA like Gotway but WITHOUT DC 5A after
    # Typical len is 0x03-0x20, cmd is 0x01-0x04 for common requests
    if len(data) >= 4 and data[0] == 0x55 and data[1] == 0xAA:
        packet_len = data[2]
        cmd = data[3] if len(data) > 3 else 0
        # If NOT followed by DC 5A (Gotway marker), assume Ninebot
        if data[2] != 0xDC:
            if packet_len >= 0x03 and packet_len <= 0x30:
                _LOGGER.debug("Detected Ninebot protocol (55 AA, len=%02x, cmd=%02x)", packet_len, cmd)
                return NinebotDecoder()
    
    # Fallback: Log unknown protocol with more context
    hex_dump = data[:min(8, len(data))].hex()
    _LOGGER.debug("Unknown protocol header (len=%d): %s", len(data), hex_dump)
    return None


def get_decoder_by_brand(brand: WheelBrand) -> Optional[EucDecoder]:
    """Create a decoder for a specific brand."""
    brand_map = {
        WheelBrand.VETERAN: VeteranDecoder,
        WheelBrand.LEAPERKIM: VeteranDecoder,
        WheelBrand.KINGSONG: KingSongDecoder,
        WheelBrand.GOTWAY: GotwayDecoder,
        WheelBrand.BEGODE: GotwayDecoder,
        WheelBrand.INMOTION: InMotionDecoder,
        WheelBrand.INMOTION_V2: InMotionV2Decoder,
        WheelBrand.NINEBOT: NinebotDecoder,
        WheelBrand.NINEBOT_Z: NinebotZDecoder,
    }
    
    decoder_class = brand_map.get(brand)
    if decoder_class:
        return decoder_class()
    
    return None
