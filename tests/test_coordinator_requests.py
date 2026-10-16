"""Coordinator request-loop plumbing (no Home Assistant runtime needed)."""

import asyncio
from types import SimpleNamespace

import pytest

from euc_charging import coordinator as coord_mod
from euc_charging.const import GOTWAY_READ_UUID, NINEBOT_WRITE_UUID, NINEBOT_Z_WRITE_UUID, WheelBrand
from euc_charging.decoders import GotwayDecoder, NinebotDecoder, NinebotZDecoder, VeteranDecoder


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


@pytest.mark.parametrize(
    "name, cls, write_uuid",
    [("Ninebot S2", NinebotDecoder, NINEBOT_WRITE_UUID), ("Ninebot Z10", NinebotZDecoder, NINEBOT_Z_WRITE_UUID)],
)
def test_ninebot_preselected_from_ble_name(name, cls, write_uuid):
    c = bare_coordinator(name)
    c._preselect_decoder_by_name()
    assert isinstance(c.decoder, cls)
    assert c._write_uuid == write_uuid and c._requires_keepalive


def test_passive_brands_not_preselected():
    c = bare_coordinator("LK3336")
    c._preselect_decoder_by_name()
    assert c.decoder is None


def test_gotway_has_write_path_for_probe():
    c = bare_coordinator()
    c._setup_uuids_for_brand(WheelBrand.GOTWAY)
    assert c._write_uuid == GOTWAY_READ_UUID and c._requires_keepalive


def test_veteran_unchanged_no_requests():
    c = bare_coordinator()
    c._setup_uuids_for_brand(WheelBrand.VETERAN)
    assert not c._requires_keepalive
    assert VeteranDecoder().get_requests() == []


def test_loop_writes_decoder_requests():
    c = bare_coordinator("Ninebot S2")
    c._preselect_decoder_by_name()

    async def run():
        task = asyncio.ensure_future(c._keepalive_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    # One request outstanding (no reply), so exactly one write so far.
    assert c.client.writes == [(NINEBOT_WRITE_UUID, bytes.fromhex("55aa0311011a02ceff"))]


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


def test_kingsong_has_write_path_for_name_request():
    from euc_charging.const import KINGSONG_READ_UUID

    c = bare_coordinator()
    c._setup_uuids_for_brand(WheelBrand.KINGSONG)
    assert c._write_uuid == KINGSONG_READ_UUID and c._requires_keepalive


@pytest.mark.parametrize("name, brand", [("V8F-1234", WheelBrand.INMOTION), ("V13-5678", WheelBrand.INMOTION_V2), ("V11-0001", WheelBrand.INMOTION_V2)])
def test_inmotion_preselected_from_ble_name(name, brand):
    c = bare_coordinator(name)
    c._preselect_decoder_by_name()
    assert c.decoder.brand == brand and c._requires_keepalive
