"""Tests for the review fix wave (coordinator, binary sensor, decoders)."""

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from bleak.exc import BleakError

from euc_charging import coordinator as coord_mod
from euc_charging.charge_tracker import ChargeTracker
from euc_charging.const import (
    INMOTION_V2_SERVICE_UUID,
    INMOTION_WRITE_SERVICE_UUID,
    INMOTION_WRITE_UUID,
    NINEBOT_READ_UUID,
    NINEBOT_SERVICE_UUID,
    NINEBOT_WRITE_UUID,
    NOTIFY_UUID,
    WheelBrand,
)
from euc_charging.decoders import (
    GotwayDecoder,
    InMotionDecoder,
    InMotionV2Decoder,
    KingSongDecoder,
    NinebotDecoder,
    VeteranDecoder,
)

FFE0 = NINEBOT_SERVICE_UUID
CAPTURE = (
    Path(__file__).parent.parent
    / "euc_captures" / "real" / "lk3336_sherman_s_charging_20261016.txt"
)


class FakeClient:
    def __init__(self, services=(FFE0,), missing=()):
        self.is_connected = False
        self.writes = []
        self.log = []
        self.notify_uuid = None
        self.handler = None
        self.services = [SimpleNamespace(uuid=u) for u in services]
        self.missing = set(missing)

    async def connect(self):
        self.is_connected = True
        self.log.append("connect")

    async def start_notify(self, uuid, handler):
        if uuid in self.missing:
            raise BleakError(f"Characteristic {uuid} was not found!")
        self.notify_uuid, self.handler = uuid, handler
        self.log.append(("notify", uuid))

    async def write_gatt_char(self, uuid, data, response=False):
        self.writes.append((uuid, bytes(data)))

    async def stop_notify(self, uuid):
        pass

    async def disconnect(self):
        self.is_connected = False


def coordinator(name, title="My wheel"):
    c = object.__new__(coord_mod.EucChargingCoordinator)
    c.hass = SimpleNamespace(
        async_create_background_task=lambda coro, name=None: asyncio.ensure_future(coro)
    )
    c.entry = SimpleNamespace(title=title)
    c.ble_device = SimpleNamespace(name=name, address="AA:BB", rssi=-50)
    c.decoder = None
    c.client = None
    c.charge_tracker = ChargeTracker()
    c._keepalive_task = None
    c._read_uuid = c._write_uuid = None
    c._requires_keepalive = False
    c._requests_enabled = asyncio.Event()
    c._write_failure_logged = False
    c._preselected = False
    c._preselect_disabled = False
    c._connects_without_data = 0
    c.auto_connect_enabled = True
    c._reconnect_event = asyncio.Event()
    c._device_available = asyncio.Event()
    c._device_seen_recently = False
    c.last_connected_time = c.last_voltage = c.last_battery_percent = None
    c.last_trip_distance = c.last_total_distance = None
    c.data = None
    c._schedule_save = lambda: None
    c.published = []
    c.async_set_updated_data = c.published.append
    c.async_set_update_error = lambda ex: None
    return c


async def run_connect(c, client, monkeypatch, seconds=0.3, feed=None):
    monkeypatch.setattr(coord_mod, "async_ble_device_from_address", lambda *a, **k: c.ble_device)
    monkeypatch.setattr(coord_mod, "BleakClient", lambda *a, **k: client)
    monkeypatch.setattr(
        coord_mod.dr, "async_get",
        lambda hass: SimpleNamespace(async_get_device=lambda identifiers: None),
    )
    task = asyncio.ensure_future(c._connect_loop())
    await asyncio.sleep(seconds)
    if feed:
        for chunk in feed:
            client.handler(None, bytearray(chunk))
        await asyncio.sleep(0.2)
    for t in (task, c._keepalive_task):
        if t:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


# --- _connect_loop with a fake BleakClient -------------------------------------

def test_connect_ninebot_preselect_reset_after_notify_and_request(monkeypatch):
    c = coordinator("Ninebot S2")
    client = FakeClient(services=(FFE0,))
    order = client.log
    original = NinebotDecoder.reset_session
    monkeypatch.setattr(
        NinebotDecoder, "reset_session",
        lambda self: (order.append("reset"), original(self))[1],
    )
    asyncio.run(run_connect(c, client, monkeypatch))
    assert isinstance(c.decoder, NinebotDecoder)
    assert client.notify_uuid == NINEBOT_READ_UUID
    # reset_session ran after notifications were enabled (the constructor's own
    # reset happens before connect).
    assert order.index(("notify", NINEBOT_READ_UUID)) < len(order) - 1 - order[::-1].index("reset")
    assert client.writes and client.writes[0] == (NINEBOT_WRITE_UUID, bytes.fromhex("55aa0311011a02ceff"))


def test_connect_veteran_writes_nothing(monkeypatch):
    c = coordinator("LK3336")
    client = FakeClient(services=(FFE0,))
    chunks = [bytes.fromhex(l.split()[1]) for l in CAPTURE.read_text().splitlines()[:200]]
    asyncio.run(run_connect(c, client, monkeypatch, feed=chunks))
    assert client.notify_uuid == NOTIFY_UUID
    assert isinstance(c.decoder, VeteranDecoder)
    assert c._keepalive_task is None and client.writes == []
    assert c.published


def test_connect_drops_preselected_decoder_on_missing_characteristic(monkeypatch):
    c = coordinator("V8F-1234")
    client = FakeClient(services=(FFE0, INMOTION_WRITE_SERVICE_UUID), missing={"0000ffe4-0000-1000-8000-00805f9b34fb"})
    asyncio.run(run_connect(c, client, monkeypatch))
    assert c.decoder is None and c._preselect_disabled
    assert client.notify_uuid == NOTIFY_UUID
    assert client.writes == []


def test_preselected_decoder_dropped_after_empty_connects():
    c = coordinator("Ninebot S2")
    c.client = FakeClient(services=(FFE0,))
    c._preselect_decoder_by_name()
    assert c._preselected
    for _ in range(coord_mod.EucChargingCoordinator.PRESELECT_MAX_EMPTY_CONNECTS):
        c._check_preselected_decoder()
        assert c.decoder is not None
    c._check_preselected_decoder()
    assert c.decoder is None and c._preselect_disabled
    c._preselect_decoder_by_name()
    assert c.decoder is None          # no second preselection


def test_confirmed_preselected_decoder_is_kept():
    c = coordinator("Ninebot S2")
    c.client = FakeClient(services=(FFE0,))
    c._preselect_decoder_by_name()
    c.decoder.packet_count = 1
    for _ in range(10):
        c._check_preselected_decoder()
    assert isinstance(c.decoder, NinebotDecoder)


# --- name / service preselection -----------------------------------------------

@pytest.mark.parametrize("name, services, expected", [
    ("P6-0001", (INMOTION_V2_SERVICE_UUID,), InMotionV2Decoder),
    ("V9-0001", (INMOTION_V2_SERVICE_UUID,), InMotionV2Decoder),
    ("E20-0001", (INMOTION_V2_SERVICE_UUID,), InMotionV2Decoder),
    ("InMotion V12", (INMOTION_V2_SERVICE_UUID,), InMotionV2Decoder),   # name ties V1/V2
    ("InMotion V8", (FFE0, INMOTION_WRITE_SERVICE_UUID), InMotionDecoder),
    ("V8F-1234", (FFE0, INMOTION_WRITE_SERVICE_UUID), InMotionDecoder),
    ("V8F-1234", (FFE0,), None),          # V1 write service missing: don't guess
])
def test_preselect_uses_services(name, services, expected):
    c = coordinator(name)
    c.client = FakeClient(services=services)
    c._preselect_decoder_by_name()
    if expected is None:
        assert c.decoder is None
    else:
        assert isinstance(c.decoder, expected)


def test_preselect_falls_back_to_entry_title_when_name_missing():
    c = coordinator(None, title="Ninebot S2")
    c.client = FakeClient(services=(FFE0,))
    c._preselect_decoder_by_name()
    assert isinstance(c.decoder, NinebotDecoder)


# --- request loop ------------------------------------------------------------

def _loop(c, seconds):
    async def run():
        task = asyncio.ensure_future(c._keepalive_loop())
        await asyncio.sleep(seconds)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())


def test_inmotion_v1_request_written_in_20_byte_pieces():
    c = coordinator("V8F")
    c.client = FakeClient()
    c.client.is_connected = True
    c.decoder = InMotionDecoder()
    c._setup_uuids_for_brand(WheelBrand.INMOTION)

    async def run():
        c._requests_enabled.set()
        task = asyncio.ensure_future(c._keepalive_loop())
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    request = InMotionDecoder.build_request("INIT_PASSWORD", b"000000")
    assert [w[1] for w in c.client.writes] == [request[:20], request[20:21] + request[1:20]]
    assert all(w[0] == INMOTION_WRITE_UUID and len(w[1]) == 20 for w in c.client.writes)


def test_no_writes_until_notifications_enabled():
    c = coordinator("GotWay")
    c.client = FakeClient()
    c.client.is_connected = True
    c.decoder = GotwayDecoder()
    c._setup_uuids_for_brand(WheelBrand.GOTWAY)

    async def run():
        task = asyncio.ensure_future(c._keepalive_loop())
        await asyncio.sleep(0.4)
        assert c.client.writes == []          # event not set yet
        c.decoder.reset_session()
        c._requests_enabled.set()
        await asyncio.sleep(0.4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert c.client.writes == [(c._write_uuid, b"N")]


def test_loop_idles_when_decoder_has_nothing_to_send():
    c = coordinator("KS-S18")
    c.client = FakeClient()
    c.client.is_connected = True
    c.decoder = KingSongDecoder()
    c.decoder._name_answered = True
    c._setup_uuids_for_brand(WheelBrand.KINGSONG)
    calls = []
    original = c.decoder.get_requests
    c.decoder.get_requests = lambda: (calls.append(1), original())[1]

    async def run():
        c._requests_enabled.set()
        task = asyncio.ensure_future(c._keepalive_loop())
        await asyncio.sleep(0.5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert len(calls) == 1          # then sleeping IDLE_REQUEST_INTERVAL (5 s)


def test_write_failure_warns_once(caplog, monkeypatch):
    c = coordinator("Ninebot S2")
    c.client = FakeClient()
    c.client.is_connected = True

    async def failing(*a, **k):
        raise BleakError("not connected")
    c.client.write_gatt_char = failing
    c.decoder = NinebotDecoder()
    c._setup_uuids_for_brand(WheelBrand.NINEBOT)
    real_sleep = asyncio.sleep

    async def fast_sleep(delay, *a):
        await real_sleep(0.001)
    c.decoder.RESPONSE_TIMEOUT = 0.0

    async def run():
        c._requests_enabled.set()
        monkeypatch.setattr(coord_mod.asyncio, "sleep", fast_sleep)
        task = asyncio.ensure_future(c._keepalive_loop())
        await real_sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        monkeypatch.setattr(coord_mod.asyncio, "sleep", real_sleep)

    with caplog.at_level(logging.DEBUG, logger=coord_mod.__name__):
        asyncio.run(run())
    failures = [r for r in caplog.records if "Request write failed" in r.getMessage()]
    assert len(failures) > 3
    assert sum(r.levelno == logging.WARNING for r in failures) == 1


# --- detection guard ------------------------------------------------------------

@pytest.mark.parametrize("name", ["GotWay_12345", "KS-S18", "LK3336", None])
def test_veteran_detection_always_accepted(name):
    c = coordinator(name)
    assert c._detection_matches_name(VeteranDecoder())


def test_kingsong_named_wheel_still_rejects_gotway_detection():
    c = coordinator("KS-S18")
    assert not c._detection_matches_name(GotwayDecoder())
