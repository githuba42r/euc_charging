"""Ninebot One / One Z decoder tests against EUC World 2.68.0 (yh/a.java, yh/b.java).

SYNTHETIC DATA: no Ninebot hardware was available. A simulated wheel answers
each request with a frame built byte-for-byte from the layout EUC World
validates and parses (little-endian registers, 0xFFFF - sum checksum; One Z
frames XORed with the session key from INIT_KEY). Expected values are what
EUC World's arithmetic gives for those bytes.
"""

import struct

import pytest

from euc_charging.const import WheelBrand
from euc_charging.decoders import (
    NinebotDecoder,
    NinebotZDecoder,
    get_decoder_by_brand,
    get_decoder_by_data,
)


def checksum(body: bytes) -> bytes:
    return struct.pack("<H", (0xFFFF - sum(body)) & 0xFFFF)


def s2_frame(addr, arg, cmd, payload: bytes) -> bytes:
    body = bytes([len(payload) + 2, addr, arg, cmd]) + payload
    return b"\x55\xaa" + body + checksum(body)


def z_plain_response(addr, arg, cmd, payload: bytes) -> bytes:
    body = bytes([len(payload), addr, 0x3E, arg, cmd]) + payload
    return b"\x5a\xa5" + body + checksum(body)


def xor(frame: bytes, key: bytes) -> bytes:
    return frame[:3] + bytes(b ^ key[(i - 3) % 16] for i, b in enumerate(frame) if i >= 3)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


GENERAL = bytearray(32)
struct.pack_into("<H", GENERAL, 8, 87)            # battery 87 %
struct.pack_into("<H", GENERAL, 10, 12345)        # speed
struct.pack_into("<I", GENERAL, 14, 1234567)      # total 1234.567 km
struct.pack_into("<H", GENERAL, 18, 1234)         # trip 12.34 km
struct.pack_into("<H", GENERAL, 24, 5890)         # 58.90 V
struct.pack_into("<h", GENERAL, 26, -250)         # -2.50 A
GENERAL = bytes(GENERAL)


def battery(status: int, current_raw: int, signed=True) -> bytes:
    p = bytearray(14)
    struct.pack_into("<H", p, 0, status)
    struct.pack_into("<H", p, 4, 87)
    struct.pack_into("<h" if signed else "<H", p, 6, current_raw)
    struct.pack_into("<H", p, 8, 5880)
    p[11] = 45   # 25 C
    return bytes(p)


def s2_payload(name, charging=True):
    return {
        "INIT_FIRMWARE_MAINBOARD": struct.pack("<H", 0x0123),
        "INIT_FIRMWARE_OTHER": struct.pack("<HHH", 0x0111, 0, 0x0222),   # pack 1 only
        "INIT_SERIAL": b"N2OS1234567890",
        "READ_GENERAL": GENERAL,
        "READ_INVERTER": struct.pack("<h", 345),                        # 34.5 C
        "READ_BATTERY_1": battery(0x40 if charging else 0, -310),
    }.get(name, bytes(NinebotDecoder.REQUESTS[name][3][0]))


def run_s2(decoder, clock, steps, charging=True, answer=True):
    """Answer `steps` requests like a wheel; return (sent names, last telemetry)."""
    sent, result = [], None
    for _ in range(steps):
        packets = decoder.get_requests()
        assert len(packets) == 1
        name = decoder._pending
        sent.append(name)
        addr, arg, cmd, _ = NinebotDecoder.REQUESTS[name]
        assert packets[0] == s2_frame(addr, arg, cmd, NinebotDecoder.REQUESTS[name][3])
        if answer:
            reply = s2_frame(addr, arg, cmd, s2_payload(name, charging))
            out = None
            for i in range(0, len(reply), 20):           # 20-byte BLE chunks
                out = decoder.decode(reply[i:i + 20]) or out
            result = out or result
        clock.now += 0.01
    return sent, result


def make(cls):
    decoder = cls()
    decoder._clock = clock = FakeClock()
    decoder.reset_session()
    return decoder, clock


def test_s2_first_request_bytes():
    decoder, _ = make(NinebotDecoder)
    # 55 AA len=03 addr=11 read=01 cmd=1A data=02, checksum 0xFFFF-0x31 LE.
    assert decoder.get_requests() == [bytes.fromhex("55aa0311011a02ceff")]


def test_s2_init_sequence_then_round_robin():
    decoder, clock = make(NinebotDecoder)
    sent, _ = run_s2(decoder, clock, 22)
    assert sent == [
        "INIT_FIRMWARE_MAINBOARD", "INIT_FIRMWARE_OTHER", "INIT_PASSWORD",
        "INIT_SERIAL", "INIT_CONFIG", "INIT_LEDS_MODE", "INIT_SPEED_TILTBACK",
        "INIT_TRANSPORTATION_MODE", "INIT_ACTIVATION_DATE",
        "INIT_BATTERY_1", "INIT_BATTERY_1_HEALTH", "INIT_BATTERY_1_MFG_DATE",
        # first pass (cycle index -1) reads every register once
        "READ_GENERAL", "READ_SPEED_RANGE", "READ_TILT_ROLL", "READ_INVERTER",
        "READ_MAINBOARD", "READ_CONFIG", "READ_BATTERY_1", "READ_BATTERY_1_CELLS",
        # then GENERAL/SPEED/TILT plus one extra register per cycle
        "READ_GENERAL", "READ_SPEED_RANGE",
    ]
    assert decoder.has_battery_1 and not decoder.has_battery_2


def test_s2_decoded_values_and_charging_bit():
    decoder, clock = make(NinebotDecoder)
    _, result = run_s2(decoder, clock, 20, charging=True)
    assert result["battery_percent"] == 87
    assert result["voltage"] == pytest.approx(58.90)
    assert result["current"] == pytest.approx(-2.50)
    assert result["speed"] == pytest.approx(12.345)      # x0.001 on One S2
    assert result["total_distance"] == pytest.approx(1234.567)
    assert result["trip_distance"] == pytest.approx(12.34)
    assert result["temperature"] == pytest.approx(34.5)
    assert result["is_charging"] is True
    assert result["battery_current"] == pytest.approx(-3.10)
    assert result["charging_current"] == pytest.approx(3.10)
    assert result["charging_power"] == pytest.approx(round(3.10 * 58.90, 1))
    assert result["model"] == "One S2"
    assert result["serial"] == "N2OS1234567890"
    assert result["version"] == "1.2.3"


def test_s2_not_charging():
    decoder, clock = make(NinebotDecoder)
    _, result = run_s2(decoder, clock, 20, charging=False)
    assert result["is_charging"] is False
    assert result["charging_current"] == 0.0


def test_s2_charging_unknown_before_battery_read():
    decoder, clock = make(NinebotDecoder)
    _, result = run_s2(decoder, clock, 13)      # up to the first READ_GENERAL
    assert result["battery_percent"] == 87
    assert result["is_charging"] is None
    assert result["charging_current"] is None


def test_s2_init_request_retried_on_timeout():
    decoder, clock = make(NinebotDecoder)
    first = decoder.get_requests()
    clock.now += 0.1
    assert decoder.get_requests() == []          # still waiting
    clock.now += 0.2
    assert decoder.get_requests() == first       # 250 ms timeout -> resend
    assert decoder._pending == "INIT_FIRMWARE_MAINBOARD"


def test_s2_reply_for_other_register_ignored():
    decoder, _ = make(NinebotDecoder)
    decoder.get_requests()
    assert decoder.decode(s2_frame(0x11, 0x01, 0xB0, GENERAL)) is None
    assert decoder._pending == "INIT_FIRMWARE_MAINBOARD"


def test_s2_bad_checksum_rejected():
    decoder, _ = make(NinebotDecoder)
    decoder.get_requests()
    reply = bytearray(s2_frame(0x11, 0x01, 0x1A, struct.pack("<H", 0x0123)))
    reply[-1] ^= 0xFF
    decoder.decode(bytes(reply))
    assert decoder._pending == "INIT_FIRMWARE_MAINBOARD"


def test_s2_detection_by_valid_frame():
    frame = s2_frame(0x11, 0x01, 0x1A, struct.pack("<H", 0x0123))
    assert isinstance(get_decoder_by_data(frame), NinebotDecoder)


# --- Ninebot One Z -------------------------------------------------------------

KEY = bytes(range(0xA0, 0xB0))


def z_payload(name):
    if name == "INIT_FIRMWARE_OTHER":
        return struct.pack("<HHH", 0x0111, 0x0112, 0x0200)          # both packs
    if name == "INIT_SERIAL":
        return b"N3OT1234567890"
    if name == "INIT_KEY":
        return KEY
    if name == "READ_GENERAL":
        return GENERAL
    if name == "READ_INVERTER":
        return struct.pack("<h", 300)
    if name == "READ_BATTERY_1":
        return battery(0, 150, signed=False)
    if name == "READ_BATTERY_2":
        return battery(0x40, 160, signed=False)
    return bytes(NinebotZDecoder.REQUESTS[name][3][0]) if NinebotZDecoder.REQUESTS[name][3] else b""


def run_z(decoder, clock, steps):
    sent, result, wheel_key = [], None, bytes(16)
    for _ in range(steps):
        (packet,) = decoder.get_requests()
        name = decoder._pending
        sent.append(name)
        addr, arg, cmd, data = NinebotZDecoder.REQUESTS[name]
        # The wheel decrypts the request with its current key.
        body = bytes([len(data), 0x3E, addr, arg, cmd]) + data
        assert xor(packet, wheel_key) == b"\x5a\xa5" + body + checksum(body)
        reply = xor(z_plain_response(addr, arg, cmd, z_payload(name)), wheel_key)
        if name == "INIT_KEY":
            wheel_key = KEY
        out = None
        for i in range(0, len(reply), 20):
            out = decoder.decode(reply[i:i + 20]) or out
        result = out or result
        clock.now += 0.01
    return sent, result


def test_z_first_request_has_3e_marker_and_zero_key():
    decoder, _ = make(NinebotZDecoder)
    body = bytes([0x01, 0x3E, 0x14, 0x01, 0x1A, 0x02])
    assert decoder.get_requests() == [b"\x5a\xa5" + body + checksum(body)]


def test_z_key_exchange_and_encrypted_session():
    decoder, clock = make(NinebotZDecoder)
    sent, result = run_z(decoder, clock, 30)
    assert sent[:3] == ["INIT_FIRMWARE_MAINBOARD", "INIT_FIRMWARE_OTHER", "INIT_KEY"]
    assert sent[3:10] == [
        "INIT_SERIAL", "INIT_CONFIG", "INIT_LEDS_MODE", "INIT_SPEAKER_VOLUME",
        "INIT_SPEED_ALERTS", "INIT_SPEED_TILTBACK", "INIT_ACTIVATION_DATE",
    ]
    assert decoder.key == KEY
    assert "READ_BATTERY_2" in sent
    assert result["model"] == "One Z10"
    assert result["speed"] == pytest.approx(123.45)      # x0.01 on One Z
    assert result["voltage"] == pytest.approx(58.90)
    assert result["battery_percent"] == 87
    assert result["temperature"] == pytest.approx(30.0)
    # Pack 2 reports the charging bit; Z pack currents are unsigned.
    assert result["is_charging"] is True
    assert result["battery_current"] == pytest.approx(3.10)
    assert result["charging_current"] == pytest.approx(3.10)


def test_z_reconnect_resets_key():
    decoder, clock = make(NinebotZDecoder)
    run_z(decoder, clock, 4)
    assert decoder.key == KEY
    decoder.reset_session()
    assert decoder.key == bytes(16)
    assert decoder._pending is None


def test_z_detection_and_brand_factory():
    assert isinstance(get_decoder_by_data(bytes([0x5A, 0xA5, 0x03, 0x22])), NinebotZDecoder)
    assert isinstance(get_decoder_by_brand(WheelBrand.NINEBOT), NinebotDecoder)
    assert get_decoder_by_brand(WheelBrand.NINEBOT_Z).brand == WheelBrand.NINEBOT_Z
