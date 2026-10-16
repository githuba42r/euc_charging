"""Experimental charging inference (KingSong, Gotway/Begode, InMotion V1).

SYNTHETIC sequences with an injectable clock. These rules are this
integration's heuristics, not EUC World behaviour.
"""

import struct

import pytest

from euc_charging import decoders
from euc_charging.decoders import (
    CHARGE_CURRENT_SUSTAIN_S,
    CHARGE_VOLTAGE_STALL_S,
    CHARGE_VOLTAGE_WINDOW_S,
    ChargingInference,
    GotwayDecoder,
    KingSongDecoder,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(use_current=True):
    clock = Clock()
    return ChargingInference(use_current, clock=clock), clock


def feed(inf, clock, seconds, voltage, speed=0.0, current=None, step=10.0, slope=0.0):
    """Feed samples every `step` s for `seconds`; voltage rises by `slope` V/s."""
    out = None
    t = 0.0
    while t <= seconds:
        out = inf.update(voltage + slope * t, speed, current)
        clock.now += step
        t += step
    return out


def test_unknown_before_enough_history():
    inf, clock = make()
    assert feed(inf, clock, 120, 80.0) == (None, None)


def test_flat_voltage_full_window_is_not_charging():
    inf, clock = make()
    assert feed(inf, clock, CHARGE_VOLTAGE_WINDOW_S, 80.0) == (False, "inferred_voltage")


def test_voltage_rise_starts_and_stall_ends_charging():
    inf, clock = make(use_current=False)
    # 0.4 V over 5 minutes while stationary -> charging
    assert feed(inf, clock, 300, 80.0, slope=0.4 / 300) == (True, "inferred_voltage")
    # keeps rising -> still charging
    assert feed(inf, clock, 600, 80.4, slope=0.001)[0] is True
    # flat (charger done / unplugged): ends after the stall period
    v = 81.0
    assert feed(inf, clock, CHARGE_VOLTAGE_STALL_S - 30, v)[0] is True
    assert feed(inf, clock, 60, v) == (False, "inferred_voltage")


def test_small_rise_is_not_charging():
    inf, clock = make()
    assert feed(inf, clock, 300, 80.0, slope=0.2 / 300)[0] is False


def test_movement_ends_charging_and_hysteresis_holds():
    inf, clock = make()
    feed(inf, clock, 300, 80.0, slope=0.4 / 300)
    assert inf.is_charging is True
    assert inf.update(80.5, 1.5) == (True, "inferred_voltage")   # 1-2 km/h: hold
    assert inf.update(80.5, 2.0) == (False, "inferred_voltage")  # moving
    # parked again with flat voltage: stays not charging
    assert feed(inf, clock, 60, 80.5)[0] is False


def test_negative_current_sustained_while_stationary():
    inf, clock = make()
    assert feed(inf, clock, CHARGE_CURRENT_SUSTAIN_S - 10, 80.0, current=-3.0)[0] is None
    assert feed(inf, clock, 20, 80.0, current=-3.0) == (True, "inferred_current")
    # current stops (unplugged) with flat voltage -> not charging
    assert feed(inf, clock, 10, 80.0, current=0.0) == (False, "inferred_voltage")


def test_regen_while_moving_does_not_count():
    inf, clock = make()
    res = feed(inf, clock, 300, 80.0, speed=15.0, current=-20.0)
    assert res == (False, "inferred_voltage")


def test_current_rule_disabled_for_gotway_style():
    inf, clock = make(use_current=False)
    assert feed(inf, clock, 120, 80.0, current=-5.0) == (None, None)


def test_either_signal_keeps_charging():
    inf, clock = make()
    feed(inf, clock, 70, 80.0, current=-2.0)
    assert inf.is_charging is True
    # current quiet but voltage now rising -> still charging (voltage rule)
    res = feed(inf, clock, 300, 80.0, current=0.0, slope=0.5 / 300)
    assert res == (True, "inferred_voltage")


def test_missing_values_keep_state():
    inf, clock = make()
    assert inf.update(None, 0.0) == (None, None)
    assert inf.update(80.0, None) == (None, None)


# --- through the decoders -------------------------------------------------------

def ks_live(voltage, speed=0, current=0):
    p = bytearray(20)
    p[0:2] = b"\xaa\x55"
    struct.pack_into("<hhHHhh", p, 2, voltage, speed, 0, 0, current, 2500)
    p[16] = 0xA9
    p[17] = 0x14
    p[18] = p[19] = 0x5A
    return bytes(p)


def test_kingsong_infers_from_negative_current_and_exposes_raw_status():
    d = KingSongDecoder()
    d._clock = clock = Clock()
    d.reset_session()
    b9 = bytearray(ks_live(0))
    b9[16] = 0xB9
    b9[13] = 1
    d.decode(bytes(b9))
    r = None
    for _ in range(8):
        r = d.decode(ks_live(8000, 0, -250))
        clock.now += 10
    assert r["is_charging"] is True and r["charging_method"] == "inferred_current"
    assert r["charging_status_raw"] == 1
    assert r["charging_current"] is None


def gw_live(voltage_raw, speed_raw=0):
    data = struct.pack(">HhHHhhh", voltage_raw, speed_raw, 0, 0, 0, 0, 0)
    return b"\x55\xaa" + data.ljust(16, b"\x00") + bytes([0, 0]) + b"\x5a" * 4


def test_gotway_voltage_rule_on_raw_voltage():
    d = GotwayDecoder()
    d._clock = clock = Clock()
    d.reset_session()
    r = None
    for i in range(31):     # 0.01 V raw every 10 s -> 0.3 V in 5 min
        r = d.decode(gw_live(6000 + i))
        clock.now += 10
    assert r["is_charging"] is True and r["charging_method"] == "inferred_voltage"


def test_reset_session_forgets_evidence():
    d = KingSongDecoder()
    d._clock = clock = Clock()
    d.reset_session()
    for _ in range(8):
        d.decode(ks_live(8000, 0, -250))
        clock.now += 10
    d.reset_session()
    assert d.decode(ks_live(8000, 0, -250))["is_charging"] is None
