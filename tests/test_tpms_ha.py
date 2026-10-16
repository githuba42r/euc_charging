"""TPMS tests that need Home Assistant installed."""

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from euc_charging.tpms_coordinator import TpmsCoordinator  # noqa: E402

ADDRESS = "B9:42:FB:00:02:A6"


def advert(payload: bytes, rssi: int = -70):
    return SimpleNamespace(address=ADDRESS, rssi=rssi, manufacturer_data={0x3000: payload})


def test_coordinator_stores_reading_and_notifies():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    calls = []
    remove = coordinator.async_add_listener(lambda: calls.append(1))

    coordinator.handle_advertisement(advert(bytes.fromhex("b0490136")), None)

    assert coordinator.reading.pressure_kpa == 210.0
    assert coordinator.reading.rssi == -70
    assert coordinator.last_seen is not None
    assert calls == [1]

    remove()
    coordinator.handle_advertisement(advert(bytes.fromhex("b0490137")), None)
    assert calls == [1]
    assert coordinator.reading.pressure_kpa == 211.0


def test_coordinator_ignores_bad_payload():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    calls = []
    coordinator.async_add_listener(lambda: calls.append(1))

    coordinator.handle_advertisement(advert(b"\x01\x02"), None)
    coordinator.handle_advertisement(SimpleNamespace(address=ADDRESS, rssi=-70, manufacturer_data={}), None)

    assert coordinator.reading is None
    assert calls == []
