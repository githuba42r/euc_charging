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
import math
import re
import struct
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .const import CELL_CONFIG, WheelBrand
from .gotway_models import GOTWAY_MODELS, GotwayModel

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
    

# WheelLog "better percents" curves keyed by series cell count, in centivolts:
# (full, upper, upper_base, upper_divisor, lower_base, lower_divisor).
# Above `upper`: (v - upper_base) / upper_divisor; above `lower_base`:
# (v - lower_base) / lower_divisor; otherwise 0%.
BETTER_PERCENT_CURVES: dict[int, tuple[float, ...]] = {
    24: (10020, 8160, 8070, 19.5, 7935, 48.75),
    30: (12525, 10200, 9975, 25.5, 9600, 67.5),
    36: (15030, 12240, 11970, 30.6, 11520, 81),
    42: (17535, 14280, 14123, 34.125, 13886, 85.3125),
}


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

    # Seconds between the coordinator's calls to get_requests() while connected.
    request_interval: float = 1.0

    def reset_session(self) -> None:
        """Forget per-connection protocol state; called on every (re)connect.

        Protocols with a handshake (Ninebot key exchange, Gotway name probe)
        restart it here. Passive protocols need nothing.
        """

    def get_requests(self) -> list[bytes]:
        """Return the packets to write to the wheel now (possibly none).

        The coordinator calls this every ``request_interval`` seconds. Protocols
        driven by a request/response state machine override it; the default
        sends the static keepalive packet, if the protocol has one.
        """
        packet = self.get_keepalive_packet()
        return [packet] if packet else []

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
        
        # Better non-linear calculation based on Li-ion discharge curve,
        # using WheelLog's VeteranAdapter "better percents" constants
        voltage_raw = voltage * 100
        cells = cell_config["cells"]
        full, upper, upper_base, upper_div, lower_base, lower_div = BETTER_PERCENT_CURVES.get(
            cells, tuple(v * cells / 24 for v in BETTER_PERCENT_CURVES[24])
        )

        if voltage_raw > full:
            return 100.0
        if voltage_raw > upper:
            return round((voltage_raw - upper_base) / upper_div, 1)
        if voltage_raw > lower_base:
            return round((voltage_raw - lower_base) / lower_div, 1)
        return 0.0


def euc_world_curve_percent(
    voltage: float, volts: tuple[float, ...], percents: tuple[float, ...]
) -> float:
    """Piecewise-linear voltage -> percent as EUC World does (zh/a.java f()).

    Clamped to the first/last point and rounded half up to a whole percent
    (fc/e.java h()), which is how EUC World reports battery level.
    """
    if voltage < volts[0]:
        return float(percents[0])
    if voltage > volts[-1]:
        return float(percents[-1])
    for i in range(len(volts) - 1):
        if voltage <= volts[i + 1]:
            pct = percents[i] + (voltage - volts[i]) * (
                percents[i + 1] - percents[i]
            ) / (volts[i + 1] - volts[i])
            return float(math.floor(pct + 0.5))
    return float(percents[-1])


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


class GotwayUnpacker:
    """Frame assembler for Gotway/Begode, as in EUC World (wh/s.java h()).

    Wire frame (24 bytes): 55 AA, 16 bytes of data, frame type (byte 18),
    sub-index (byte 19), footer 5A 5A 5A 5A. EUC World appends each BLE chunk
    to a buffer, takes the span from the first 55 AA to the next 5A 5A 5A 5A
    after it, drops everything up to the end of that span, and only decodes
    the span when it is exactly 24 bytes long. A buffer over 40 bytes with no
    complete span is discarded.
    """

    FRAME_SIZE = 24
    MAX_BUFFER = 40
    HEADER = bytes([0x55, 0xAA])
    FOOTER = bytes([0x5A, 0x5A, 0x5A, 0x5A])

    def __init__(self) -> None:
        self.buffer = bytearray()

    def add_data(self, data: bytes) -> list[bytes]:
        """Add a BLE chunk and return the complete 24-byte frames it finished."""
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(self.HEADER)
            end = self.buffer.find(self.FOOTER, start) if start > -1 else -1
            if start > -1 and end > start:
                span = bytes(self.buffer[start:end + 4])
                del self.buffer[:end + 4]
                if len(span) == self.FRAME_SIZE:
                    frames.append(span)
                continue
            if len(self.buffer) > self.MAX_BUFFER:
                _LOGGER.debug("Gotway buffer overrun; dropped %s", self.buffer.hex())
                self.buffer = bytearray(data)
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
        # Battery currents from extended sub-pages 0/4, cached because the
        # sub-page id rotates from frame to frame
        self._subpage_current: Optional[float] = None
        self._pack_currents: Optional[tuple[float, float]] = None

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
            battery_current = self._decode_battery_current(buff, is_charging)
            if is_charging:
                charging_current = (
                    round(-battery_current, 2) if battery_current is not None else None
                )
            else:
                charging_current = 0.0
            charging_power = (
                round(charging_current * voltage, 1) if charging_current is not None else None
            )

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
            if battery_current is not None:
                self.last_telemetry.battery_current = battery_current

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
                "battery_current": battery_current,
                "charging_current": charging_current,
                "charging_power": charging_power,
            }

        except (struct.error, IndexError) as e:
            _LOGGER.debug(f"Veteran decode error: {e}")
            self.error_count += 1
            return None

    def _decode_battery_current(self, buff: bytes, is_charging: bool) -> Optional[float]:
        """Return battery current in amps (negative while charging), per EUC World.

        Frames with payload length >= 47 carry an extended sub-page selected by
        byte 46. Sub-pages 0 and 4 hold the battery current at offset 63 (x0.1 A)
        and, on frames with length >= 73, per-pack currents at 69/71 (x0.01 A).
        """
        length = buff[3]
        if length < 47:
            return None

        if buff[46] in (0, 4) and length >= 69:
            raw = struct.unpack(">h", buff[63:65])[0]
            self._subpage_current = raw * 0.1 if is_charging and raw <= 0 else None
            if length >= 73:
                self._pack_currents = (
                    struct.unpack(">h", buff[69:71])[0] * 0.01,
                    struct.unpack(">h", buff[71:73])[0] * 0.01,
                )

        if not is_charging:
            self._subpage_current = None
            self._pack_currents = None
            return round(struct.unpack(">h", buff[38:40])[0] * 0.15, 2)
        if self._pack_currents is not None:
            return round(sum(self._pack_currents), 2)
        if self._subpage_current is not None:
            return round(self._subpage_current, 2)
        return None

    def _int_from_bytes_rev_be(self, data: bytes, offset: int) -> int:
        """Read a 32-bit integer in 'reversed big-endian' format."""
        low = struct.unpack(">H", data[offset:offset+2])[0]
        high = struct.unpack(">H", data[offset+2:offset+4])[0]
        return (high << 16) | low


class KingSongDecoder(EucDecoder):
    """Decoder for KingSong wheels, following EUC World 2.68.0 (wh/z.java).

    Every notification is one 20-byte little-endian packet: AA 55, data,
    command at byte 16 (requests also carry 0x14 at 17 and 5A 5A at 18-19).
    EUC World takes the first 20 bytes of a notification that starts AA 55 and
    does no reassembly or footer check. Live data is command 0xA9; the model
    comes from the 0xBB name reply ("KS-S18-0205" -> model KS-S18, v2.05),
    which EUC World requests 1 s after connecting and re-requests every 3 s
    until answered. Battery percent is EUC World's default per-model voltage
    curve. EUC World has no charging flag for KingSong, so ``is_charging`` and
    ``charging_current`` are None.
    """

    PACKET_SIZE = 20
    HEADER = bytes([0xAA, 0x55])
    CMD_LIVE = 0xA9
    CMD_DISTANCE = 0xB9
    CMD_SERIAL = 0xB3
    CMD_NAME = 0xBB
    CMD_REQUEST_NAME = 0x9B
    NAME_FIRST_DELAY = 1.0    # wh/z.java e(): N() posted 1000 ms after connect
    NAME_RETRY = 3.0          # K(READ_NAME, 3000, INIT_NAME); timeout re-sends (wh/x.java)

    # EUC World battery_level=0 curves (zh/a.java), (volts, percent) points,
    # chosen by model-name prefix in this order; anything else -> DEFAULT_CURVE.
    BATTERY_CURVES: tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...] = (
        ("KS-16X", (63, 65, 66, 68, 69, 71, 73, 74, 76, 77, 79, 81, 83),
         (0, 10, 21, 31, 40, 49, 55, 63, 71, 79, 86, 93, 100)),
        ("KS-18L", (61, 83), (0, 100)),
        ("KS-F18", (111.6, 149.4), (0, 100)),
        ("KS-F22P", (130.2, 175.5), (0, 100)),
        ("KS-F22", (114.7, 153.5), (0, 100)),
        ("KS-N12P", (50, 66), (0, 100)),
        ("KS-N", (42.9, 54.6), (0, 100)),
        ("KS-S16", (63, 83.5), (0, 100)),
        ("KS-S18", (60, 83), (0, 100)),
        ("KS-S19", (74.4, 100), (0, 100)),
        ("KS-S20", (93, 124.5), (0, 100)),
        ("KS-S22", (93, 124.5), (0, 100)),
        ("KS-S9", (36, 49.8), (0, 100)),
        ("KS-X", (33, 42), (0, 100)),
    )
    DEFAULT_CURVE = ((50.0, 66.0), (0.0, 100.0))

    # Gauge maximum per model (zh/a.java b()) is 4.25 V x series cells; the
    # series count recovered from it gives system_voltage = cells x 4.2 V.
    SERIES_CELLS: tuple[tuple[str, int], ...] = (
        ("KS-16X", 20), ("KS-18L", 20), ("KS-F18", 36), ("KS-F22P", 42),
        ("KS-F22", 37), ("KS-N12P", 16), ("KS-N", 13), ("KS-S16", 20),
        ("KS-S18", 20), ("KS-S19", 24), ("KS-S20", 30), ("KS-S22", 30),
        ("KS-S9", 12), ("KS-X", 10),
    )
    DEFAULT_SERIES = 16

    request_interval = 0.1

    def __init__(self) -> None:
        super().__init__()
        self._clock = time.monotonic
        self.wheel_name: Optional[str] = None
        self.model: Optional[str] = None
        self.version: Optional[str] = None
        self.serial: Optional[str] = None
        self.trip_distance: Optional[float] = None
        self.reset_session()

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.KINGSONG

    def reset_session(self) -> None:
        """Re-request the wheel name after every connect."""
        self._name_answered = False
        self._next_name_request = self._clock() + self.NAME_FIRST_DELAY

    @classmethod
    def build_request(cls, command: int) -> bytes:
        """AA 55, zeros, command at 16, 0x14, 5A 5A (wh/z.java y(false))."""
        packet = bytearray(cls.PACKET_SIZE)
        packet[0:2] = cls.HEADER
        packet[16] = command
        packet[17] = 0x14
        packet[18] = packet[19] = 0x5A
        return bytes(packet)

    def get_requests(self) -> list[bytes]:
        if self._name_answered:
            return []
        now = self._clock()
        if now < self._next_name_request:
            return []
        self._next_name_request = now + self.NAME_RETRY
        return [self.build_request(self.CMD_REQUEST_NAME)]

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode one notification (EUC World: >= 20 bytes starting AA 55)."""
        if len(data) < self.PACKET_SIZE or data[:2] != self.HEADER:
            return None
        return self._decode_frame(bytes(data[:self.PACKET_SIZE]))

    def _decode_frame(self, buff: bytes) -> Optional[dict[str, Any]]:
        command = buff[16]
        if command == self.CMD_NAME:
            self._parse_name(buff)
            return None
        if command == self.CMD_SERIAL:
            # Bytes 2..15 and 17..19, NUL-trimmed (wh/z.java, command 0xB3).
            self.serial = (buff[2:16] + buff[17:20]).decode("ascii", "replace").strip("\x00")
            return None
        if command == self.CMD_DISTANCE:
            hi, lo = struct.unpack_from("<HH", buff, 2)
            self.trip_distance = (hi * 65536 + lo) * 0.001
            return None
        if command != self.CMD_LIVE:
            return None

        voltage = struct.unpack_from("<h", buff, 2)[0] * 0.01
        speed = struct.unpack_from("<h", buff, 4)[0] * 0.01
        hi, lo = struct.unpack_from("<HH", buff, 6)
        total_distance = (hi * 65536 + lo) * 0.001
        current = struct.unpack_from("<h", buff, 10)[0] * 0.01
        temperature = struct.unpack_from("<h", buff, 12)[0] * 0.01

        battery_percent = system_voltage = None
        if self._name_answered:
            battery_percent = self._battery_percent(voltage)
            system_voltage = round(self._series_cells() * 4.2, 2)

        self.packet_count += 1
        return {
            "voltage": round(voltage, 2),
            "speed": round(speed, 2),
            "trip_distance": (
                round(self.trip_distance, 3) if self.trip_distance is not None else None
            ),
            "total_distance": round(total_distance, 3),
            "current": round(current, 2),
            "temperature": round(temperature, 2),
            "battery_percent": battery_percent,
            "is_charging": None,
            "charging_current": None,
            "charging_power": None,
            "battery_current": None,
            "model": self.model or "KingSong",
            "version": self.version,
            "serial": self.serial,
            "manufacturer": "KingSong",
            "system_voltage": system_voltage,
        }

    def _parse_name(self, buff: bytes) -> None:
        """0xBB: bytes 2..15 = "KS-S18-0205" -> model KS-S18, version 2.05."""
        name = buff[2:16].decode("utf-8", "replace").strip("\x00")
        self.wheel_name = name
        self._name_answered = True
        parts = name.split("-")
        if len(parts) == 3:
            self.model = f"{parts[0]}-{parts[1]}"
            digits = parts[2].lstrip("0")
            try:
                self.version = f"{float(digits) / 100:.2f}"
            except ValueError:
                pass
        _LOGGER.debug("KingSong name %r -> model %s, version %s", name, self.model, self.version)

    def _battery_percent(self, voltage: float) -> float:
        model = self.model or ""
        volts, percents = self.DEFAULT_CURVE
        for prefix, curve_v, curve_p in self.BATTERY_CURVES:
            if model.startswith(prefix):
                volts, percents = curve_v, curve_p
                break
        if voltage < volts[0]:
            return float(percents[0])
        if voltage > volts[-1]:
            return float(percents[-1])
        for i in range(len(volts) - 1):
            if voltage <= volts[i + 1]:
                span = volts[i + 1] - volts[i]
                pct = percents[i] + (voltage - volts[i]) * (percents[i + 1] - percents[i]) / span
                # EUC World rounds half up (fc/e.java h()).
                return float(math.floor(pct + 0.5))
        return float(percents[-1])

    def _series_cells(self) -> int:
        model = self.model or ""
        for prefix, cells in self.SERIES_CELLS:
            if model.startswith(prefix):
                return cells
        return self.DEFAULT_SERIES


class GotwayDecoder(EucDecoder):
    """Decoder for Gotway/Begode wheels, following EUC World 2.68.0 (wh/s.java).

    The wheel streams 24-byte frames unprompted. Its voltage field is always
    scaled as if the pack were 16S (67.2 V); the real voltage needs the wheel
    model's full-pack voltage, which EUC World takes from its model table
    (gotway_models.py). The model is matched from the wheel's answers to the
    single-byte "N" (name) and "V" (firmware) requests sent after connecting.
    Until a model is known, voltage, battery percent and system voltage are
    None and only the 67.2 V-scaled ``raw_voltage`` is reported, as EUC World
    does (it shows no voltage without a model).

    EUC World exposes no charging flag or battery charging current for this
    protocol, so ``is_charging``/``charging_current`` are None (unknown).
    """

    # Raw 0.01 V reading -> pack voltage, keyed by int(full voltage) (wh/s.java).
    # Models not listed (67.2 V, 126 V) are used unscaled.
    VOLTAGE_RATIOS = {
        42: 0.625, 84: 1.25, 100: 1.5, 134: 2.0,
        151: 2.25, 168: 2.5, 210: 3.125, 252: 3.75,
    }
    REQUEST_NAME = b"N"
    REQUEST_FIRMWARE = b"V"
    PROBE_FIRST_DELAY = 0.25   # wh/s.java e(): first "N" 250 ms after connect
    PROBE_TIMEOUT = 1.5        # gi/j, gi/l: retry timer A1 posted for 1500 ms
    PROBE_STEP_DELAY = 0.1     # B()/C(): next request posted after 100 ms
    PROBE_ATTEMPTS = 2         # B()/C(): counter set to 2, decremented per timeout
    NAME_RE = re.compile(rb"NAME:(.*)")
    FIRMWARE_RE = re.compile(rb"^(GW|JL|JN|CF)\d{7}")

    request_interval = 0.05

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = GotwayUnpacker()
        self._clock = time.monotonic
        self.wheel_name: Optional[str] = None
        self.firmware: Optional[str] = None
        self.model: Optional[GotwayModel] = None
        self._model_forced = False
        self.trip_distance: Optional[float] = None
        self.total_distance: Optional[float] = None
        self.reset_session()

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.GOTWAY

    # --- model selection -------------------------------------------------

    def set_model(self, name: str) -> bool:
        """Select a model from the table by its EUC World name (manual override)."""
        for model in GOTWAY_MODELS:
            if model.name == name:
                self.model = model
                self._model_forced = True
                return True
        return False

    def _match_model(self) -> None:
        """Pick the model by wheel name, else by firmware string (EUC World order)."""
        if self._model_forced:
            return
        if self.wheel_name is not None:
            for model in GOTWAY_MODELS:
                if any(re.fullmatch(p, self.wheel_name) for p in model.match_by_name):
                    self.model = model
                    _LOGGER.info("Gotway wheel name %r matched model %s", self.wheel_name, model.name)
                    return
        if self.firmware is not None:
            for model in GOTWAY_MODELS:
                if any(re.fullmatch(p, self.firmware) for p in model.match_by_firmware):
                    self.model = model
                    _LOGGER.info("Gotway firmware %r matched model %s", self.firmware, model.name)
                    return
        _LOGGER.info(
            "No Gotway model matches name %r / firmware %r; voltage and battery "
            "percent are unavailable (raw 67.2 V-scaled voltage is still reported)",
            self.wheel_name, self.firmware,
        )

    # --- name / firmware probe --------------------------------------------

    def reset_session(self) -> None:
        """Restart the name/firmware probe (EUC World does this on every connect)."""
        self._probe = "name"
        self._attempts_left = self.PROBE_ATTEMPTS
        self._next_send = self._clock() + self.PROBE_FIRST_DELAY
        self._deadline: Optional[float] = None

    def get_requests(self) -> list[bytes]:
        """Send "N", then "V", each retried once after 1.5 s without an answer."""
        if self._probe == "done":
            return []
        now = self._clock()
        if self._deadline is not None:
            if now < self._deadline:
                return []
            self._deadline = None
            self._attempts_left -= 1
            if self._attempts_left <= 0:
                # Timed out twice: EUC World gives up and goes straight to live data
                # (a failed name probe skips the firmware probe too).
                self._finish_probe()
                return []
            self._next_send = now
        if now < self._next_send:
            return []
        self._deadline = now + self.PROBE_TIMEOUT
        return [self.REQUEST_NAME if self._probe == "name" else self.REQUEST_FIRMWARE]

    def _finish_probe(self) -> None:
        self._probe = "done"
        self._match_model()

    def _handle_probe_reply(self, data: bytes) -> None:
        if self._probe == "name":
            match = self.NAME_RE.search(data)
            if match:
                self.wheel_name = match.group(1).decode("latin-1")
                _LOGGER.debug("Gotway wheel name: %s", self.wheel_name)
                self._probe = "firmware"
                self._attempts_left = self.PROBE_ATTEMPTS
                self._deadline = None
                self._next_send = self._clock() + self.PROBE_STEP_DELAY
        elif self._probe == "firmware":
            match = self.FIRMWARE_RE.match(data)
            if match:
                self.firmware = match.group(0).decode("latin-1")
                _LOGGER.debug("Gotway firmware: %s", self.firmware)
                self._finish_probe()

    # --- frames -------------------------------------------------------------

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode BLE notification data."""
        if not data:
            return None
        if self._probe != "done":
            self._handle_probe_reply(data)

        result = None
        for frame in self.unpacker.add_data(data):
            decoded = self._decode_frame(frame)
            if decoded:
                result = decoded
        return result

    def _decode_frame(self, buff: bytes) -> Optional[dict[str, Any]]:
        """Decode one 24-byte frame. Only type 0 (live data) produces output."""
        frame_type = buff[18]
        model = self.model
        distance_ratio = model.distance_correction if model else 1.0
        if frame_type == 0x04:
            # Total distance: unsigned 32-bit BE metres at offset 2.
            self.total_distance = struct.unpack(">I", buff[2:6])[0] * 0.001 * distance_ratio
            return None
        if frame_type != 0x00:
            return None

        speed_raw = struct.unpack(">h", buff[4:6])[0] * 0.036
        raw_voltage = struct.unpack(">H", buff[2:4])[0] * 0.01
        phase_current = struct.unpack(">h", buff[10:12])[0] * 0.01
        # Java int division: getShort(12) / 340 truncates before adding 36.53.
        temp_raw = struct.unpack(">h", buff[12:14])[0]
        temperature = int(temp_raw / 340) + 36.53
        if not (
            40.0 <= raw_voltage <= 72.0
            and -200.0 <= speed_raw <= 200.0
            and -300.0 <= phase_current <= 300.0
            and -20.0 <= temperature <= 90.0
        ):
            _LOGGER.debug("Gotway frame out of range, dropped: %s", buff.hex())
            self.error_count += 1
            return None

        speed = abs(speed_raw) * (model.speed_correction if model else 1.0)
        self.trip_distance = struct.unpack(">H", buff[8:10])[0] * 0.001 * distance_ratio
        # EUC World's current metric: phase current signed by direction of travel.
        current = (1.0 if speed_raw > 0 else -1.0 if speed_raw < 0 else 0.0) * phase_current

        voltage = battery_percent = system_voltage = None
        if model:
            system_voltage = model.full_voltage
            voltage = raw_voltage * self.VOLTAGE_RATIOS.get(int(model.full_voltage), 1.0)
            battery_percent = self._battery_percent(voltage, model)

        self.packet_count += 1
        model_name = model.name if model else "Gotway"
        manufacturer = (model.make if model and model.make else "Begode")
        return {
            "voltage": round(voltage, 2) if voltage is not None else None,
            "raw_voltage": round(raw_voltage, 2),
            "speed": round(speed, 2),
            "trip_distance": round(self.trip_distance, 3),
            "total_distance": (
                round(self.total_distance, 3) if self.total_distance is not None else None
            ),
            "current": round(current, 2),
            "temperature": round(temperature, 2),
            "battery_percent": battery_percent,
            "is_charging": None,
            "charging_current": None,
            "charging_power": None,
            "battery_current": None,
            "model": model_name,
            "version": self.firmware,
            "manufacturer": manufacturer,
            "system_voltage": system_voltage,
        }

    # EUC World's default (battery_level = 0) Gotway curves, keyed by
    # int(full voltage): (volts, percent) points (zh/a.java tables B..J,
    # selected in e() - confirmed in the fallback decompilation).
    BATTERY_CURVES: dict[int, tuple[tuple[float, ...], tuple[float, ...]]] = {
        42: ((33.25, 40.9375), (0, 100)),
        67: ((53.2, 65.5), (0, 100)),
        84: ((66.5, 81.875), (0, 100)),
        100: ((79.8, 98.25), (0, 100)),
        134: ((106.4, 131.0), (0, 100)),
        151: ((119.7, 147.4), (0, 100)),
        168: ((133.0, 163.75), (0, 100)),
        210: ((166.25, 204.6875), (0, 100)),
        252: ((199.5, 245.625), (0, 100)),
    }

    @classmethod
    def _battery_percent(cls, voltage: float, model: GotwayModel) -> Optional[float]:
        """EUC World's default battery level for the model's pack voltage."""
        curve = cls.BATTERY_CURVES.get(int(model.full_voltage))
        if curve is None:
            return None   # e.g. a 126 V pack: EUC World has no curve either
        return euc_world_curve_percent(voltage, *curve)


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

    request_interval = 0.025  # keepalive every 25 ms

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

    request_interval = 0.025  # keepalive every 25 ms

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




# --- Ninebot One (S2/A1/C/E/P) and Ninebot One Z, per EUC World 2.68.0 ---------
#
# Both protocols are strict request/response: the wheel only answers register
# reads, so the decoder drives a state machine (get_requests) and decodes the
# replies. Sources: yh/a.java (55 AA, One S2/A1 family), yh/b.java (5A A5, One Z),
# wh/b0.java (serial-prefix model table), sh/m.java (which register is which
# metric). Field names in comments are EUC World metric keys.

# Serial number prefix -> model (wh/b0.java x()).
NINEBOT_SERIAL_MODELS = {
    "N1OC": "One C", "N1OE": "One E", "N1OP": "One P",
    "N2OA": "One A1", "N2OC": "One C+", "N2OE": "One E+", "N2OP": "One P",
    "N2OS": "One S2",
    "N3OL": "One Z6", "N3OS": "One Z8", "N3OT": "One Z10",
}


def _ninebot_checksum(body: bytes) -> bytes:
    """0xFFFF minus the byte sum, little-endian (yh/a.java w(), yh/b.java x())."""
    return struct.pack("<H", (0xFFFF - sum(body)) & 0xFFFF)


def _ninebot_version(raw: int) -> Optional[str]:
    """Firmware word -> "a.b.c"; 0 means no such component (wh/b0.java w())."""
    if raw <= 0:
        return None
    return f"{(raw >> 8) & 15}.{(raw >> 4) & 15}.{raw & 15}"


class _NinebotBase(EucDecoder):
    """Shared request state machine and register decoding for both variants."""

    HEADER: bytes = b""
    # name -> (addr, argtype, cmd, data); data is the number of bytes to read.
    REQUESTS: dict[str, tuple[int, int, int, bytes]] = {}
    INIT_SEQUENCE: tuple[str, ...] = ()
    SPEED_SCALE = 0.001
    BATTERY_CURRENT_SIGNED = True
    MAINBOARD_NEEDS_BATTERY = True   # yh/a.java case 24 vs yh/b.java case 26
    CELLS = 15
    VARIANT = "Ninebot"
    RESPONSE_TIMEOUT = 0.25          # 250 ms per request (field z)

    request_interval = 0.02

    def __init__(self) -> None:
        super().__init__()
        self._clock = time.monotonic
        self.reset_session()

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.NINEBOT

    # --- framing (overridden for Z) ---------------------------------------

    def _build_frame(self, name: str) -> bytes:
        raise NotImplementedError

    def _extract_frame(self) -> Optional[tuple[bytes, bytes]]:
        """Return (raw, plain) for one complete valid frame in the buffer, if any."""
        raise NotImplementedError

    def _payload(self, plain: bytes) -> bytes:
        raise NotImplementedError

    def _matches_pending(self, plain: bytes) -> bool:
        raise NotImplementedError

    # --- session / state machine ------------------------------------------

    def reset_session(self) -> None:
        """Start the init handshake from scratch (EUC World e()/g())."""
        self._buffer = bytearray()
        self._pending: Optional[str] = None
        self._deadline = 0.0
        self._last: Optional[str] = None
        self._initialising = True
        self._cycle = -1
        self.has_battery_1 = False
        self.has_battery_2 = False
        self.version: Optional[str] = None
        self.serial: Optional[str] = None
        self.model: Optional[str] = None
        self._general_seen = False
        self._values: dict[str, Any] = {}
        self._batteries: dict[int, dict[str, Any]] = {}

    def get_requests(self) -> list[bytes]:
        """Send the next request once the previous one is answered or timed out."""
        now = self._clock()
        if self._pending is not None:
            if now < self._deadline:
                return []
            _LOGGER.debug("%s request %s timed out", self.VARIANT, self._pending)
            self._buffer.clear()
            if self._initialising:
                # Init commands are retried until answered (dc/p.java timeout handler).
                return [self._send(self._pending, now)]
            self._last = self._pending
        name = self._next_request()
        return [self._send(name, now)]

    def _send(self, name: str, now: float) -> bytes:
        self._pending = name
        self._deadline = now + self.RESPONSE_TIMEOUT
        return self._build_frame(name)

    def _cycle_general(self) -> str:
        self._cycle = (self._cycle + 1) % 7
        return "READ_GENERAL"

    def _finish_init(self) -> str:
        self._initialising = False
        return "READ_GENERAL"

    def _next_request(self) -> str:
        """EUC World's next-request choice after `self._last` (yh/a.java z())."""
        last, cyc = self._last, self._cycle
        b1, b2 = self.has_battery_1, self.has_battery_2
        seq = self.INIT_SEQUENCE
        if last is None:
            return seq[0]
        if last in seq[:-1]:
            return seq[seq.index(last) + 1]
        if last == seq[-1]:   # INIT_ACTIVATION_DATE
            if b1:
                return "INIT_BATTERY_1"
            if b2:
                return "INIT_BATTERY_2"
            return self._finish_init()
        nxt = {
            "INIT_BATTERY_1": "INIT_BATTERY_1_HEALTH",
            "INIT_BATTERY_1_HEALTH": "INIT_BATTERY_1_MFG_DATE",
            "INIT_BATTERY_2": "INIT_BATTERY_2_HEALTH",
            "INIT_BATTERY_2_HEALTH": "INIT_BATTERY_2_MFG_DATE",
            "READ_GENERAL": "READ_SPEED_RANGE",
            "READ_SPEED_RANGE": "READ_TILT_ROLL",
        }.get(last)
        if nxt:
            return nxt
        if last == "INIT_BATTERY_1_MFG_DATE":
            return "INIT_BATTERY_2" if b2 else self._finish_init()
        if last == "INIT_BATTERY_2_MFG_DATE":
            return self._finish_init()
        first = cyc == -1
        if last == "READ_TILT_ROLL":
            if cyc in (-1, 0):
                return "READ_INVERTER"
            if cyc == 1:
                return "READ_MAINBOARD"
            if cyc == 2:
                return "READ_CONFIG"
            if b1 and cyc == 3:
                return "READ_BATTERY_1"
            if b2 and cyc == 4:
                return "READ_BATTERY_2"
            if b1 and cyc == 5:
                return "READ_BATTERY_1_CELLS"
            if b2 and cyc == 6:
                return "READ_BATTERY_2_CELLS"
            return self._cycle_general()
        follow = {
            "READ_INVERTER": ("READ_MAINBOARD", first),
            "READ_MAINBOARD": (
                "READ_CONFIG", first and (b1 or not self.MAINBOARD_NEEDS_BATTERY)
            ),
            "READ_CONFIG": ("READ_BATTERY_1", first and b1),
            "READ_BATTERY_1": ("READ_BATTERY_1_CELLS", first and b1),
            "READ_BATTERY_1_CELLS": ("READ_BATTERY_2", first and b2),
            "READ_BATTERY_2": ("READ_BATTERY_2_CELLS", first and b2),
            "READ_BATTERY_2_CELLS": (None, False),
        }.get(last)
        if follow is not None:
            target, ok = follow
            return target if ok else self._cycle_general()
        return "READ_GENERAL"

    # --- receive -------------------------------------------------------------

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Feed a BLE chunk; return the telemetry after each answered request."""
        if not data:
            return None
        self._buffer.extend(data)
        result = None
        while True:
            frame = self._extract_frame()
            if frame is None:
                break
            raw, plain = frame
            if self._pending is None or not self._matches_pending(plain):
                continue
            name = self._pending
            try:
                self._handle_response(name, raw, self._payload(plain))
            except (struct.error, IndexError) as ex:
                _LOGGER.debug("%s: bad %s response: %s", self.VARIANT, name, ex)
                self.error_count += 1
            self._last = name
            self._pending = None
            self._buffer.clear()
            self.packet_count += 1
            if self._general_seen:
                result = self._telemetry()
        return result

    def _handle_response(self, name: str, raw: bytes, p: bytes) -> None:
        if name == "INIT_FIRMWARE_MAINBOARD":
            self.version = _ninebot_version(struct.unpack_from("<H", p, 0)[0])
        elif name == "INIT_FIRMWARE_OTHER":
            # Battery firmware words; a zero word means that pack is absent.
            self.has_battery_1 = _ninebot_version(struct.unpack_from("<H", p, 0)[0]) is not None
            self.has_battery_2 = _ninebot_version(struct.unpack_from("<H", p, 2)[0]) is not None
        elif name == "INIT_KEY":
            self._set_key(raw)
        elif name == "INIT_SERIAL":
            self.serial = p.decode("ascii", errors="replace").rstrip("\x00")
            self.model = NINEBOT_SERIAL_MODELS.get(self.serial[:4])
        elif name == "READ_GENERAL":
            v = self._values
            v["battery_percent"] = float(struct.unpack_from("<H", p, 8)[0])        # vba
            v["speed"] = struct.unpack_from("<H", p, 10)[0] * self.SPEED_SCALE      # vsp
            v["total_distance"] = struct.unpack_from("<I", p, 14)[0] * 0.001        # km
            v["trip_distance"] = struct.unpack_from("<H", p, 18)[0] * 0.01          # km
            v["voltage"] = struct.unpack_from("<H", p, 24)[0] * 0.01
            v["current"] = struct.unpack_from("<h", p, 26)[0] * 0.01
            self._general_seen = True
        elif name == "READ_INVERTER":
            self._values["temperature"] = struct.unpack_from("<h", p, 0)[0] * 0.1    # vte
        elif name in ("READ_BATTERY_1", "READ_BATTERY_2"):
            status = struct.unpack_from("<H", p, 0)[0]
            fmt = "<h" if self.BATTERY_CURRENT_SIGNED else "<H"
            self._batteries[1 if name.endswith("1") else 2] = {
                "charging": bool(status & 0x40),                               # vbch
                "percent": struct.unpack_from("<H", p, 4)[0],                  # vb1
                "current": struct.unpack_from(fmt, p, 6)[0] * 0.01,            # vcb1
                "voltage": struct.unpack_from("<H", p, 8)[0] * 0.01,           # vvb1
                "temperature": p[11] - 20,                                     # vteb1
            }

    def _set_key(self, raw: bytes) -> None:
        """Only Ninebot Z has a key exchange."""

    def _telemetry(self) -> dict[str, Any]:
        v = self._values
        packs = [self._batteries[i] for i in (1, 2) if i in self._batteries]
        is_charging: Optional[bool] = None
        battery_current = charging_current = charging_power = None
        if packs:
            # EUC World: charging if either pack's status bit 6 is set (sh/m.java).
            is_charging = any(pack["charging"] for pack in packs)
            battery_current = round(sum(pack["current"] for pack in packs), 2)
            if is_charging:
                # Sign convention of the pack current while charging is not shown
                # by EUC World, so report the magnitude.
                charging_current = round(abs(battery_current), 2)
            else:
                charging_current = 0.0
            if v.get("voltage") is not None:
                charging_power = round(charging_current * v["voltage"], 1)
        return {
            "voltage": round(v["voltage"], 2) if "voltage" in v else None,
            "speed": round(v["speed"], 3) if "speed" in v else None,
            "trip_distance": round(v["trip_distance"], 2) if "trip_distance" in v else None,
            "total_distance": round(v["total_distance"], 3) if "total_distance" in v else None,
            "current": round(v["current"], 2) if "current" in v else None,
            "temperature": round(v["temperature"], 1) if "temperature" in v else None,
            "battery_percent": v.get("battery_percent"),
            "is_charging": is_charging,
            "battery_current": battery_current,
            "charging_current": charging_current,
            "charging_power": charging_power,
            "model": self.model or self.VARIANT,
            "serial": self.serial,
            "version": self.version,
            "manufacturer": "Ninebot",
            "system_voltage": None,
        }


class NinebotDecoder(_NinebotBase):
    """Ninebot One S2/A1/C/E/P: 55 AA frames, plaintext (yh/a.java).

    Frame: 55 AA len addr argtype cmd data... chk_lo chk_hi, len = data + 2,
    checksum = 0xFFFF - sum(bytes[2:-2]). A response repeats the request's
    addr/argtype/cmd at bytes 3/4/5.
    """

    HEADER = bytes([0x55, 0xAA])
    REQUESTS = {
        "INIT_FIRMWARE_MAINBOARD": (0x11, 0x01, 0x1A, b"\x02"),
        "INIT_FIRMWARE_OTHER": (0x11, 0x01, 0x66, b"\x06"),
        "INIT_PASSWORD": (0x11, 0x01, 0x17, b"\x06"),
        "INIT_SERIAL": (0x11, 0x01, 0x10, b"\x0e"),
        "INIT_CONFIG": (0x11, 0x01, 0xD2, b"\x04"),
        "INIT_LEDS_MODE": (0x11, 0x01, 0xC6, b"\x02"),
        "INIT_SPEED_TILTBACK": (0x11, 0x01, 0x72, b"\x06"),
        "INIT_TRANSPORTATION_MODE": (0x11, 0x01, 0x9D, b"\x02"),
        "INIT_ACTIVATION_DATE": (0x11, 0x01, 0x69, b"\x02"),
        "INIT_BATTERY_1": (0x13, 0x01, 0x10, b"\x1a"),
        "INIT_BATTERY_1_HEALTH": (0x13, 0x01, 0x3B, b"\x02"),
        "INIT_BATTERY_1_MFG_DATE": (0x13, 0x01, 0x20, b"\x02"),
        "INIT_BATTERY_2": (0x14, 0x01, 0x10, b"\x1a"),
        "INIT_BATTERY_2_HEALTH": (0x14, 0x01, 0x3B, b"\x02"),
        "INIT_BATTERY_2_MFG_DATE": (0x14, 0x01, 0x20, b"\x02"),
        "READ_GENERAL": (0x11, 0x01, 0xB0, b"\x20"),
        "READ_SPEED_RANGE": (0x11, 0x01, 0x25, b"\x0c"),
        "READ_TILT_ROLL": (0x11, 0x01, 0x61, b"\x04"),
        "READ_INVERTER": (0x11, 0x01, 0x3E, b"\x02"),
        "READ_MAINBOARD": (0x11, 0x01, 0x43, b"\x0a"),
        "READ_CONFIG": (0x11, 0x01, 0xD2, b"\x04"),
        "READ_BATTERY_1": (0x13, 0x01, 0x30, b"\x0e"),
        "READ_BATTERY_2": (0x14, 0x01, 0x30, b"\x0e"),
        "READ_BATTERY_1_CELLS": (0x13, 0x01, 0x40, b"\x1e"),
        "READ_BATTERY_2_CELLS": (0x14, 0x01, 0x40, b"\x1e"),
    }
    INIT_SEQUENCE = (
        "INIT_FIRMWARE_MAINBOARD", "INIT_FIRMWARE_OTHER", "INIT_PASSWORD",
        "INIT_SERIAL", "INIT_CONFIG", "INIT_LEDS_MODE", "INIT_SPEED_TILTBACK",
        "INIT_TRANSPORTATION_MODE", "INIT_ACTIVATION_DATE",
    )
    SPEED_SCALE = 0.001
    BATTERY_CURRENT_SIGNED = True
    MAINBOARD_NEEDS_BATTERY = True
    CELLS = 15
    VARIANT = "Ninebot One"

    def _build_frame(self, name: str) -> bytes:
        addr, arg, cmd, data = self.REQUESTS[name]
        body = bytes([len(data) + 2, addr, arg, cmd]) + data
        return self.HEADER + body + _ninebot_checksum(body)

    @staticmethod
    def is_valid_frame(frame: bytes) -> bool:
        """yh/a.java b.a(): size == len + 6, 55 AA header, checksum."""
        return (
            len(frame) > 7
            and frame[:2] == b"\x55\xaa"
            and len(frame) == frame[2] + 6
            and frame[-2:] == _ninebot_checksum(frame[2:-2])
        )

    def _extract_frame(self) -> Optional[tuple[bytes, bytes]]:
        buf = self._buffer
        while True:
            start = buf.find(self.HEADER)
            if start < 0:
                del buf[:max(0, len(buf) - 1)]
                return None
            del buf[:start]
            if len(buf) < 3:
                return None
            size = buf[2] + 6
            if len(buf) < size:
                return None
            frame = bytes(buf[:size])
            if self.is_valid_frame(frame):
                del buf[:size]
                return frame, frame
            del buf[:2]   # not a frame start; resync

    def _payload(self, plain: bytes) -> bytes:
        return plain[6:-2]

    def _matches_pending(self, plain: bytes) -> bool:
        addr, arg, cmd, _ = self.REQUESTS[self._pending]
        return plain[3] == addr and plain[4] == arg and plain[5] == cmd


class NinebotZDecoder(_NinebotBase):
    """Ninebot One Z6/Z8/Z10: 5A A5 frames XOR-encrypted with a session key (yh/b.java).

    Frame: 5A A5 len 3E addr argtype cmd data... chk_lo chk_hi, len = data,
    checksum = 0xFFFF - sum(bytes[2:-2]) over the plaintext. Every byte from
    index 3 on (checksum included) is XORed with key[(i - 3) % 16]. The key
    starts as 16 zero bytes and is replaced by bytes 7..22 of the wheel's
    reply to INIT_KEY (addr 0x16, argtype 0x5B, cmd 0x00). A response carries
    the request's addr at byte 3, 0x3E at byte 4 and its cmd at byte 6.
    """

    HEADER = bytes([0x5A, 0xA5])
    REQUESTS = {
        "INIT_FIRMWARE_MAINBOARD": (0x14, 0x01, 0x1A, b"\x02"),
        "INIT_FIRMWARE_OTHER": (0x14, 0x01, 0x66, b"\x06"),
        "INIT_KEY": (0x16, 0x5B, 0x00, b""),
        "INIT_SERIAL": (0x14, 0x01, 0x10, b"\x0e"),
        "INIT_CONFIG": (0x14, 0x01, 0xD2, b"\x04"),
        "INIT_LEDS_MODE": (0x14, 0x01, 0xC6, b"\x02"),
        "INIT_SPEAKER_VOLUME": (0x14, 0x01, 0xF5, b"\x02"),
        "INIT_SPEED_ALERTS": (0x14, 0x01, 0x7C, b"\x08"),
        "INIT_SPEED_TILTBACK": (0x14, 0x01, 0x72, b"\x06"),
        "INIT_ACTIVATION_DATE": (0x14, 0x01, 0x69, b"\x02"),
        "INIT_BATTERY_1": (0x11, 0x01, 0x10, b"\x1a"),
        "INIT_BATTERY_1_HEALTH": (0x11, 0x01, 0x3B, b"\x02"),
        "INIT_BATTERY_1_MFG_DATE": (0x11, 0x01, 0x20, b"\x02"),
        "INIT_BATTERY_2": (0x12, 0x01, 0x10, b"\x1a"),
        "INIT_BATTERY_2_HEALTH": (0x12, 0x01, 0x3B, b"\x02"),
        "INIT_BATTERY_2_MFG_DATE": (0x12, 0x01, 0x20, b"\x02"),
        "READ_GENERAL": (0x14, 0x01, 0xB0, b"\x20"),
        "READ_SPEED_RANGE": (0x14, 0x01, 0x25, b"\x0c"),   # READ_SPEED_DIST
        "READ_TILT_ROLL": (0x14, 0x01, 0x61, b"\x04"),
        "READ_INVERTER": (0x14, 0x01, 0x3E, b"\x02"),
        "READ_MAINBOARD": (0x14, 0x01, 0x43, b"\x0a"),
        "READ_CONFIG": (0x14, 0x01, 0xD2, b"\x04"),
        "READ_BATTERY_1": (0x11, 0x01, 0x30, b"\x0e"),
        "READ_BATTERY_2": (0x12, 0x01, 0x30, b"\x0e"),
        "READ_BATTERY_1_CELLS": (0x11, 0x01, 0x40, b"\x1e"),
        "READ_BATTERY_2_CELLS": (0x12, 0x01, 0x40, b"\x1e"),
    }
    INIT_SEQUENCE = (
        "INIT_FIRMWARE_MAINBOARD", "INIT_FIRMWARE_OTHER", "INIT_KEY", "INIT_SERIAL",
        "INIT_CONFIG", "INIT_LEDS_MODE", "INIT_SPEAKER_VOLUME", "INIT_SPEED_ALERTS",
        "INIT_SPEED_TILTBACK", "INIT_ACTIVATION_DATE",
    )
    SPEED_SCALE = 0.01
    BATTERY_CURRENT_SIGNED = False
    MAINBOARD_NEEDS_BATTERY = False
    CELLS = 14
    VARIANT = "Ninebot One Z"

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.NINEBOT_Z

    def reset_session(self) -> None:
        super().reset_session()
        self.key = bytes(16)

    def crypt(self, frame: bytes) -> bytes:
        """XOR bytes 3.. with the session key (symmetric; yh/b.java w())."""
        out = bytearray(frame)
        for i in range(3, len(out)):
            out[i] ^= self.key[(i - 3) % 16]
        return bytes(out)

    def _build_frame(self, name: str) -> bytes:
        addr, arg, cmd, data = self.REQUESTS[name]
        body = bytes([len(data), 0x3E, addr, arg, cmd]) + data
        return self.crypt(self.HEADER + body + _ninebot_checksum(body))

    @staticmethod
    def is_valid_plain_frame(frame: bytes) -> bool:
        """yh/b.java b.a(): size == len + 9, 5A A5 header, checksum (plaintext)."""
        return (
            len(frame) > 8
            and frame[:2] == b"\x5a\xa5"
            and len(frame) == frame[2] + 9
            and frame[-2:] == _ninebot_checksum(frame[2:-2])
        )

    def _extract_frame(self) -> Optional[tuple[bytes, bytes]]:
        buf = self._buffer
        while True:
            start = buf.find(self.HEADER)
            if start < 0:
                del buf[:max(0, len(buf) - 1)]
                return None
            del buf[:start]
            if len(buf) < 3:
                return None
            size = buf[2] + 9   # header and length byte are never encrypted
            if len(buf) < size:
                return None
            raw = bytes(buf[:size])
            plain = self.crypt(raw)
            if self.is_valid_plain_frame(plain):
                del buf[:size]
                return raw, plain
            del buf[:2]

    def _payload(self, plain: bytes) -> bytes:
        return plain[7:-2]

    def _matches_pending(self, plain: bytes) -> bool:
        addr, _, cmd, _ = self.REQUESTS[self._pending]
        return plain[3] == addr and plain[4] == 0x3E and plain[6] == cmd

    def _set_key(self, raw: bytes) -> None:
        # Copied from the undecrypted reply bytes 7..22 (yh/b.java h(), case 3).
        self.key = bytes(raw[7:23])


def get_decoder_by_data(data: bytes) -> Optional[EucDecoder]:
    """Factory to create the correct decoder based on initial packet header.
    
    Detects protocol by examining packet headers with minimum length requirements:
    - DC 5A 5C [len]: Veteran/Leaperkim (min 4 bytes)
    - AA 55: KingSong (20-byte packets, command at byte 16, 0xA9 = live data)
    - 55 AA: Gotway/Begode, which streams frames unprompted; a chunk that is a
      complete checksum-valid Ninebot One frame is Ninebot instead (Ninebot
      only ever answers requests, so it is normally chosen by BLE name before
      any data arrives - see the coordinator)
    - DC 5A [flags]: InMotion V2 (min 3 bytes, flags=0x11/0x14)
    - AA AA [len] [cmd]: InMotion V1 (min 4 bytes, CAN-style)
    - 5A A5 [len] [cmd]: Ninebot Z (min 4 bytes, Z-series header)
    """
    if len(data) < 2:
        return None
    
    # 55 AA: Ninebot One if the chunk is a whole valid Ninebot frame, else Gotway.
    if len(data) >= 4 and data[0] == 0x55 and data[1] == 0xAA:
        if NinebotDecoder.is_valid_frame(bytes(data)):
            _LOGGER.debug("Detected Ninebot One protocol (valid 55 AA frame)")
            return NinebotDecoder()
        _LOGGER.debug("Detected Gotway/Begode protocol (55 AA header)")
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
    
    # KingSong: every packet starts AA 55 (wh/z.java h()); no other protocol does.
    if len(data) >= 4 and data[0] == 0xAA and data[1] == 0x55:
        _LOGGER.debug("Detected KingSong protocol (AA 55 header)")
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
