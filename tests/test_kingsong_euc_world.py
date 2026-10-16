"""KingSong decoder tests against EUC World 2.68.0's parser (wh/z.java).

SYNTHETIC DATA: no KingSong hardware was available. Packets are built
byte-for-byte from the layout EUC World parses (20 bytes, AA 55 header,
little-endian fields, command at byte 16, 0x14 at 17, 5A 5A at 18-19) and the
expected values are what EUC World's arithmetic gives for those bytes.
"""

import struct

import pytest

from euc_charging.decoders import KingSongDecoder, get_decoder_by_data


def packet(command: int, data: bytes = b"") -> bytes:
    body = bytearray(20)
    body[0:2] = b"\xaa\x55"
    body[2:2 + len(data)] = data
    body[16] = command
    body[17] = 0x14
    body[18] = body[19] = 0x5A
    return bytes(body)


def live(voltage=8000, speed=0, total_m=0, current=0, temp=2500):
    data = struct.pack("<hhHHhh", voltage, speed, total_m >> 16, total_m & 0xFFFF, current, temp)
    return packet(0xA9, data)


def name(text: str) -> bytes:
    return packet(0xBB, text.encode().ljust(14, b"\x00"))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make():
    d = KingSongDecoder()
    d._clock = clock = FakeClock()
    d.reset_session()
    return d, clock


def test_live_fields_little_endian():
    d, _ = make()
    r = d.decode(live(voltage=8123, speed=2550, total_m=0x0001E240, current=-1234, temp=3456))
    assert r["voltage"] == pytest.approx(81.23)
    assert r["speed"] == pytest.approx(25.5)                 # already km/h x 0.01
    assert r["total_distance"] == pytest.approx(123.456)     # hi word @6, lo word @8
    assert r["current"] == pytest.approx(-12.34)
    assert r["temperature"] == pytest.approx(34.56)          # direct x 0.01 C
    # Moving at 25.5 km/h: the experimental inference says not charging.
    assert r["is_charging"] is False and r["charging_method"] == "inferred_voltage"
    assert r["charging_current"] is None


def test_total_distance_word_order():
    d, _ = make()
    # 70000 m = 0x00011170: hi=0x0001 at 6, lo=0x1170 at 8.
    raw = packet(0xA9, struct.pack("<hhHH", 8000, 0, 0x0001, 0x1170))
    assert d.decode(raw)["total_distance"] == pytest.approx(70.0)


def test_battery_unknown_until_name_answered():
    d, _ = make()
    assert d.decode(live())["battery_percent"] is None


def test_name_request_timing_and_retry():
    d, clock = make()
    assert d.get_requests() == []
    clock.now = 1.0
    req = d.get_requests()
    assert req == [bytes.fromhex("aa55" + "00" * 14 + "9b145a5a")]
    clock.now = 2.0
    assert d.get_requests() == []
    clock.now = 4.0
    assert d.get_requests() == req                           # 3 s retry
    d.decode(name("KS-S18-0205"))
    clock.now = 10.0
    assert d.get_requests() == []


def test_name_sets_model_version_curve_and_series():
    d, _ = make()
    d.decode(name("KS-S18-0205"))
    assert d.model == "KS-S18" and d.version == "2.05"
    r = d.decode(live(voltage=7150))                         # 71.5 V on 60..83 V
    assert r["model"] == "KS-S18"
    assert r["battery_percent"] == round((71.5 - 60) / 23 * 100)
    assert r["system_voltage"] == pytest.approx(84.0)        # 20S


def test_f22_is_37s_not_f22p():
    d, _ = make()
    d.decode(name("KS-F22-0110"))
    r = d.decode(live(voltage=13410))
    assert r["system_voltage"] == pytest.approx(155.4)       # 37 x 4.2
    assert r["battery_percent"] == round((134.1 - 114.7) / (153.5 - 114.7) * 100)


def test_multi_point_curve_16x():
    d, _ = make()
    d.decode(name("KS-16X-0100"))
    assert d.decode(live(voltage=6750))["battery_percent"] == 29   # 21 + 1.5 * 5 = 28.5, half up
    assert d.decode(live(voltage=9000))["battery_percent"] == 100
    assert d.decode(live(voltage=5000))["battery_percent"] == 0


def test_unknown_model_uses_euc_world_default_curve():
    d, _ = make()
    d.decode(name("ABC"))
    r = d.decode(live(voltage=5800))
    assert r["battery_percent"] == 50
    assert r["system_voltage"] == pytest.approx(67.2)


def test_trip_distance_from_b9():
    d, _ = make()
    d.decode(packet(0xB9, struct.pack("<HH", 0, 4321)))
    assert d.decode(live())["trip_distance"] == pytest.approx(4.321)


def test_serial_from_b3():
    d, _ = make()
    raw = bytearray(packet(0xB3, b"KS18S12345678A"))
    raw[17:20] = b"XYZ"
    d.decode(bytes(raw))
    assert d.serial == "KS18S12345678AXYZ"


def test_short_or_foreign_notifications_ignored():
    d, _ = make()
    assert d.decode(live()[:19]) is None
    assert d.decode(b"\x55\xaa" + live()[2:]) is None


def test_detection():
    assert isinstance(get_decoder_by_data(live()[:4]), KingSongDecoder)


def test_rockw_name_uses_60_83_curve():
    d, _ = make()
    d.decode(name("ROCKW-X-0100"))     # 3 parts -> model "ROCKW-X"
    assert d.decode(live(voltage=7150))["battery_percent"] == 50
