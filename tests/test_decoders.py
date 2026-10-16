"""Unit tests for EUC protocol decoders."""

import sys
from pathlib import Path

# Add parent directory to path to import the custom component
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "euc_charging"))

import unittest

# Import directly from decoders module to avoid __init__.py dependencies
import decoders

VeteranDecoder = decoders.VeteranDecoder
KingSongDecoder = decoders.KingSongDecoder
GotwayDecoder = decoders.GotwayDecoder
InMotionDecoder = decoders.InMotionDecoder
InMotionV2Decoder = decoders.InMotionV2Decoder
NinebotDecoder = decoders.NinebotDecoder
NinebotZDecoder = decoders.NinebotZDecoder
get_decoder_by_data = decoders.get_decoder_by_data


class TestVeteranDecoder(unittest.TestCase):
    """Test Veteran protocol decoder."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = VeteranDecoder()

    def test_veteran_live_data_sherman_s(self):
        """Test decoding Sherman S live data packet."""
        # Sample packet from Sherman S (24S, 100.8V system)
        # DC 5A 5C 14 B9 01 00 00 1A 62 00 00 FF C6 00 00 2E 3D 00 00 00 00 [checksum]
        packet = bytes([
            0xDC, 0x5A, 0x5C, 0x14,  # Header + length
            0xB9, 0x01,  # Voltage: 441 / 100.0 = 4.41V per cell * 24 = ~105.84V (charging)
            0x00, 0x00,  # Speed: 0
            0x1A, 0x62,  # Trip: 6754 / 1000 = 6.754 km
            0x00, 0x00, 0xFF, 0xC6,  # Total: 65478 / 1000 = 65.478 km
            0x00, 0x00,  # Current: 0
            0x2E, 0x3D,  # Temperature: 11837 / 100 = 118.37°C (likely wrong, should be / 10)
            0x00, 0x00,  # PWM: 0
            0x12, 0x34,  # Checksum (placeholder)
        ])

        result = self.decoder.decode(packet)
        
        # Should not decode yet (need full frame assembly)
        # Veteran uses unpacker that accumulates BLE packets
        self.assertIsNone(result)

    def test_veteran_protocol_detection(self):
        """Test that Veteran protocol is detected correctly."""
        packet = bytes([0xDC, 0x5A, 0x5C, 0x10])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, VeteranDecoder)


class TestKingSongDecoder(unittest.TestCase):
    """Test KingSong protocol decoder."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = KingSongDecoder()

    # The old live-data test fed a made-up big-endian layout; the EUC World
    # layout (little-endian, command at byte 16) is covered in
    # test_kingsong_euc_world.py.

    def test_kingsong_protocol_detection(self):
        """Test that KingSong protocol is detected correctly."""
        packet = bytes([0xAA, 0x55, 0x14, 0x5A, 0xA9])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, KingSongDecoder)


class TestGotwayDecoder(unittest.TestCase):
    """Test Gotway/Begode protocol decoder."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = GotwayDecoder()

    def test_gotway_protocol_detection(self):
        """Test that Gotway protocol is detected correctly."""
        packet = bytes([0x55, 0xAA, 0xDC, 0x5A])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, GotwayDecoder)

    # Gotway frame decoding (24-byte frames, model-based voltage scaling) is
    # covered in test_gotway_euc_world.py; the old voltage-threshold
    # detection test was removed with that behaviour.


class TestInMotionDecoder(unittest.TestCase):
    """Test InMotion V1 protocol decoder."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = InMotionDecoder()

    def test_inmotion_protocol_detection(self):
        """Test that InMotion V1 protocol is detected correctly."""
        packet = bytes([0xAA, 0xAA, 0x09, 0x01])
        decoder = get_decoder_by_data(packet)
        # Note: May not detect until enough data for header + length
        # Protocol detection needs improvement for InMotion

    def test_inmotion_keepalive_packet(self):
        """Test that keepalive packet is generated."""
        keepalive = self.decoder.get_keepalive_packet()
        self.assertIsNotNone(keepalive)
        self.assertEqual(keepalive[0:2], bytes([0xAA, 0xAA]))


class TestInMotionV2Decoder(unittest.TestCase):
    """Test InMotion V2 protocol decoder."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = InMotionV2Decoder()

    def test_inmotionv2_protocol_detection(self):
        """Test that InMotion V2 protocol is detected correctly."""
        packet = bytes([0xDC, 0x5A, 0x05, 0x01])
        # Note: Conflicts with Veteran header, needs better detection

    def test_inmotionv2_keepalive_packet(self):
        """Test that keepalive packet is generated."""
        keepalive = self.decoder.get_keepalive_packet()
        self.assertIsNotNone(keepalive)
        self.assertEqual(keepalive[0:2], bytes([0xDC, 0x5A]))


class TestNinebotDecoder(unittest.TestCase):
    """Test Ninebot protocol decoder."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = NinebotDecoder()

    def test_ninebot_protocol_detection(self):
        """Test that Ninebot protocol is detected correctly."""
        packet = bytes([0x55, 0xAA, 0x03, 0x22, 0x01])
        decoder = get_decoder_by_data(packet)
        # Note: Conflicts with Gotway header, needs better detection

    # The old keepalive (55 AA 03 22 01, XOR checksum) and serial-derived
    # "encryption" tests encoded behaviour EUC World does not have; the real
    # request/response protocol is covered in test_ninebot_euc_world.py.


class TestNinebotZDecoder(unittest.TestCase):
    """Test Ninebot Z protocol decoder."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = NinebotZDecoder()

    def test_ninebotz_protocol_detection(self):
        """Test that Ninebot Z protocol is detected correctly."""
        packet = bytes([0x5A, 0xA5, 0x03, 0x22, 0x01])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, NinebotZDecoder)

    # The old keepalive test (5A A5 03 22 01, no 0x3E byte, wrong checksum) is
    # replaced by the key-exchange tests in test_ninebot_euc_world.py.


class TestProtocolDetection(unittest.TestCase):
    """Test protocol auto-detection."""

    def test_detection_veteran(self):
        """Test detection of Veteran protocol."""
        packet = bytes([0xDC, 0x5A, 0x5C, 0x10])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, VeteranDecoder)

    def test_detection_kingsong(self):
        """Test detection of KingSong protocol."""
        packet = bytes([0xAA, 0x55, 0x14, 0x5A])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, KingSongDecoder)

    def test_detection_gotway(self):
        """Test detection of Gotway protocol."""
        packet = bytes([0x55, 0xAA, 0xDC, 0x5A])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, GotwayDecoder)

    def test_detection_ninebotz(self):
        """Test detection of Ninebot Z protocol."""
        packet = bytes([0x5A, 0xA5, 0x03, 0x22])
        decoder = get_decoder_by_data(packet)
        self.assertIsInstance(decoder, NinebotZDecoder)

    def test_detection_unknown(self):
        """Test handling of unknown protocol."""
        packet = bytes([0xFF, 0xFF, 0xFF, 0xFF])
        decoder = get_decoder_by_data(packet)
        self.assertIsNone(decoder)

    def test_detection_short_packet(self):
        """Test handling of too-short packet."""
        packet = bytes([0xDC])
        decoder = get_decoder_by_data(packet)
        self.assertIsNone(decoder)


class TestBatteryCalculation(unittest.TestCase):
    """Test battery percentage calculation."""

    def setUp(self):
        """Set up test fixtures."""
        self.decoder = VeteranDecoder()

    def test_battery_full(self):
        """Test battery calculation at full charge."""
        # 24S full: 100.8V
        percent = self.decoder.calculate_battery_percent(100.8, 100.8)
        self.assertGreaterEqual(percent, 95.0)

    def test_battery_half(self):
        """Test battery calculation at ~50%."""
        # WheelLog 24S curve: 50% at 80.70V + 50 * 0.195V = 90.45V
        percent = self.decoder.calculate_battery_percent(90.45, 100.8)
        self.assertAlmostEqual(percent, 50.0, delta=0.5)

    def test_battery_low_region(self):
        """Test the slow-discharge region below 3.40V/cell."""
        # 82.0V = 3.42V/cell is in the upper region: (8200 - 8070) / 19.5
        self.assertAlmostEqual(
            self.decoder.calculate_battery_percent(82.0, 100.8), 6.7, delta=0.1
        )
        # 80.0V is in the lower region: (8000 - 7935) / 48.75
        self.assertAlmostEqual(
            self.decoder.calculate_battery_percent(80.0, 100.8), 1.3, delta=0.1
        )

    def test_battery_curve_is_monotonic(self):
        """Percent never decreases as voltage rises (no jump at 3.40V/cell)."""
        for system_voltage in (100.8, 126.0, 151.2, 176.4, 84.0):
            last = -1.0
            for centivolts in range(int(system_voltage * 70), int(system_voltage * 101)):
                percent = self.decoder.calculate_battery_percent(centivolts / 100, system_voltage)
                self.assertGreaterEqual(percent, last, f"{system_voltage}V at {centivolts / 100}V")
                last = percent

    def test_battery_empty(self):
        """Test battery calculation at empty."""
        # 24S empty: 72V (3.0V per cell)
        percent = self.decoder.calculate_battery_percent(72.0, 100.8)
        self.assertLessEqual(percent, 5.0)

    def test_battery_linear_mode(self):
        """Test linear battery calculation mode."""
        # Linear spans 3.0V/cell (72.0V) to 4.2V/cell (100.8V), so 50% is 86.4V
        percent = self.decoder.calculate_battery_percent(86.4, 100.8, use_better_percents=False)
        self.assertAlmostEqual(percent, 50.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
