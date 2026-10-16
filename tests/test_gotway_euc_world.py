"""Gotway/Begode decoder tests against EUC World 2.68.0's parser (wh/s.java).

SYNTHETIC DATA: no Gotway/Begode hardware was available. Every frame below is
built byte-for-byte from the layout EUC World parses (big-endian, 24-byte
frames: 55 AA, data, type at byte 18, sub-index at 19, 5A 5A 5A 5A), and the
expected values are what EUC World's arithmetic gives for those bytes.
"""

import struct

import pytest

from euc_charging.decoders import GotwayDecoder, GotwayUnpacker, get_decoder_by_data


def frame(frame_type: int, data: bytes = b"", sub: int = 0) -> bytes:
    """55 AA + 16 data bytes (offsets 2..17) + type + sub-index + footer."""
    body = data.ljust(16, b"\x00")
    assert len(body) == 16
    return b"\x55\xaa" + body + bytes([frame_type, sub]) + b"\x5a\x5a\x5a\x5a"


def live(voltage_raw=6000, speed_raw=0, trip_m=0, current_raw=0, temp_raw=0, word14=0):
    """Frame type 0: voltage@2 speed@4 trip@8 current@10 temp@12 word@14."""
    data = struct.pack(
        ">HhHHhhh", voltage_raw, speed_raw, 0, trip_m, current_raw, temp_raw, word14
    )
    return frame(0x00, data)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_decoder():
    decoder = GotwayDecoder()
    decoder._clock = clock = FakeClock()
    decoder.reset_session()
    return decoder, clock


def test_frames_are_24_bytes_and_split_chunks_reassemble():
    unpacker = GotwayUnpacker()
    f = live()
    assert len(f) == 24
    assert unpacker.add_data(f[:20]) == []
    assert unpacker.add_data(f[20:]) == [f]


def test_junk_and_short_spans_are_dropped():
    unpacker = GotwayUnpacker()
    f = live()
    # A 55 AA ... 5A5A5A5A span that isn't 24 bytes long is discarded.
    short = b"\x55\xaa\x01\x02\x5a\x5a\x5a\x5a"
    assert unpacker.add_data(b"\x00\x13" + short + f) == [f]


def test_unknown_model_reports_raw_voltage_only():
    decoder, _ = make_decoder()
    result = decoder.decode(live(voltage_raw=6543))
    assert result["raw_voltage"] == pytest.approx(65.43)
    assert result["voltage"] is None
    assert result["battery_percent"] is None
    assert result["system_voltage"] is None
    assert result["is_charging"] is None
    assert result["charging_current"] is None


def test_live_fields_scaling():
    decoder, _ = make_decoder()
    # speed 1000 * 0.036 = 36 km/h; trip 12345 m; current 1234 * 0.01;
    # temp: Java int division 3400 / 340 = 10 -> 46.53 C.
    result = decoder.decode(live(speed_raw=1000, trip_m=12345, current_raw=1234, temp_raw=3400))
    assert result["speed"] == pytest.approx(36.0)
    assert result["trip_distance"] == pytest.approx(12.345)
    assert result["current"] == pytest.approx(12.34)
    assert result["temperature"] == pytest.approx(46.53)


def test_reverse_speed_is_abs_and_current_follows_direction():
    decoder, _ = make_decoder()
    result = decoder.decode(live(speed_raw=-500, current_raw=300))
    assert result["speed"] == pytest.approx(18.0)
    assert result["current"] == pytest.approx(-3.0)  # signum(speed) * current


def test_temperature_uses_truncating_division():
    decoder, _ = make_decoder()
    result = decoder.decode(live(temp_raw=-700))  # -700/340 -> -2 (toward zero)
    assert result["temperature"] == pytest.approx(34.53)


@pytest.mark.parametrize("voltage_raw", [3999, 7201])
def test_out_of_range_voltage_frame_dropped(voltage_raw):
    decoder, _ = make_decoder()
    assert decoder.decode(live(voltage_raw=voltage_raw)) is None


def test_total_distance_from_frame_type_4():
    decoder, _ = make_decoder()
    assert decoder.decode(frame(0x04, struct.pack(">I", 1234567))) is None
    result = decoder.decode(live())
    assert result["total_distance"] == pytest.approx(1234.567)


def test_name_probe_selects_model_and_scales_voltage():
    """'N' -> "NAME:Master Pro" matches the 134.4 V model: raw x 2.0."""
    decoder, clock = make_decoder()
    assert decoder.get_requests() == []          # first probe after 250 ms
    clock.now += 0.25
    assert decoder.get_requests() == [b"N"]
    decoder.decode(b"NAME:Master Pro")
    clock.now += 0.1
    assert decoder.get_requests() == [b"V"]
    decoder.decode(b"GW23040" + b"01")
    assert decoder.get_requests() == []          # probe finished
    assert decoder.model.name == "Master Pro"

    result = decoder.decode(live(voltage_raw=6000))
    assert result["raw_voltage"] == pytest.approx(60.0)
    assert result["voltage"] == pytest.approx(120.0)
    assert result["system_voltage"] == pytest.approx(134.4)
    assert result["model"] == "Master Pro"
    assert result["version"] == "GW2304001"
    # Discharge map: empty 99.2 V -> 0 %, 134.4 - 0.5 = 133.9 V -> 100 %.
    assert result["battery_percent"] == pytest.approx(round((120 - 99.2) / (133.9 - 99.2) * 100, 1))


def test_firmware_match_when_name_unknown():
    """Name unmatched -> firmware regex: GW1912001 is RS C38 (100.8 V, x1.5)."""
    decoder, clock = make_decoder()
    clock.now += 0.25
    decoder.get_requests()
    decoder.decode(b"NAME:SomethingElse")
    clock.now += 0.1
    decoder.get_requests()
    decoder.decode(b"GW1912001")
    assert decoder.model.name == "RS C38"
    result = decoder.decode(live(voltage_raw=6720))
    assert result["voltage"] == pytest.approx(100.8)
    assert result["battery_percent"] == 100.0


def test_16s_model_is_not_scaled():
    decoder, _ = make_decoder()
    assert decoder.set_model("MCM 4")
    result = decoder.decode(live(voltage_raw=6000))
    assert result["voltage"] == pytest.approx(60.0)
    # No empty voltage in the table -> EUC World default full * 0.7857.
    empty = 67.2 * 0.7857142857142856
    assert result["battery_percent"] == pytest.approx(round((60 - empty) / (66.7 - empty) * 100, 1))


def test_probe_gives_up_after_two_timeouts_per_request():
    decoder, clock = make_decoder()
    clock.now += 0.25
    assert decoder.get_requests() == [b"N"]
    clock.now += 1.5
    assert decoder.get_requests() == [b"N"]     # retry
    clock.now += 1.5
    assert decoder.get_requests() == []         # gave up; no firmware probe
    assert decoder._probe == "done"
    assert decoder.model is None


def test_detection_55aa_is_gotway():
    assert isinstance(get_decoder_by_data(live()[:20]), GotwayDecoder)
