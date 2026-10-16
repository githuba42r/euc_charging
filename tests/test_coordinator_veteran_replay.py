"""Replay the real LK3336 (Sherman S) capture through the coordinator's
notification handler and check the Veteran path is unchanged: Veteran is
detected, every telemetry dict equals what VeteranDecoder alone produces,
no request task is started and nothing is written to the wheel.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from euc_charging import coordinator as coord_mod
from euc_charging.charge_tracker import ChargeTracker
from euc_charging.decoders import VeteranDecoder

CAPTURE = (
    Path(__file__).parent.parent
    / "euc_captures" / "real" / "lk3336_sherman_s_charging_20261016.txt"
)


def chunks():
    return [bytes.fromhex(line.split()[1]) for line in CAPTURE.read_text().splitlines()]


def make_coordinator(monkeypatch, name="LK3336"):
    c = object.__new__(coord_mod.EucChargingCoordinator)
    c.ble_device = SimpleNamespace(name=name, address="AA:BB")
    c.decoder = None
    c.client = None
    c._read_uuid = c._write_uuid = None
    c._requires_keepalive = False
    c._keepalive_task = None
    c.charge_tracker = ChargeTracker()
    c.last_connected_time = c.last_voltage = c.last_battery_percent = None
    c.last_trip_distance = c.last_total_distance = None
    c._schedule_save = lambda: None
    c.published = []
    c.async_set_updated_data = c.published.append
    c.hass = SimpleNamespace(
        async_create_background_task=lambda *a, **k: pytest.fail("request task started")
    )
    monkeypatch.setattr(
        coord_mod.dr, "async_get",
        lambda hass: SimpleNamespace(async_get_device=lambda identifiers: None),
    )
    return c


@pytest.mark.parametrize("start", [0, 1, 2])
def test_veteran_capture_through_handler(monkeypatch, start):
    c = make_coordinator(monkeypatch)
    reference = VeteranDecoder()
    expected = []
    data = chunks()[start:]
    started = False
    for chunk in data:
        # The coordinator starts decoding at the first chunk carrying the
        # Veteran header; earlier (mid-frame) chunks are dropped, as before.
        started = started or chunk[:3] == b"\xdc\x5a\x5c"
        out = reference.decode(chunk) if started else None
        if out:
            expected.append(out)
    for chunk in data:
        c._notification_handler(None, bytearray(chunk))
    assert isinstance(c.decoder, VeteranDecoder)
    assert not c._requires_keepalive and c._write_uuid is None
    assert c.published, "no telemetry published"
    for got, want in zip(c.published, expected):
        got = {k: v for k, v in got.items() if k not in ("charge_estimates", "last_connected_time")}
        assert got == want
    assert len(c.published) == len(expected)
