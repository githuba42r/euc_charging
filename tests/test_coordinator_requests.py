"""Coordinator request-loop plumbing (no Home Assistant runtime needed)."""

import asyncio
from types import SimpleNamespace

import pytest

from euc_charging import coordinator as coord_mod
from euc_charging.const import GOTWAY_READ_UUID, WheelBrand
from euc_charging.decoders import GotwayDecoder, VeteranDecoder


class FakeClient:
    def __init__(self):
        self.is_connected = True
        self.writes = []

    async def write_gatt_char(self, uuid, data, response=False):
        self.writes.append((uuid, bytes(data)))


def bare_coordinator(name="Whatever"):
    c = object.__new__(coord_mod.EucChargingCoordinator)
    c.ble_device = SimpleNamespace(name=name, address="AA:BB")
    c.decoder = None
    c.client = FakeClient()
    c._read_uuid = c._write_uuid = None
    c._requires_keepalive = False
    c._keepalive_task = None
    return c


def test_gotway_has_write_path_for_probe():
    c = bare_coordinator()
    c._setup_uuids_for_brand(WheelBrand.GOTWAY)
    assert c._write_uuid == GOTWAY_READ_UUID and c._requires_keepalive


def test_veteran_unchanged_no_requests():
    c = bare_coordinator()
    c._setup_uuids_for_brand(WheelBrand.VETERAN)
    assert not c._requires_keepalive
    assert VeteranDecoder().get_requests() == []


def test_gotway_probe_written_through_loop():
    c = bare_coordinator()
    c.decoder = GotwayDecoder()
    c._setup_uuids_for_brand(WheelBrand.GOTWAY)

    async def run():
        task = asyncio.ensure_future(c._keepalive_loop())
        await asyncio.sleep(0.4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert c.client.writes == [(GOTWAY_READ_UUID, b"N")]
