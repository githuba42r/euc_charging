"""Tests for Veteran/Leaperkim charging current decoding.

Field layout (from EUC World 2.68.0 decompilation, confirmed against a real
LK3336 Sherman S capture while charging):
  buff[3]      payload length (frame is len + 4 bytes)
  buff[23]     charging flag
  buff[38:40]  int16 battery current when not charging (x0.1 x1.5 A)
  buff[46]     extended sub-page id (0-7 rotate), present when len >= 47
  sub-page 0/4, len >= 69:
    buff[63:65] int16 battery current x0.1 A (<= 0 while charging)
  sub-page 0/4, len >= 73:
    buff[69:71], buff[71:73] int16 pack 1 / pack 2 current x0.01 A
"""

import struct
import unittest
from pathlib import Path

import decoders

CAPTURE = (
    Path(__file__).parent.parent
    / "euc_captures" / "real" / "lk3336_sherman_s_charging_20261016.txt"
)


def make_frame(length, charging=1, page=None, values=None):
    """Build a Veteran frame of payload `length` with int16 values at offsets."""
    buff = bytearray(length + 4)
    buff[0:4] = bytes([0xDC, 0x5A, 0x5C, length])
    struct.pack_into(">H", buff, 4, 10030)        # 100.30 V
    struct.pack_into(">H", buff, 28, 3015)        # Sherman S firmware
    buff[23] = charging
    if page is not None:
        buff[46] = page
    for offset, value in (values or {}).items():
        struct.pack_into(">h", buff, offset, value)
    return bytes(buff)


class TestVeteranChargingCurrentCapture(unittest.TestCase):
    """Decode the real LK3336 charging capture."""

    def setUp(self):
        self.decoder = decoders.VeteranDecoder()
        self.results = []
        for line in CAPTURE.read_text().splitlines():
            _, hexdata = line.split()
            result = self.decoder.decode(bytes.fromhex(hexdata))
            if result:
                self.results.append(result)

    def test_frames_decode(self):
        self.assertGreater(len(self.results), 800)
        self.assertTrue(all(r["is_charging"] for r in self.results))

    def test_charging_current_tracks_offset_63(self):
        currents = [r["charging_current"] for r in self.results
                    if r["charging_current"] is not None]
        # Raw offset 63 went from -26 to -21 over the capture (CV taper).
        self.assertAlmostEqual(currents[0], 2.6, places=2)
        self.assertAlmostEqual(currents[-1], 2.1, places=2)
        self.assertTrue(all(2.0 <= c <= 2.7 for c in currents))

    def test_battery_current_is_negative_while_charging(self):
        last = self.results[-1]
        self.assertAlmostEqual(last["battery_current"], -2.1, places=2)

    def test_charging_power(self):
        last = self.results[-1]
        self.assertAlmostEqual(
            last["charging_power"], last["charging_current"] * last["voltage"], places=1
        )


class TestVeteranChargingCurrentSynthetic(unittest.TestCase):
    """Cases the single-pack capture does not cover."""

    def setUp(self):
        self.decoder = decoders.VeteranDecoder()

    def test_unknown_until_subpage_received(self):
        result = self.decoder.decode(make_frame(47, page=1))
        self.assertIsNone(result["charging_current"])
        self.assertIsNone(result["charging_power"])

    def test_value_persists_across_other_subpages(self):
        self.decoder.decode(make_frame(69, page=0, values={63: -30}))
        result = self.decoder.decode(make_frame(47, page=2))
        self.assertAlmostEqual(result["charging_current"], 3.0, places=2)

    def test_dual_pack_currents_are_summed(self):
        # Long frames carry per-pack currents which take precedence over offset 63.
        result = self.decoder.decode(
            make_frame(73, page=4, values={63: -50, 69: -251, 71: -249})
        )
        self.assertAlmostEqual(result["battery_current"], -5.0, places=2)
        self.assertAlmostEqual(result["charging_current"], 5.0, places=2)

    def test_positive_offset_63_is_ignored(self):
        result = self.decoder.decode(make_frame(69, page=0, values={63: 15}))
        self.assertIsNone(result["charging_current"])

    def test_not_charging(self):
        self.decoder.decode(make_frame(69, page=0, values={63: -30}))
        result = self.decoder.decode(make_frame(47, charging=0, page=1, values={38: 20}))
        self.assertFalse(result["is_charging"])
        self.assertEqual(result["charging_current"], 0.0)
        self.assertEqual(result["charging_power"], 0.0)
        self.assertAlmostEqual(result["battery_current"], 3.0, places=2)

    def test_short_frame_has_no_battery_current(self):
        result = self.decoder.decode(make_frame(32))
        self.assertIsNone(result["battery_current"])


if __name__ == "__main__":
    unittest.main()
