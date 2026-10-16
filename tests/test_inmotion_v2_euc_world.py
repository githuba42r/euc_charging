"""InMotion V2 decoder tests against EUC World 2.68.0 ("InmotionNewAdapter", wh/w.java).

SYNTHETIC DATA: no InMotion hardware was available. A simulated wheel answers
each request with a frame built byte-for-byte from the layout EUC World
validates and parses (AA AA cmd len data xor, 0xA5 escaping, little-endian
per-model live layouts). Expected values are what EUC World's arithmetic
gives for those bytes.
"""

import struct

import pytest

from euc_charging.decoders import InMotionV2Decoder, get_decoder_by_data


def frame(cmd: int, payload: bytes, escape=True) -> bytes:
    raw = InMotionV2Decoder.build_frame(cmd, payload)
    if not escape:
        return raw
    out = bytearray(raw[:2])
    for b in raw[2:]:
        if b in (0xAA, 0x55, 0xA5):
            out.append(0xA5)
        out.append(b)
    return bytes(out)


def values_v_layout(voltage=8400, current=-520, speed=-1234, battery=8765, temp_raw=-50, charging=True):
    p = bytearray(90)
    p[0] = 0x84
    struct.pack_into("<h", p, 1, voltage)
    struct.pack_into("<h", p, 3, current)
    struct.pack_into("<h", p, 9, speed)
    struct.pack_into("<H", p, 35, battery)
    struct.pack_into("b", p, 59, temp_raw)
    struct.pack_into("<i", p, 75, 0x80 if charging else 0)
    return bytes(p)


def values_p_layout(voltage=10000, battery=5000, temp_raw=-45, charging=False):
    p = bytearray(70)
    p[0] = 0x84
    struct.pack_into("<h", p, 1, voltage)
    struct.pack_into("<h", p, 3, 300)
    struct.pack_into("<h", p, 5, 2000)
    struct.pack_into("<h", p, 25, battery)
    struct.pack_into("b", p, 41, temp_raw)
    struct.pack_into("<i", p, 55, 0x80 if charging else 0)
    return bytes(p)


def values_v11_14(charging=True):
    p = bytearray(70)
    p[0] = 0x84
    struct.pack_into("<h", p, 1, 8000)
    struct.pack_into("<h", p, 3, 250)
    struct.pack_into("<h", p, 5, 1500)
    struct.pack_into("<h", p, 29, 6650)
    struct.pack_into("b", p, 43, -40)
    struct.pack_into("<i", p, 57, 0x80 if charging else 0)
    return bytes(p)


def values_v11_old(charging=True):
    p = bytearray(50)
    p[0] = 0x84
    struct.pack_into("<h", p, 1, 8000)
    struct.pack_into("<h", p, 3, 250)
    struct.pack_into("<h", p, 5, 1500)
    p[17] = 0x80 | 55          # battery 55 % (bit 7 masked off)
    struct.pack_into("b", p, 21, -45)
    p[39] = 0x80 if charging else 0
    return bytes(p)


def firmware(major, minor, patch):
    p = bytearray(30)
    p[0], p[1] = 0x82, 0x06
    struct.pack_into("<h", p, 12, patch)
    p[14], p[15] = minor, major
    return bytes(p)


class Wheel:
    def __init__(self, model_id, variant=0, fw=(1, 4, 5), values=values_v_layout):
        self.model_id, self.variant, self.fw, self.values = model_id, variant, fw, values

    def answer(self, name, cmd):
        if name == "INIT_ID":
            return frame(cmd, bytes([0x82, 0x01, 0, self.model_id, self.variant]))
        if name == "INIT_SERIAL":
            return frame(cmd, bytes([0x82, 0x02]) + b"1480CA123456789\x00")
        if name == "INIT_FIRMWARE":
            return frame(cmd, firmware(*self.fw))
        if name == "INIT_SETTINGS":
            return frame(cmd, bytes([0xA0, 0x20, 0]))
        if name.startswith("INIT_BATTERY_"):
            n = int(name[13])
            return frame(cmd, bytes([0x23 + n, 0x02, 0x84, 0]))
        if name == "READ_VALUES":
            return frame(cmd, self.values())
        if name == "READ_TRIP":
            p = bytearray(30)
            p[0] = 0x90
            struct.pack_into("<I", p, 23, 1234)
            return frame(cmd, bytes(p))
        if name == "READ_TOTAL":
            p = bytearray(10)
            p[0] = 0x91
            struct.pack_into("<I", p, 1, 987654)
            return frame(cmd, bytes(p))
        return frame(cmd, bytes([0x85, 0, 0]))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def run(wheel, steps):
    d = InMotionV2Decoder()
    d._clock = clock = FakeClock()
    d.reset_session()
    sent, result = [], None
    for _ in range(steps):
        (req,) = d.get_requests()
        name = d._pending
        sent.append(name)
        cmd, data = InMotionV2Decoder.REQUESTS[name]
        assert req == InMotionV2Decoder.build_frame(cmd, data)
        reply = wheel.answer(name, cmd)
        out = None
        for i in range(0, len(reply), 20):
            out = d.decode(reply[i:i + 20]) or out
        result = out or result
        clock.now += 0.01
    return d, sent, result


def test_request_frame_bytes():
    # AA AA 11 02 02 01 xor
    assert InMotionV2Decoder.build_frame(0x11, bytes([2, 1])) == bytes.fromhex("aaaa11020201") + bytes(
        [0xAA ^ 0xAA ^ 0x11 ^ 0x02 ^ 0x02 ^ 0x01])


def test_v13_sequence_values_and_charging_flag():
    d, sent, r = run(Wheel(8), 14)
    assert sent[:8] == ["INIT_ID", "INIT_SERIAL", "INIT_FIRMWARE", "INIT_SETTINGS",
                        "INIT_BATTERY_1_SERIAL", "INIT_BATTERY_2_SERIAL",
                        "READ_VALUES", "READ_TRIP"]
    assert sent[8:11] == ["READ_TOTAL", "READ_BATTERY_1_STATUS", "READ_VALUES"]
    assert d.model == "V13" and d.serial == "1480CA123456789" and d.firmware == "1.4.5"
    assert r["voltage"] == pytest.approx(84.0)
    assert r["current"] == pytest.approx(-5.2)
    assert r["speed"] == pytest.approx(12.34)
    assert r["battery_percent"] == pytest.approx(87.65)
    assert r["temperature"] == 30.0
    assert r["is_charging"] is True
    assert r["charging_current"] == pytest.approx(5.2)
    assert r["trip_distance"] == pytest.approx(12.34)
    assert r["total_distance"] == pytest.approx(9876.54)
    assert r["system_voltage"] == pytest.approx(126.0)


def test_v14_reads_four_pack_serials():
    _, sent, _ = run(Wheel(9), 9)
    assert sent[4:8] == ["INIT_BATTERY_1_SERIAL", "INIT_BATTERY_2_SERIAL",
                         "INIT_BATTERY_3_SERIAL", "INIT_BATTERY_4_SERIAL"]
    assert sent[8] == "READ_VALUES"


def test_v12_layout_and_no_pack_reads():
    d, sent, r = run(Wheel(7, values=values_p_layout), 9)
    assert sent[4] == "READ_VALUES" and sent[7] == "READ_BATTERY"
    assert r["model"] == "V12"
    assert r["speed"] == pytest.approx(20.0)
    assert r["battery_percent"] == pytest.approx(50.0)
    assert r["temperature"] == 35.0
    assert r["is_charging"] is False and r["charging_current"] == 0.0
    assert r["system_voltage"] == pytest.approx(100.8)


def test_v11_firmware_dependent_layouts():
    _, _, r = run(Wheel(6, fw=(1, 4, 0), values=values_v11_14), 6)
    assert r["battery_percent"] == pytest.approx(66.5)
    assert r["temperature"] == 40.0 and r["is_charging"] is True
    _, _, r = run(Wheel(6, fw=(1, 2, 30), values=values_v11_old), 6)
    assert r["battery_percent"] == 55.0
    assert r["temperature"] == 35.0 and r["is_charging"] is True


def test_v11y_variant():
    d, _, _ = run(Wheel(6, variant=2), 3)
    assert d.model == "V11Y"


def test_unknown_model_id_assumed_v12():
    d, _, _ = run(Wheel(99, values=values_p_layout), 2)
    assert d.model == "V12"


def test_temperature_sensor_absent_until_first_reading():
    _, _, r = run(Wheel(8, values=lambda: values_v_layout(temp_raw=-80)), 7)
    assert r["temperature"] is None


def test_init_retried_on_timeout_and_bad_checksum_ignored():
    d = InMotionV2Decoder()
    d._clock = clock = FakeClock()
    d.reset_session()
    first = d.get_requests()
    bad = bytearray(frame(0x11, bytes([0x82, 0x01, 0, 8, 0]), escape=False))
    bad[-1] ^= 1
    d.decode(bytes(bad))
    assert d._pending == "INIT_ID"
    clock.now += 1.0
    assert d.get_requests() == first


def test_detection_by_xor_frame():
    assert isinstance(get_decoder_by_data(frame(0x14, bytes([0x84, 1, 2]))), InMotionV2Decoder)
