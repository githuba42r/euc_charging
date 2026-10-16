"""InMotion V1 decoder tests against EUC World 2.68.0's adapter (wh/v.java).

SYNTHETIC DATA: no InMotion hardware was available. A simulated wheel answers
each request with a frame built byte-for-byte from the layout EUC World
validates and parses (AA AA, int32 id, extended payload from byte 18, byte-sum
checksum at len-3, 55 55 trailer, 0xA5 escaping). Expected values are what
EUC World's arithmetic gives for those bytes.
"""

import struct

import pytest

from euc_charging.decoders import InMotionDecoder, get_decoder_by_data

READ_VALUES_ID = 257229075
STATUS_ID = 257229076
PASSWORD_ID = 257229575


def escape(body: bytes) -> bytes:
    out = bytearray()
    for b in body:
        if b in (0xAA, 0x55, 0xA5):
            out.append(0xA5)
        out.append(b)
    return bytes(out)


def reply(req_id: int, payload: bytes, req_type: int = 0) -> bytes:
    """Extended reply: header, id, len 0xFE, format 1, payload @18, chk, 55 55."""
    frame = bytearray(18)
    frame[0:2] = b"\xaa\xaa"
    struct.pack_into("<i", frame, 2, req_id)
    struct.pack_into("<i", frame, 6, len(payload))
    frame[14] = 0xFE
    frame[15] = 5
    frame[16] = 1
    frame[17] = req_type
    frame += payload
    chk = sum(frame[2:]) & 0xFF
    body = bytes(frame[2:]) + bytes([chk])
    return b"\xaa\xaa" + escape(body) + b"\x55\x55"


def short_reply(req_id: int) -> bytes:
    frame = bytearray(21)
    frame[0:2] = b"\xaa\xaa"
    struct.pack_into("<i", frame, 2, req_id)
    frame[14] = 0
    frame[15] = 5
    frame[18] = sum(frame[2:18]) & 0xFF
    frame[19] = frame[20] = 0x55
    return bytes(frame)


def values_payload(voltage=8000, current=-150, temp=31, trip=12345, total=1234567, a=3812, b=3812):
    p = bytearray(64)
    struct.pack_into("<ii", p, 12, a, b)
    struct.pack_into("<i", p, 20, current)    # v.L -> "vca" current (sh/m.java e())
    struct.pack_into("<I", p, 24, voltage)    # v.V -> "vvo" voltage
    struct.pack_into("b", p, 32, temp)
    struct.pack_into("<I", p, 44, trip)
    struct.pack_into("<I", p, 48, total)
    return bytes(p)


def status_payload(car_hi=1, car_lo=40):
    p = bytearray(140)
    struct.pack_into("<q", p, 0, 0x12345678)
    struct.pack_into("<H", p, 24, 15)
    p[26] = 2
    p[27] = 1
    p[104] = car_lo
    p[107] = car_hi
    return bytes(p)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make():
    d = InMotionDecoder()
    d._clock = clock = FakeClock()
    d.reset_session()
    return d, clock


def feed(d, frame):
    out = None
    for i in range(0, len(frame), 20):
        out = d.decode(frame[i:i + 20]) or out
    return out


def test_password_request_bytes():
    d, _ = make()
    (req,) = d.get_requests()
    assert len(req) == 21
    assert req[:2] == b"\xaa\xaa" and req[-2:] == b"\x55\x55"
    assert struct.unpack_from("<i", req, 2)[0] == PASSWORD_ID
    assert req[6:12] == b"000000" and req[14] == 6 and req[15] == 5 and req[17] == 0
    assert req[18] == sum(req[2:18]) & 0xFF


def test_read_values_request_bytes():
    req = InMotionDecoder.build_request("READ_VALUES", None)
    assert req[6:14] == b"\xff" * 8 and req[14] == 0xFE and req[16] == 0
    assert struct.unpack_from("<i", req, 2)[0] == READ_VALUES_ID


def run_session(d, clock):
    sent, result = [], None
    for _ in range(6):
        clock.now += 0.06
        (req,) = d.get_requests()
        name = d._pending
        sent.append(name)
        req_id = struct.unpack_from("<i", req, 2)[0]
        if name == "INIT_PASSWORD":
            frame = short_reply(req_id)
        elif name in ("INIT_STATUS", "READ_STATUS"):
            frame = reply(req_id, status_payload(), 1)
        else:
            frame = reply(req_id, values_payload())
        result = feed(d, frame) or result
    return sent, result


def test_sequence_and_values():
    d, clock = make()
    sent, r = run_session(d, clock)
    assert sent == ["INIT_PASSWORD", "INIT_STATUS", "READ_VALUES", "READ_STATUS",
                    "READ_VALUES", "READ_STATUS"]
    assert r["voltage"] == pytest.approx(80.0)
    assert r["current"] == pytest.approx(-1.5)
    assert r["speed"] == pytest.approx(7624 * 3.6 / 7624)
    assert r["temperature"] == 31
    assert r["trip_distance"] == pytest.approx(12.345)
    assert r["total_distance"] == pytest.approx(1234.567)
    assert r["model"] == "V10"                       # "1" + "40" -> 140
    assert r["version"] == "1.2.15"
    assert r["serial"] == "12345678"
    # 80 V on EUC World's V1 curve (74.5 V 50 %, 82.5 V 100 %): 84.375 -> 84.
    assert r["battery_percent"] == 84
    assert r["system_voltage"] == pytest.approx(84.0)
    assert r["is_charging"] is False   # 3.6 km/h: moving -> inferred not charging


def test_escaped_bytes_in_reply():
    d, clock = make()
    run_session(d, clock)
    clock.now += 0.06
    d.get_requests()
    assert d._pending == "READ_VALUES"
    # 0xAA/0x55/0xA5 inside the payload are escaped on the wire.
    r = feed(d, reply(READ_VALUES_ID, values_payload(voltage=0x55AA)))
    assert r["voltage"] == pytest.approx(0x55AA * 0.01)


def test_bad_checksum_and_wrong_id_ignored():
    d, clock = make()
    clock.now += 0.06
    d.get_requests()
    bad = bytearray(short_reply(PASSWORD_ID))
    bad[18] ^= 1
    feed(d, bytes(bad))
    assert d._pending == "INIT_PASSWORD"
    feed(d, short_reply(STATUS_ID))
    assert d._pending == "INIT_PASSWORD"


def test_init_retried_and_later_timeouts_skipped():
    d, clock = make()
    first = d.get_requests()
    clock.now += 0.5
    assert len(d.get_requests()) == 1 and d._pending == "INIT_PASSWORD"   # retried
    d, clock = make()
    run_session(d, clock)
    clock.now += 0.06
    d.get_requests()                     # READ_VALUES, unanswered
    clock.now += 0.5
    d.get_requests()
    assert d._pending == "READ_STATUS"   # skipped after init


def test_detection():
    assert isinstance(get_decoder_by_data(short_reply(PASSWORD_ID)), InMotionDecoder)


def test_voltage_at_24_current_at_20():
    """sh/m.java e(): v.V (i32@24, unsigned-widened) -> "vvo" voltage; v.L (i32@20) -> "vca" current."""
    d, clock = make()
    run_session(d, clock)
    clock.now += 0.06
    d.get_requests()
    p = bytearray(values_payload())
    p[20:24] = (-2534).to_bytes(4, "little", signed=True)
    p[24:28] = (8412).to_bytes(4, "little")
    r = feed(d, reply(READ_VALUES_ID, bytes(p)))
    assert r["voltage"] == pytest.approx(84.12)
    assert r["current"] == pytest.approx(-25.34)
