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
    def has_pending_requests(self) -> bool:
        """True while the protocol still has (or may soon have) something to send.

        The coordinator polls slowly once this is False (e.g. Gotway/KingSong
        after their one-off model probe).
        """
        return self.get_keepalive_packet() is not None

    # Pause between the pieces split_write() returns.
    write_chunk_delay: float = 0.0

    def split_write(self, packet: bytes) -> list[bytes]:
        """Split a request into the GATT writes EUC World makes (default: one)."""
        return [packet]

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


# --- Experimental charging inference ---------------------------------------------
# KingSong, Gotway/Begode and InMotion V1 send no charging flag that EUC World
# uses, so charging is inferred from what they do send. These are heuristics of
# this integration, not EUC World behaviour, hence "experimental".

CHARGE_STATIONARY_KMH = 1.0       # below this the wheel counts as standing still
CHARGE_MOVING_KMH = 2.0           # at/above this the wheel is moving: not charging
CHARGE_SETTLE_S = 900.0           # ignore voltage for 15 min after riding (pack rebound)
CHARGE_VOLTAGE_RISE_V = 0.3       # pack voltage rise that means charging ...
CHARGE_VOLTAGE_WINDOW_S = 600.0   # ... within this window (10 min)
CHARGE_NEW_HIGH_V = 0.05          # a new high must beat the peak by this much ...
CHARGE_VOLTAGE_STALL_S = 600.0    # ... and charging ends after none for 10 min
CHARGE_CURRENT_A = -0.5           # current below this while stationary ...
CHARGE_CURRENT_SUSTAIN_S = 60.0   # ... for this long means charging

METHOD_FLAG = "flag"
METHOD_INFERRED_CURRENT = "inferred_current"
METHOD_INFERRED_VOLTAGE = "inferred_voltage"


class ChargingInference:
    """Infer charging from stationary voltage rise and, optionally, negative current.

    * Voltage rule: standing still, at least 15 minutes after the last riding
      (so the pack's post-ride voltage rebound isn't mistaken for charging),
      and the pack voltage is >= 0.3 V above its lowest value in the last
      10 minutes -> charging. It stays charging until no new high (>= 0.05 V
      above the peak) has been seen for 10 minutes.
    * Current rule (``use_current``): standing still with current < -0.5 A for
      60 s -> charging (negative current while moving is regen, ignored). Not
      gated by the settle time.
    * Either rule active -> charging. Moving (>= 2 km/h) -> not charging. With
      a full 10-minute stationary window and neither rule active -> not
      charging. Until then the state is unknown (None).
    """

    def __init__(self, use_current: bool, clock=time.monotonic) -> None:
        self.use_current = use_current
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        self._history: list[tuple[float, float]] = []   # (time, voltage) while stationary
        self._window_start: Optional[float] = None        # first accepted stationary sample
        self._peak: Optional[float] = None
        self._peak_time: Optional[float] = None
        self._negative_since: Optional[float] = None
        self._last_moving: Optional[float] = None
        self.is_charging: Optional[bool] = None
        self.method: Optional[str] = None

    def restart_voltage_history(self) -> None:
        """Drop voltage evidence (e.g. the voltage scale changed); keep motion/current state."""
        self._history.clear()
        self._window_start = None
        self._peak = self._peak_time = None

    def update(
        self, voltage: Optional[float], speed: Optional[float], current: Optional[float] = None
    ) -> tuple[Optional[bool], Optional[str]]:
        """Feed one live sample; return (is_charging, charging_method)."""
        if voltage is None or speed is None:
            return self.is_charging, self.method
        now = self._clock()
        if abs(speed) >= CHARGE_MOVING_KMH:
            self._history.clear()
            self._window_start = None
            self._peak = self._peak_time = None
            self._negative_since = None
            self._last_moving = now
            return self._set(False, METHOD_INFERRED_VOLTAGE)
        if abs(speed) >= CHARGE_STATIONARY_KMH:
            return self.is_charging, self.method   # 1-2 km/h: hold (hysteresis)

        # Voltage rule (skipped while the pack settles after a ride)
        voltage_active = False
        settling = self._last_moving is not None and now - self._last_moving < CHARGE_SETTLE_S
        if not settling:
            if self._window_start is None:
                self._window_start = now
            self._history.append((now, voltage))
            self._history = [
                (t, v) for t, v in self._history if now - t <= CHARGE_VOLTAGE_WINDOW_S
            ]
            lowest = min(v for _, v in self._history)
            if self._peak is None:
                if voltage - lowest >= CHARGE_VOLTAGE_RISE_V:
                    self._peak, self._peak_time = voltage, now
            elif voltage >= self._peak + CHARGE_NEW_HIGH_V:
                self._peak, self._peak_time = voltage, now
            if self._peak_time is not None and now - self._peak_time >= CHARGE_VOLTAGE_STALL_S:
                self._peak = self._peak_time = None
            voltage_active = self._peak_time is not None

        # Current rule
        current_active = False
        if self.use_current and current is not None:
            if current < CHARGE_CURRENT_A:
                if self._negative_since is None:
                    self._negative_since = now
                current_active = now - self._negative_since >= CHARGE_CURRENT_SUSTAIN_S
            else:
                self._negative_since = None

        if current_active:
            return self._set(True, METHOD_INFERRED_CURRENT)
        if voltage_active:
            return self._set(True, METHOD_INFERRED_VOLTAGE)
        if (
            self.is_charging
            or self._last_moving is not None
            or (self._window_start is not None
                and now - self._window_start >= CHARGE_VOLTAGE_WINDOW_S)
        ):
            return self._set(False, METHOD_INFERRED_VOLTAGE)
        return self.is_charging, self.method

    def _set(self, charging: bool, method: str) -> tuple[bool, str]:
        self.is_charging, self.method = charging, method
        return charging, method


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
    ROCKW_CURVE = ((60.0, 83.0), (0.0, 100.0))

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
        self.charging_status_raw: Optional[int] = None
        self.charging = ChargingInference(use_current=True, clock=lambda: self._clock())
        self.reset_session()

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.KINGSONG

    def reset_session(self) -> None:
        """Re-request the wheel name after every connect."""
        self._name_answered = False
        self.charging.reset()
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

    @property
    def has_pending_requests(self) -> bool:
        return not self._name_answered

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
            # "chargingStatus" (wh/z.java, 0xB9 byte 13): parsed by EUC World but
            # not shown; exposed raw for diagnostics only.
            self.charging_status_raw = buff[13]
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

        is_charging, charging_method = self.charging.update(voltage, speed, current)
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
            "is_charging": is_charging,
            "charging_method": charging_method,
            "charging_status_raw": self.charging_status_raw,
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
        """EUC World default: BMS average (not decoded here) else model curve.

        A wheel whose name starts "ROCKW" (rebadged GT16) uses the 60-83 V
        curve before any model match (zh/a.java e(), fallback decompilation).
        """
        model = self.model or ""
        volts, percents = self.DEFAULT_CURVE
        if (self.wheel_name or "").startswith("ROCKW"):
            volts, percents = self.ROCKW_CURVE
        else:
            for prefix, curve_v, curve_p in self.BATTERY_CURVES:
                if model.startswith(prefix):
                    volts, percents = curve_v, curve_p
                    break
        return euc_world_curve_percent(voltage, volts, percents)

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
    NAME_RE = re.compile(rb"NAME:([^\r\n]*)")
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
        # Voltage rule only: Gotway's current is zeroed at standstill (wh/s.java Y0).
        self.charging = ChargingInference(use_current=False, clock=lambda: self._clock())
        self._inference_scale: Optional[float] = None
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

    # Series cell counts offered for a custom pack: those whose full voltage
    # (cells x 4.2 V) EUC World has a voltage ratio or curve for (int(full)).
    CUSTOM_PACK_CELLS = (10, 16, 20, 24, 32, 36, 40, 50, 60)

    def set_custom_pack(self, cells: int) -> None:
        """Manual override with only the pack size known (cells in series)."""
        full = round(cells * 4.2, 1)
        self.model = GotwayModel(f"Custom {cells}S", None, full, None, 1.0, 1.0, (), ())
        self._model_forced = True

    def clear_model_override(self) -> None:
        """Back to auto-detection: re-match from the probed name/firmware."""
        if not self._model_forced:
            return
        self._model_forced = False
        self.model = None
        if self._probe == "done":
            self._match_model()

    @property
    def model_unmatched(self) -> bool:
        """Probe finished (or gave up) and no model was matched or set."""
        return self._probe == "done" and self.model is None

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
        self.charging.reset()
        self._attempts_left = self.PROBE_ATTEMPTS
        self._next_send = self._clock() + self.PROBE_FIRST_DELAY
        self._deadline: Optional[float] = None

    @property
    def has_pending_requests(self) -> bool:
        return self._probe != "done"

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

        # Real pack voltage when the model is known, else the 67.2 V-scaled raw
        # value (a smaller but still monotonic rise while charging). Never mix
        # the two in one window: a model match/override mid-session changes the
        # scale, so the voltage history restarts.
        scale = model.full_voltage if model else None
        if scale != self._inference_scale:
            self._inference_scale = scale
            self.charging.restart_voltage_history()
        is_charging, charging_method = self.charging.update(
            voltage if voltage is not None else raw_voltage, speed
        )
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
            "is_charging": is_charging,
            "charging_method": charging_method,
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


# --- InMotion V1 (V5/V8/V10/Glide 3 family), per EUC World 2.68.0 (wh/v.java) ---

# Car-type id (status reply byte 104, prefixed by byte 107 when > 0) -> model.
INMOTION_V1_MODELS = {
    0: "R1N", 1: "R1S", 2: "R1CF", 3: "R1AP", 4: "R1EX", 6: "R1T", 7: "R10",
    10: "V3", 11: "V3C", 12: "V3PRO", 13: "V3S", 20: "R2", 21: "R2N", 22: "R2S",
    24: "R2EX", 30: "R0", 50: "V5", 51: "V5+", 52: "V5F", 53: "V5F+", 60: "L6",
    61: "Lively", 80: "V8", 85: "Solowheel Glide 3", 86: "V8F", 87: "V8S",
    100: "V10S", 101: "V10SF", 140: "V10", 141: "V10F", 142: "V10T", 143: "V10FT",
}


class InMotionDecoder(EucDecoder):
    """InMotion V1 (CAN-over-BLE) decoder, following EUC World (wh/v.java).

    Request (21 bytes, written to FFE9): AA AA, request id (int32 LE) at 2,
    data at 6..13 (eight 0xFF when none), data length at 14 (0xFE = none),
    0x05 at 15, frame format at 16 (0 standard), type at 17 (0 data,
    1 remote), byte-sum checksum of bytes 2..17 at 18, 55 55. EUC World does
    not escape requests.

    Reply: a notification starting AA AA restarts the buffer; the frame is
    complete when it is longer than 20 bytes and ends 55 55. 0xA5 escapes the
    next byte. The byte at len-3 is the sum of bytes 2..len-4; the id must
    match the pending request. Extended frames (byte 14 = 0xFE, byte 16 != 0)
    carry their payload in bytes 18..len-4.

    Sequence: INIT_PASSWORD -> INIT_STATUS, then READ_VALUES / READ_STATUS
    alternately, one request 50 ms after each reply, 500 ms timeout (init
    requests retried; afterwards up to 3 consecutive timeouts are skipped).
    EUC World reads no charging flag or battery percent for V1: battery
    percent is its default curve (68 V 0 %, 74.5 V 50 %, 82.5 V 100 %).
    """

    # name -> (request id, type: 0 data / 1 remote, default data)
    REQUESTS = {
        "INIT_PASSWORD": (257229575, 0, bytes([48, 48, 48, 48, 48, 48, 0, 0])),
        "INIT_STATUS": (257229076, 1, None),
        "READ_VALUES": (257229075, 0, None),
        "READ_STATUS": (257229076, 1, None),
    }
    DEFAULT_PASSWORD = "000000"   # EUC World default when none is configured
    SEND_DELAY = 0.05             # Y = 50 ms
    RESPONSE_TIMEOUT = 0.5        # X = 500 ms
    MAX_SKIPPED_TIMEOUTS = 3
    BATTERY_CURVE = ((68.0, 74.5, 82.5), (0.0, 50.0, 100.0))   # zh/a.java K
    SYSTEM_VOLTAGE = 84.0         # gauge max 85 V = 20 x 4.25 (zh/a.java b())

    request_interval = 0.02
    has_pending_requests = True   # request/response for the whole session

    def __init__(self) -> None:
        super().__init__()
        self._clock = time.monotonic
        self.password = self.DEFAULT_PASSWORD
        self.charging = ChargingInference(use_current=True, clock=lambda: self._clock())
        self.reset_session()

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.INMOTION

    def reset_session(self) -> None:
        self._buffer = bytearray()
        self._pending: Optional[str] = None
        self._last: Optional[str] = None
        self._initialising = True
        self._timeouts = 0
        self._deadline = 0.0
        self._next_send = self._clock()
        self._first = True
        self.model: Optional[str] = None
        self.version: Optional[str] = None
        self.serial: Optional[str] = None
        self._values: dict[str, Any] = {}
        self.charging.reset()
        # Per-connection evidence for the wrong-password check.
        self.password_sent = False
        self.values_received = False

    write_chunk_delay = 0.02     # Thread.sleep(20) between full pieces

    def split_write(self, packet: bytes) -> list[bytes]:
        """FFE9 writes as EUC World makes them (ui/a.java, fallback decompilation).

        Full 20-byte pieces, then the remainder copied into the start of the
        same reused 20-byte buffer, which is written whole - so the last write
        is always 20 bytes, its tail repeating the previous piece. Replicated
        byte-for-byte because that is what is known to work with real wheels.
        """
        if len(packet) <= 20:
            return [packet]
        pieces, buf = [], bytearray(20)
        full = len(packet) // 20
        for i in range(full):
            buf[:] = packet[i * 20:(i + 1) * 20]
            pieces.append(bytes(buf))
        rest = packet[full * 20:]
        if rest:
            buf[:len(rest)] = rest
            pieces.append(bytes(buf))
        return pieces

    @classmethod
    def build_request(cls, name: str, data: Optional[bytes]) -> bytes:
        req_id, req_type, _ = cls.REQUESTS[name]
        frame = bytearray(21)
        if data is None:
            frame[6:14] = b"\xff" * 8
            frame[14] = 0xFE
        else:
            frame[6:6 + len(data)] = data
            frame[14] = len(data)
        frame[0:2] = b"\xaa\xaa"
        struct.pack_into("<i", frame, 2, req_id)
        frame[15] = 5
        frame[16] = 0
        frame[17] = req_type
        frame[18] = sum(frame[2:18]) & 0xFF
        frame[19] = frame[20] = 0x55
        return bytes(frame)

    def get_requests(self) -> list[bytes]:
        now = self._clock()
        if self._pending is not None:
            if now < self._deadline:
                return []
            self._timeouts += 1
            if self._initialising or self._timeouts > self.MAX_SKIPPED_TIMEOUTS:
                # Retry with the request's data (wh/t.java). EUC World resends
                # INIT_PASSWORD with its default "000000\0\0"; with a custom
                # password we resend that instead, never the default.
                data = self.REQUESTS[self._pending][2]
                if self._pending == "INIT_PASSWORD":
                    data = self.password_bytes() + b"\x00\x00"
                return [self._send(self._pending, data, now)]
            self._last = self._pending
            self._pending = None
            self._next_send = now
        if now < self._next_send:
            return []
        if self._first:
            self._first = False
            self.password_sent = True
            return [self._send("INIT_PASSWORD", self.password_bytes(), now)]
        name = {
            "INIT_PASSWORD": "INIT_STATUS",
            "INIT_COMM": "INIT_STATUS",
            "READ_VALUES": "READ_STATUS",
        }.get(self._last or "", "READ_VALUES")
        if self._last == "INIT_STATUS":
            self._initialising = False
        return [self._send(name, self.REQUESTS[name][2], now)]

    def password_bytes(self) -> bytes:
        """Password as EUC World sends it: first 6 chars, '0'-padded to 6 (wh/v.java e())."""
        return (self.password or self.DEFAULT_PASSWORD).ljust(6, "0")[:6].encode("ascii", "replace")

    def _send(self, name: str, data: Optional[bytes], now: float) -> bytes:
        self._pending = name
        self._deadline = now + self.RESPONSE_TIMEOUT
        return self.build_request(name, data)

    @staticmethod
    def unescape(frame: bytes) -> bytes:
        out = bytearray()
        escaped = False
        for b in frame:
            if b == 0xA5 and not escaped:
                escaped = True
                continue
            out.append(b)
            escaped = False
        return bytes(out)

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        if not data:
            return None
        if data[:2] == b"\xaa\xaa":
            self._buffer.clear()
        self._buffer.extend(data)
        buf = bytes(self._buffer)
        if not (buf[:2] == b"\xaa\xaa" and len(buf) > 20 and buf[-2:] == b"\x55\x55"):
            return None
        frame = self.unescape(buf)
        if len(frame) < 21 or (sum(frame[2:-3]) & 0xFF) != frame[-3]:
            return None
        req_id = struct.unpack_from("<i", frame, 2)[0]
        if self._pending is None or self.REQUESTS[self._pending][0] != req_id:
            return None
        name = self._pending
        self._pending = None
        self._last = name
        self._timeouts = 0
        self._next_send = self._clock() + self.SEND_DELAY
        self._buffer.clear()
        length, fmt = frame[14], frame[16]
        if length == 0xFE and fmt != 0:
            payload = frame[18:-3]
        elif length < 9 and fmt == 0:
            payload = frame[6:6 + length]
        else:
            payload = b""
        try:
            if name in ("INIT_STATUS", "READ_STATUS"):
                self._parse_status(payload)
            elif name == "READ_VALUES":
                self._parse_values(payload)
                self.values_received = True
                self.packet_count += 1
                return self._telemetry()
        except (struct.error, IndexError) as ex:
            _LOGGER.debug("InMotion V1: bad %s reply: %s", name, ex)
            self.error_count += 1
        return None

    def _parse_status(self, p: bytes) -> None:
        self.serial = f"{struct.unpack_from('<q', p, 0)[0]:08X}"
        self.version = f"{p[27]}.{p[26]}.{struct.unpack_from('<H', p, 24)[0]}"
        if 104 < len(p):
            hi = struct.unpack_from("b", p, 107)[0]
            lo = struct.unpack_from("b", p, 104)[0]
            car_type = int(f"{hi}{lo}") if hi > 0 else lo
            self.model = INMOTION_V1_MODELS.get(car_type)

    def _parse_values(self, p: bytes) -> None:
        v = self._values
        a, b = struct.unpack_from("<ii", p, 12)
        v["speed"] = abs(a + b) * 3.6 / 7624.0
        # sh/m.java e() feeds v.V (offset 24, widened unsigned by k1.e) into the
        # voltage metric "vvo" and v.L (offset 20, signed) into current "vca";
        # zh/a.java's V1 battery curve and sag model also take v.V as voltage.
        v["voltage"] = struct.unpack_from("<I", p, 24)[0] * 0.01
        v["current"] = struct.unpack_from("<i", p, 20)[0] * 0.01
        v["temperature"] = float(struct.unpack_from("b", p, 32)[0])
        v["trip_distance"] = struct.unpack_from("<I", p, 44)[0] * 0.001
        v["total_distance"] = struct.unpack_from("<I", p, 48)[0] * 0.001

    def _telemetry(self) -> dict[str, Any]:
        v = self._values
        is_charging, charging_method = self.charging.update(
            v["voltage"], v["speed"], v["current"]
        )
        return {
            "voltage": round(v["voltage"], 2),
            "speed": round(v["speed"], 2),
            "trip_distance": round(v["trip_distance"], 3),
            "total_distance": round(v["total_distance"], 3),
            "current": round(v["current"], 2),
            "temperature": v["temperature"],
            "battery_percent": euc_world_curve_percent(v["voltage"], *self.BATTERY_CURVE),
            "is_charging": is_charging,
            "charging_method": charging_method,
            "charging_current": None,
            "charging_power": None,
            "battery_current": None,
            "model": self.model or "InMotion",
            "version": self.version,
            "serial": self.serial,
            "manufacturer": "InMotion",
            "system_voltage": self.SYSTEM_VOLTAGE,
        }


# --- InMotion V2 (V9/V11/V11Y/V12/V12S/V13/V14/E20/P6), per EUC World 2.68.0 ---
# ("InmotionNewAdapter", wh/w.java; request sequencer X() from the fallback
# decompilation.)

# INIT_ID reply byte 3 -> (model, series cells from EUC World's gauge maximum,
# zh/a.java b(): max / 4.25). Unknown ids are treated as V12, as EUC World does.
INMOTION_V2_MODELS = {
    6: "V11", 7: "V12", 8: "V13", 9: "V14", 10: "E20", 11: "V12S", 12: "V9", 13: "P6",
}
INMOTION_V2_SERIES = {
    "V11": 20, "V11Y": 20, "V12": 24, "V12S": 20, "V13": 30, "V14": 32,
    "V9": 20, "E20": 13, "P6": 56,
}


class InMotionV2Decoder(EucDecoder):
    """InMotion V2 decoder, following EUC World (wh/w.java).

    Frame: AA AA cmd len data xor, where xor is the XOR of every byte before
    it. 0xA5 escapes the next byte in replies; EUC World does not escape
    requests. A reply's payload is bytes 4..len-2 of the unescaped frame.

    Sequence (one request per reply, 1000 ms timeout, init retried):
    INIT_ID (0x11 02 01) -> INIT_SERIAL (0x11 02 02) -> INIT_FIRMWARE
    (0x11 02 06) -> INIT_SETTINGS (0x14 20 20) -> pack serials (0x16 02 24..27
    04, P6/V9/V11Y/V12S/V13/V14 only) -> READ_VALUES (0x14 04) -> READ_TRIP
    (0x14 10 00 01) -> READ_TOTAL (0x14 11) -> READ_BATTERY (0x14 05) or a
    pack status/voltage read (0x16 02 2x 01/02) -> READ_VALUES ...

    Live values are parsed per model (and, for the V11, per firmware): battery
    percent is the wheel's own value and charging is bit 7 of the status flags,
    as EUC World does.
    """

    # name -> (cmd, data)
    REQUESTS: dict[str, tuple[int, bytes]] = {
        "INIT_ID": (0x11, bytes([2, 1])),
        "INIT_SERIAL": (0x11, bytes([2, 2])),
        "INIT_FIRMWARE": (0x11, bytes([2, 6])),
        "INIT_SETTINGS": (0x14, bytes([32, 32])),
        "INIT_BATTERY_1_SERIAL": (0x16, bytes([2, 36, 4])),
        "INIT_BATTERY_2_SERIAL": (0x16, bytes([2, 37, 4])),
        "INIT_BATTERY_3_SERIAL": (0x16, bytes([2, 38, 4])),
        "INIT_BATTERY_4_SERIAL": (0x16, bytes([2, 39, 4])),
        "READ_VALUES": (0x14, bytes([4])),
        "READ_TRIP": (0x14, bytes([16, 0, 1])),
        "READ_TOTAL": (0x14, bytes([17])),
        "READ_BATTERY": (0x14, bytes([5])),
        "READ_BATTERY_1_STATUS": (0x16, bytes([2, 36, 1])),
        "READ_BATTERY_1_VOLTAGES": (0x16, bytes([2, 36, 2])),
        "READ_BATTERY_2_STATUS": (0x16, bytes([2, 37, 1])),
        "READ_BATTERY_2_VOLTAGES": (0x16, bytes([2, 37, 2])),
        "READ_BATTERY_3_STATUS": (0x16, bytes([2, 38, 1])),
        "READ_BATTERY_3_VOLTAGES": (0x16, bytes([2, 38, 2])),
        "READ_BATTERY_4_STATUS": (0x16, bytes([2, 39, 1])),
        "READ_BATTERY_4_VOLTAGES": (0x16, bytes([2, 39, 2])),
    }
    PACK_MODELS = ("P6", "V9", "V13", "V14", "V11Y", "V12S")
    PACK_ROTATION_2 = ("READ_BATTERY_1_STATUS", "READ_BATTERY_1_VOLTAGES",
                       "READ_BATTERY_2_STATUS", "READ_BATTERY_2_VOLTAGES")
    PACK_ROTATION_4 = PACK_ROTATION_2 + (
        "READ_BATTERY_3_STATUS", "READ_BATTERY_3_VOLTAGES",
        "READ_BATTERY_4_STATUS", "READ_BATTERY_4_VOLTAGES")
    RESPONSE_TIMEOUT = 1.0
    # Replies EUC World checks before accepting an init step (wh/w.java h()).
    INIT_REPLY_PREFIX = {
        "INIT_ID": b"\x82\x01", "INIT_SERIAL": b"\x82\x02", "INIT_FIRMWARE": b"\x82\x06",
        "INIT_SETTINGS": b"\xa0\x20",
        "INIT_BATTERY_1_SERIAL": b"\x24\x02\x84", "INIT_BATTERY_2_SERIAL": b"\x25\x02\x84",
        "INIT_BATTERY_3_SERIAL": b"\x26\x02\x84", "INIT_BATTERY_4_SERIAL": b"\x27\x02\x84",
    }

    request_interval = 0.02
    has_pending_requests = True   # request/response for the whole session

    def __init__(self) -> None:
        super().__init__()
        self._clock = time.monotonic
        self.reset_session()

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.INMOTION_V2

    def reset_session(self) -> None:
        self._buffer = bytearray()
        self._pending: Optional[str] = None
        self._last: Optional[str] = None
        self._deadline = 0.0
        self._initialising = True
        self._pack_index = 0
        self.model: Optional[str] = None
        self.serial: Optional[str] = None
        self.firmware: Optional[str] = None
        self._values: dict[str, Any] = {}

    @classmethod
    def build_frame(cls, cmd: int, data: bytes) -> bytes:
        frame = bytearray([0xAA, 0xAA, cmd, len(data)]) + data
        chk = 0
        for b in frame:
            chk ^= b
        return bytes(frame + bytes([chk]))

    # --- requests -------------------------------------------------------------

    def get_requests(self) -> list[bytes]:
        now = self._clock()
        if self._pending is not None:
            if now < self._deadline:
                return []
            if self._initialising:
                return [self._send(self._pending, now)]   # gi/p.java -> Y()
            self._last = self._pending
        return [self._send(self._next_request(), now)]

    def _send(self, name: str, now: float) -> bytes:
        self._pending = name
        self._deadline = now + self.RESPONSE_TIMEOUT
        self._buffer.clear()
        return self.build_frame(*self.REQUESTS[name])

    def _finish_init(self) -> str:
        self._initialising = False
        return "READ_VALUES"

    def _next_request(self) -> str:
        """wh/w.java X(): next request after `self._last`."""
        last, model = self._last, self.model
        if last is None:
            return "INIT_ID"
        simple = {
            "INIT_ID": "INIT_SERIAL",
            "INIT_SERIAL": "INIT_FIRMWARE",
            "INIT_FIRMWARE": "INIT_SETTINGS",
            "INIT_BATTERY_1_SERIAL": "INIT_BATTERY_2_SERIAL",
            "INIT_BATTERY_3_SERIAL": "INIT_BATTERY_4_SERIAL",
            "READ_VALUES": "READ_TRIP",
            "READ_TRIP": "READ_TOTAL",
        }
        if last in simple:
            return simple[last]
        if last == "INIT_SETTINGS":
            return "INIT_BATTERY_1_SERIAL" if model in self.PACK_MODELS else self._finish_init()
        if last == "INIT_BATTERY_2_SERIAL":
            return "INIT_BATTERY_3_SERIAL" if model == "V14" else self._finish_init()
        if last == "INIT_BATTERY_4_SERIAL":
            return self._finish_init()
        if last == "READ_TOTAL":
            if model == "V14":
                rotation = self.PACK_ROTATION_4
            elif model in self.PACK_MODELS:
                rotation = self.PACK_ROTATION_2
            else:
                return "READ_BATTERY"
            name = rotation[self._pack_index % len(rotation)]
            self._pack_index = (self._pack_index + 1) % len(rotation)
            return name
        return "READ_VALUES"

    # --- replies --------------------------------------------------------------

    @staticmethod
    def unescape(data: bytes) -> bytes:
        return InMotionDecoder.unescape(data)

    @staticmethod
    def checksum_ok(frame: bytes) -> bool:
        """wh/w.java Z(): more than 5 bytes, XOR of all but last == last."""
        if len(frame) <= 5:
            return False
        chk = 0
        for b in frame[:-1]:
            chk ^= b
        return chk == frame[-1]

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        if not data:
            return None
        self._buffer.extend(data)
        frame = self.unescape(bytes(self._buffer))
        if not self.checksum_ok(frame):
            return None
        self._buffer.clear()
        if self._pending is None:
            return None
        name = self._pending
        payload = frame[4:-1]
        prefix = self.INIT_REPLY_PREFIX.get(name)
        if prefix is not None and not payload.startswith(prefix):
            # Unexpected reply to an init step: resend it (wh/w.java Y()).
            self._deadline = 0.0
            return None
        self._pending = None
        self._last = name
        result = None
        try:
            result = self._handle(name, payload)
        except (struct.error, IndexError) as ex:
            _LOGGER.debug("InMotion V2: bad %s reply: %s", name, ex)
            self.error_count += 1
        return result

    def _handle(self, name: str, p: bytes) -> Optional[dict[str, Any]]:
        if name == "INIT_ID":
            model_id, variant = p[3], p[4]
            model = INMOTION_V2_MODELS.get(model_id)
            if model is None:
                _LOGGER.warning("Unknown InMotion model id %d; assuming V12 (as EUC World)", model_id)
                model = "V12"
            if model == "V11" and variant == 2:
                model = "V11Y"
            self.model = model
        elif name == "INIT_SERIAL":
            self.serial = p[2:23].decode("ascii", "replace").strip("\x00")
        elif name == "INIT_FIRMWARE":
            # E0(12): byte 15 . byte 14 . int16 @12 (main board firmware)
            self.firmware = f"{struct.unpack_from('b', p, 15)[0]}.{struct.unpack_from('b', p, 14)[0]}.{struct.unpack_from('<h', p, 12)[0]}"
        elif name == "READ_VALUES":
            if p[:1] == b"\x84" and self.model is not None:
                if self._parse_values(p):
                    self.packet_count += 1
                    return self._telemetry()
        elif name == "READ_TRIP":
            if p[:1] == b"\x90":
                self._values["trip_distance"] = struct.unpack_from("<I", p, 23)[0] * 0.01
        elif name == "READ_TOTAL":
            if p[:1] == b"\x91":
                self._values["total_distance"] = struct.unpack_from("<I", p, 1)[0] * 0.01
        return None

    @staticmethod
    def _temp(p: bytes, offset: int, previous: Optional[float]) -> Optional[float]:
        """wh/w.java C0(): signed byte + 80; 0 and -80 mean "no sensor" until a reading."""
        raw = struct.unpack_from("b", p, offset)[0]
        if previous is not None or raw not in (0, -80):
            return float(raw + 80)
        return None

    @staticmethod
    def _fw_at_least(firmware: Optional[str], minimum: str) -> bool:
        if firmware is None:
            return False
        try:
            have = [int(x) for x in firmware.split(".")]
            want = [int(x) for x in minimum.split(".")]
        except ValueError:
            return False
        for a, b in zip(have, want):
            if a != b:
                return a > b
        return len(have) >= len(want)

    def _parse_values(self, p: bytes) -> bool:
        """Per-model live layouts (wh/w.java H/I/K/M/N/P/R/T/V). LE throughout."""
        v = self._values
        s16 = lambda o: struct.unpack_from("<h", p, o)[0]   # noqa: E731
        model = self.model
        v["voltage"] = s16(1) * 0.01
        v["current"] = s16(3) * 0.01
        if model in ("V12", "E20"):                     # P(), H()
            v["speed"] = abs(s16(5)) * 0.01
            v["battery_percent"] = s16(25) * 0.01
            v["temperature"] = self._temp(p, 41, v.get("temperature"))
            flags = struct.unpack_from("<i", p, 55)[0]
            v["is_charging"] = bool(flags & 0x80)
        elif model == "V11":                             # K(), firmware-dependent
            v["speed"] = abs(s16(5)) * 0.01
            fw = self.firmware
            if fw is None:
                return True     # EUC World parses nothing more until firmware is known
            if self._fw_at_least(fw, "1.4.0"):
                v["battery_percent"] = s16(29) * 0.01
                v["temperature"] = float(struct.unpack_from("b", p, 43)[0] + 80)
                v["is_charging"] = bool(struct.unpack_from("<i", p, 57)[0] & 0x80)
            else:
                v["battery_percent"] = float(p[17] & 0x7F)
                v["temperature"] = float(struct.unpack_from("b", p, 21)[0] + 80)
                flag_offset = 39 if self._fw_at_least(fw, "1.2.22") else 37
                v["is_charging"] = bool(p[flag_offset] & 0x80)
        else:                                            # V(): V9, P6, V12S, V11Y, V13, V14
            v["speed"] = abs(s16(9)) * 0.01
            v["battery_percent"] = struct.unpack_from("<H", p, 35)[0] * 0.01
            v["temperature"] = self._temp(p, 59, v.get("temperature"))
            flags = struct.unpack_from("<i", p, 75)[0]
            v["is_charging"] = bool(flags & 0x80)
        return True

    def _telemetry(self) -> dict[str, Any]:
        v = self._values
        voltage = v.get("voltage")
        is_charging = v.get("is_charging")
        charging_current = charging_power = None
        if is_charging is not None:
            # Sign of the current while charging isn't shown by EUC World; use magnitude.
            charging_current = round(abs(v["current"]), 2) if is_charging else 0.0
            if voltage is not None:
                charging_power = round(charging_current * voltage, 1)
        battery = v.get("battery_percent")
        series = INMOTION_V2_SERIES.get(self.model or "")
        return {
            "voltage": round(voltage, 2) if voltage is not None else None,
            "speed": round(v["speed"], 2) if "speed" in v else None,
            "trip_distance": round(v["trip_distance"], 2) if "trip_distance" in v else None,
            "total_distance": round(v["total_distance"], 2) if "total_distance" in v else None,
            "current": round(v["current"], 2) if "current" in v else None,
            "temperature": v.get("temperature"),
            "battery_percent": round(battery, 2) if battery is not None else None,
            "is_charging": is_charging,
            "charging_method": METHOD_FLAG if is_charging is not None else None,
            "battery_current": round(v["current"], 2) if "current" in v else None,
            "charging_current": charging_current,
            "charging_power": charging_power,
            "model": self.model or "InMotion",
            "version": self.firmware,
            "serial": self.serial,
            "manufacturer": "InMotion",
            "system_voltage": round(series * 4.2, 1) if series else None,
        }


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
    has_pending_requests = True   # request/response for the whole session

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
            "charging_method": METHOD_FLAG if is_charging is not None else None,
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
    - AA AA ... xor: InMotion V2 when the chunk is a whole XOR-checksummed frame
    - AA AA: InMotion V1 (request/response; normally chosen by BLE name)
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
    
    # InMotion V1 (AA AA ... 55 55) and V2 (AA AA cmd len data xor) only
    # answer requests, so they are normally preselected by BLE name.
    if len(data) >= 4 and data[0] == 0xAA and data[1] == 0xAA:
        if InMotionV2Decoder.checksum_ok(InMotionV2Decoder.unescape(bytes(data))):
            _LOGGER.debug("Detected InMotion V2 protocol (AA AA, XOR checksum)")
            return InMotionV2Decoder()
        _LOGGER.debug("Detected InMotion V1 protocol (AA AA header)")
        return InMotionDecoder()
    
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
