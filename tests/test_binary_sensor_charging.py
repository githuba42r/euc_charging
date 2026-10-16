"""Charging binary sensor: unknown when the protocol has no charging flag."""

from types import SimpleNamespace

import pytest

from euc_charging.binary_sensor import BINARY_SENSORS, EucChargingBinarySensor


def _charging_entity(data):
    entity = object.__new__(EucChargingBinarySensor)
    entity.coordinator = SimpleNamespace(data=data)
    entity.entity_description = BINARY_SENSORS[0]
    return entity


@pytest.mark.parametrize("data, expected", [
    ({"is_charging": None, "voltage": 80.0}, None),     # KingSong/Gotway/InMotion V1
    ({"is_charging": True}, True),
    ({"is_charging": False}, False),
    (None, False),                                         # disconnected, unchanged
])
def test_charging_binary_sensor_unknown(data, expected):
    assert _charging_entity(data).is_on is expected


