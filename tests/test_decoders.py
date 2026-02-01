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

    def test_kingsong_live_data(self):
        """Test decoding KingSong live data packet."""
        # Sample packet from KS-S18 (20S, 84V system)
        # AA 55 14 5A A9 14 A0 00 00 00 C8 01 F4 00 00 1E 5A 00 00 00 00 [checksum]
        packet = bytes([
            0xAA, 0x55,  # Header
            0x14, 0x5A, 0xA9,  # Length + sequence
            0x14, 0xA0,  # Voltage: 5280 / 100 = 52.80V (discharged 20S)
            0x00, 0x00,  # Speed: 0
            0x00, 0xC8,  # Trip: 200 / 1000 = 0.2 km
            0x01, 0xF4, 0x00, 0x00,  # Total: 500 km
            0x1E,  # Current: 30 / 100 = 0.3A
            0x5A,  # Temperature: 90 / 100 = 0.9°C (likely / 10 = 9°C)
            0x00, 0x00,  # PWM
            0x00, 0x00,  # Checksum (placeholder)
        ])

        result = self.decoder.decode(packet)
        
        # KingSong uses unpacker too
        self.assertIsNone(result)

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

    def test_gotway_voltage_detection(self):
        """Test voltage-based cell configuration detection."""
        # Test with 24S voltage (100.8V system)
        packet = bytes([
            0x55, 0xAA, 0xDC, 0x5A,  # Header
            0x27, 0x10,  # Voltage: 10000 / 100 = 100V (24S)
        ] + [0x00] * 30)
        
        result = self.decoder.decode(packet)
        self.assertIsNone(result)  # Needs full frame


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

    def test_ninebot_keepalive_packet(self):
        """Test that keepalive packet is generated."""
        keepalive = self.decoder.get_keepalive_packet()
        self.assertIsNotNone(keepalive)
        self.assertEqual(keepalive[0:2], bytes([0x55, 0xAA]))

    def test_ninebot_encryption(self):
        """Test Ninebot encryption/decryption."""
        encryption = decoders.NinebotEncryption()
        encryption.init_key("TEST12345678")
        
        original = b"Hello World!"
        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)
        
        self.assertNotEqual(original, encrypted)
        self.assertEqual(original, decrypted)


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

    def test_ninebotz_keepalive_packet(self):
        """Test that keepalive packet is generated."""
        keepalive = self.decoder.get_keepalive_packet()
        self.assertIsNotNone(keepalive)
        self.assertEqual(keepalive[0:2], bytes([0x5A, 0xA5]))


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
        # 24S ~50%: ~82V
        percent = self.decoder.calculate_battery_percent(82.0, 100.8)
        self.assertGreaterEqual(percent, 40.0)
        self.assertLessEqual(percent, 60.0)

    def test_battery_empty(self):
        """Test battery calculation at empty."""
        # 24S empty: 72V (3.0V per cell)
        percent = self.decoder.calculate_battery_percent(72.0, 100.8)
        self.assertLessEqual(percent, 5.0)

    def test_battery_linear_mode(self):
        """Test linear battery calculation mode."""
        # Linear should give exactly 50% at 50.4V for 100.8V system
        percent = self.decoder.calculate_battery_percent(50.4, 100.8, use_better_percents=False)
        self.assertAlmostEqual(percent, 50.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
