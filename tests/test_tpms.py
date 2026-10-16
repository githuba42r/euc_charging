"""Tests for Motoeye VD TPMS advertisement decoding (no Home Assistant)."""

import unittest

from euc_charging.const import ENTRY_TYPE_TPMS, is_tpms_entry
from euc_charging.tpms import (
    TpmsReading,
    decode_tpms,
    is_low_battery,
    is_low_pressure,
    is_tpms_advertisement,
)

# Worked example from MotoEyeFullScreenRemote README / TpmsBleMonitor.kt
README_PAYLOAD = bytes.fromhex("b0490136")


class TestDecodeTpms(unittest.TestCase):

    def test_readme_example(self):
        reading = decode_tpms(README_PAYLOAD, rssi=-70)
        self.assertAlmostEqual(reading.battery_voltage, 2.98, places=2)
        self.assertEqual(reading.battery_percent, 98)
        self.assertEqual(reading.temperature, 23)
        self.assertAlmostEqual(reading.pressure_kpa, 210.0)
        self.assertEqual(reading.rssi, -70)

    def test_pressure_below_atmospheric_clamps_to_zero(self):
        reading = decode_tpms(bytes([0xB0, 0x49, 0x00, 0x50]))  # 80 kPa abs
        self.assertEqual(reading.pressure_kpa, 0.0)

    def test_battery_percent_clamps(self):
        self.assertEqual(decode_tpms(bytes([0x00, 0x49, 0x01, 0x36])).battery_percent, 0)    # 1.22 V
        self.assertEqual(decode_tpms(bytes([0xFF, 0x49, 0x01, 0x36])).battery_percent, 100)  # 3.77 V

    def test_temperature_offset(self):
        self.assertEqual(decode_tpms(bytes([0xB0, 0x00, 0x01, 0x36])).temperature, -50)

    def test_short_payload(self):
        self.assertIsNone(decode_tpms(b"\xb0\x49\x01"))
        self.assertIsNone(decode_tpms(b""))


class TestIsTpmsAdvertisement(unittest.TestCase):

    def test_matches(self):
        self.assertTrue(is_tpms_advertisement("VD", {0x3000: README_PAYLOAD}))
        self.assertTrue(is_tpms_advertisement("vd", {0x3000: README_PAYLOAD}))

    def test_rejects(self):
        self.assertFalse(is_tpms_advertisement("VD", {}))
        self.assertFalse(is_tpms_advertisement("VD", {0x004C: README_PAYLOAD}))
        self.assertFalse(is_tpms_advertisement("VD", {0x3000: b"\x01\x02"}))
        self.assertFalse(is_tpms_advertisement("LK3336", {0x3000: README_PAYLOAD}))
        self.assertFalse(is_tpms_advertisement(None, {0x3000: README_PAYLOAD}))


class TestAlarms(unittest.TestCase):

    def reading(self, pressure_kpa=210.0, battery_percent=98):
        return TpmsReading(2.98, battery_percent, 23, pressure_kpa, None)

    def test_low_pressure(self):
        # 30 psi = 206.84 kPa
        self.assertFalse(is_low_pressure(self.reading(210.0), 30))
        self.assertTrue(is_low_pressure(self.reading(200.0), 30))

    def test_low_battery(self):
        self.assertFalse(is_low_battery(self.reading(battery_percent=20)))
        self.assertTrue(is_low_battery(self.reading(battery_percent=19)))


class TestIsTpmsEntry(unittest.TestCase):

    def test_entry_type(self):
        self.assertTrue(is_tpms_entry({"address": "B9:42:FB:00:02:A6", "entry_type": ENTRY_TYPE_TPMS}))
        self.assertFalse(is_tpms_entry({"address": "88:25:83:F3:5D:30"}))


if __name__ == "__main__":
    unittest.main()
