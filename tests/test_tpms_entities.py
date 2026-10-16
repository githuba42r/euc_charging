"""Tests for TPMS entities (device info, sensor value_fns, alarms).

No running hass is needed: entities are constructed directly and their
state-computation methods are called without going through the entity
platform (never call async_write_ha_state here).
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from euc_charging.const import CONF_MIN_PRESSURE_PSI, DOMAIN  # noqa: E402
from euc_charging.tpms_coordinator import TpmsCoordinator  # noqa: E402
from euc_charging.tpms_entities import (  # noqa: E402
    TPMS_SENSORS,
    TpmsEntity,
    build_tpms_alarms,
)

ADDRESS = "B9:42:FB:00:02:A6"
README_PAYLOAD = bytes.fromhex("b0490136")


def advert(payload: bytes, rssi: int = -70):
    return SimpleNamespace(address=ADDRESS, rssi=rssi, manufacturer_data={0x3000: payload})


def make_entry(title: str = "Front Wheel TPMS", options: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(title=title, data={}, options=options or {})


# --- DeviceInfo -------------------------------------------------------------

def test_device_info_with_via_device_id():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    entry = make_entry()

    entity = TpmsEntity(coordinator, entry, "pressure", via_device_id="wheel-device-id")

    info = entity._attr_device_info
    assert info["via_device_id"] == "wheel-device-id"
    assert info["identifiers"] == {(DOMAIN, ADDRESS)}
    assert DOMAIN == "euc_charging"
    assert info["manufacturer"] == "Motoeye"
    assert info["model"] == "VD TPMS"
    assert info["name"] == entry.title


def test_device_info_without_via_device_id():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    entry = make_entry()

    entity = TpmsEntity(coordinator, entry, "pressure")

    assert "via_device_id" not in entity._attr_device_info


# --- TPMS_SENSORS value_fn ---------------------------------------------------

def test_sensor_value_fns_return_none_without_a_reading():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)

    values = {d.key: d.value_fn(coordinator) for d in TPMS_SENSORS}

    assert values == {
        "pressure": None,
        "temperature": None,
        "battery": None,
        "battery_voltage": None,
        "rssi": None,
        "last_seen": None,
    }
    assert coordinator.last_seen is None


def test_sensor_value_fns_after_advertisement():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    coordinator.handle_advertisement(advert(README_PAYLOAD), None)

    values = {d.key: d.value_fn(coordinator) for d in TPMS_SENSORS}

    assert values["pressure"] == 210.0
    assert values["temperature"] == 23
    assert values["battery"] == 98
    assert values["last_seen"] is coordinator.last_seen
    assert values["last_seen"] is not None


# --- Alarms -------------------------------------------------------------------

def test_low_pressure_alarm_false_when_above_threshold():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    coordinator.handle_advertisement(advert(README_PAYLOAD), None)
    entry = make_entry(options={CONF_MIN_PRESSURE_PSI: 30})

    low_pressure, low_battery = build_tpms_alarms(coordinator, entry)
    low_pressure._update_from_coordinator()
    low_battery._update_from_coordinator()

    assert low_pressure._attr_is_on is False
    assert low_battery._attr_is_on is False


def test_low_pressure_alarm_true_when_below_threshold():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    coordinator.handle_advertisement(advert(README_PAYLOAD), None)
    entry = make_entry(options={CONF_MIN_PRESSURE_PSI: 31})

    low_pressure, _low_battery = build_tpms_alarms(coordinator, entry)
    low_pressure._update_from_coordinator()

    assert low_pressure._attr_is_on is True


def test_low_battery_alarm_false_for_98_percent():
    coordinator = TpmsCoordinator(hass=None, address=ADDRESS)
    coordinator.handle_advertisement(advert(README_PAYLOAD), None)
    entry = make_entry(options={CONF_MIN_PRESSURE_PSI: 30})

    _low_pressure, low_battery = build_tpms_alarms(coordinator, entry)
    low_battery._update_from_coordinator()

    assert low_battery._attr_is_on is False
