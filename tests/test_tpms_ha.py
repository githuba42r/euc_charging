"""TPMS tests that need Home Assistant installed."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components import bluetooth  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402

from euc_charging import tpms_coordinator  # noqa: E402
from euc_charging.tpms_coordinator import TpmsCoordinator  # noqa: E402
from euc_charging import config_flow  # noqa: E402
from euc_charging.config_flow import (  # noqa: E402
    NO_WHEEL,
    EucChargingConfigFlow,
    build_tpms_entry,
    build_wheel_options,
)

ADDRESS = "B9:42:FB:00:02:A6"


def advert(payload: bytes, rssi: int = -70, time: float | None = None):
    return SimpleNamespace(
        address=ADDRESS,
        rssi=rssi,
        manufacturer_data={0x3000: payload},
        time=bluetooth.MONOTONIC_TIME() if time is None else time,
    )


def test_coordinator_stores_reading_and_notifies():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    calls = []
    remove = coordinator.async_add_listener(lambda: calls.append(1))

    coordinator.handle_advertisement(advert(bytes.fromhex("b0490136")))

    assert coordinator.reading.pressure_kpa == 210.0
    assert coordinator.reading.rssi == -70
    assert coordinator.last_seen is not None
    assert calls == [1]

    remove()
    coordinator.handle_advertisement(advert(bytes.fromhex("b0490137")))
    assert calls == [1]
    assert coordinator.reading.pressure_kpa == 211.0


def test_coordinator_ignores_bad_payload():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    calls = []
    coordinator.async_add_listener(lambda: calls.append(1))

    coordinator.handle_advertisement(advert(b"\x01\x02"))
    coordinator.handle_advertisement(SimpleNamespace(address=ADDRESS, rssi=-70, manufacturer_data={}, time=0.0))

    assert coordinator.reading is None
    assert calls == []


def test_last_seen_reflects_advert_time(monkeypatch):
    monkeypatch.setattr(tpms_coordinator.bluetooth, "MONOTONIC_TIME", lambda: 1000.0)
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)

    coordinator.handle_advertisement(advert(bytes.fromhex("b0490136"), time=940.0))

    expected = dt_util.utcnow() - timedelta(seconds=60)
    assert abs((coordinator.last_seen - expected).total_seconds()) < 2


def test_last_seen_never_in_future(monkeypatch):
    monkeypatch.setattr(tpms_coordinator.bluetooth, "MONOTONIC_TIME", lambda: 1000.0)
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)

    coordinator.handle_advertisement(advert(bytes.fromhex("b0490136"), time=1005.0))

    assert coordinator.last_seen <= dt_util.utcnow()


def _patch_bluetooth(monkeypatch, last_info):
    registered = []
    lookups = []

    def fake_register(hass, callback, address):
        registered.append((hass, callback, address))
        return lambda: registered.append("unsubscribed")

    def fake_last(hass, address, connectable=True):
        lookups.append((hass, address, connectable))
        return last_info

    monkeypatch.setattr(
        tpms_coordinator.bluetooth, "async_register_advertisement_callback", fake_register
    )
    monkeypatch.setattr(tpms_coordinator.bluetooth, "async_last_service_info", fake_last)
    return registered, lookups


def test_async_start_registers_for_every_advert_and_seeds(monkeypatch):
    hass = object()
    registered, lookups = _patch_bluetooth(monkeypatch, advert(bytes.fromhex("b0490136")))
    coordinator = TpmsCoordinator(hass=hass, address=ADDRESS)

    coordinator.async_start()

    assert registered == [(hass, coordinator.handle_advertisement, ADDRESS)]
    assert lookups == [(hass, ADDRESS, False)]
    assert coordinator.reading.pressure_kpa == 210.0
    assert coordinator.last_seen is not None

    asyncio.run(coordinator.async_shutdown())
    assert registered[-1] == "unsubscribed"


def test_async_start_without_history_has_no_reading(monkeypatch):
    registered, _lookups = _patch_bluetooth(monkeypatch, None)
    coordinator = TpmsCoordinator(hass=object(), address=ADDRESS)

    coordinator.async_start()

    assert len(registered) == 1
    assert coordinator.reading is None
    assert coordinator.last_seen is None


def test_build_tpms_entry_with_wheel():
    data, options = build_tpms_entry(
        ADDRESS, {"name": "Front", "wheel_address": "88:25:83:F3:5D:30", "min_pressure_psi": 32}
    )
    assert data == {"address": ADDRESS, "entry_type": "tpms", "wheel_address": "88:25:83:F3:5D:30"}
    assert options == {"min_pressure_psi": 32.0}


def test_build_tpms_entry_without_wheel():
    data, options = build_tpms_entry(
        ADDRESS, {"name": "Front", "wheel_address": NO_WHEEL, "min_pressure_psi": 30}
    )
    assert data == {"address": ADDRESS, "entry_type": "tpms"}
    assert options == {"min_pressure_psi": 30.0}


def test_build_wheel_options_skips_tpms_and_ignored_entries():
    entries = [
        SimpleNamespace(title="Front TPMS", data={"address": ADDRESS, "entry_type": "tpms"}),
        SimpleNamespace(title="LK3336", data={"address": "88:25:83:F3:5D:30"}),
        SimpleNamespace(title="Ignored", data={}),  # ignored discovery: empty data
    ]

    options = build_wheel_options(entries)

    assert options == [
        {"value": NO_WHEEL, "label": "None"},
        {"value": "88:25:83:F3:5D:30", "label": "LK3336"},
    ]


def test_build_wheel_options_only_none_without_wheels():
    assert build_wheel_options([]) == [{"value": NO_WHEEL, "label": "None"}]


def _service_info(name, address, manufacturer_data=None, service_uuids=None):
    return SimpleNamespace(
        name=name, address=address, rssi=-60,
        manufacturer_data=manufacturer_data or {}, service_uuids=service_uuids or [],
    )


def test_user_step_excludes_tpms_sensors_even_when_showing_all(monkeypatch):
    infos = [
        _service_info("VD-02A6", ADDRESS, {0x3000: bytes.fromhex("b0490136")}),
        _service_info("LK3336", "88:25:83:F3:5D:30"),
    ]
    monkeypatch.setattr(config_flow, "async_discovered_service_info", lambda hass: infos)
    flow = EucChargingConfigFlow()
    flow.hass = object()
    monkeypatch.setattr(flow, "_async_current_ids", lambda: set())
    shown = {}
    monkeypatch.setattr(flow, "async_show_form", lambda **kw: shown.update(kw) or kw)
    flow._show_all_devices = True

    asyncio.run(flow.async_step_user())

    assert list(flow._discovered_devices) == ["88:25:83:F3:5D:30"]
    assert shown["step_id"] == "user"
