"""Tests for BLE device name to wheel brand matching."""

import unittest

from const import WheelBrand, match_brand_by_name


class TestMatchBrandByName(unittest.TestCase):

    def test_leaperkim_lk_names(self):
        for name in ("LK3336", "LK14132", "LK11184"):
            self.assertEqual(match_brand_by_name(name), WheelBrand.VETERAN, name)

    def test_full_brand_names(self):
        self.assertEqual(match_brand_by_name("KS-S18"), WheelBrand.KINGSONG)
        self.assertEqual(match_brand_by_name("Sherman S"), WheelBrand.VETERAN)
        self.assertEqual(match_brand_by_name("Begode Master"), WheelBrand.GOTWAY)

    def test_longest_pattern_wins(self):
        self.assertEqual(match_brand_by_name("Ninebot Z10"), WheelBrand.NINEBOT_Z)
        self.assertEqual(match_brand_by_name("Ninebot One"), WheelBrand.NINEBOT)

    def test_short_patterns_need_prefix_and_boundary(self):
        self.assertEqual(match_brand_by_name("V8-1234"), WheelBrand.INMOTION)
        for name in ("JBL Tune 770NC-LE", "Cardo Packtalk", "Phil's S25", "LKQ Parts", None, ""):
            self.assertIsNone(match_brand_by_name(name), name)


    def test_digit_ending_model_codes_allow_letter_suffix(self):
        self.assertEqual(match_brand_by_name("V8F-1234"), WheelBrand.INMOTION)
        self.assertEqual(match_brand_by_name("V5F"), WheelBrand.INMOTION)
        self.assertEqual(match_brand_by_name("V12HS"), WheelBrand.INMOTION_V2)
        self.assertEqual(match_brand_by_name("V12HS-ABCD"), WheelBrand.INMOTION_V2)

    def test_letter_ending_patterns_still_need_boundary(self):
        for name in ("LKQ Parts", "Cardo Packtalk", "JBL Tune 770NC-LE"):
            self.assertIsNone(match_brand_by_name(name), name)


if __name__ == "__main__":
    unittest.main()


def test_inmotion_v2_model_names():
    """V9/E20/P6 are InMotion V2 models (wh/w.java INIT_ID table)."""
    from euc_charging.const import WheelBrand, match_brand_by_name

    for name in ("P6-0001", "V9-1234", "E20-0042", "V12HS-1", "V13-9"):
        assert match_brand_by_name(name) == WheelBrand.INMOTION_V2, name
    assert match_brand_by_name("V8F-1") == WheelBrand.INMOTION
    assert match_brand_by_name("P") == WheelBrand.NINEBOT
