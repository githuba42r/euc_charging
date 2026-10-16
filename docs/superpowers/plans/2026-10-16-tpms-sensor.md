# TPMS Sensor Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Motoeye "VD" BLE TPMS sensors in the `euc_charging` HA integration as their own devices with pressure/temperature/battery sensors and Low Pressure / Low Battery binary sensors.

**Architecture:** A pure decoder module (`tpms.py`, no HA imports) plus a small HA advertisement-listener coordinator (`tpms_coordinator.py`) and TPMS entity classes (`tpms_entities.py`). TPMS config entries are tagged `entry_type: "tpms"`; `__init__.py`, `sensor.py` and `binary_sensor.py` branch on that tag so the existing wheel path is untouched.

**Tech Stack:** Python 3.12+, Home Assistant 2026.10 (`homeassistant.components.bluetooth`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-tpms-sensor-design.md`

## Global Constraints

- Work on branch `feature/charging-current`; commit after each task; never push.
- Do not add `Co-Authored-By` lines to commits.
- Test runner: `$V/bin/python -m pytest` where
  `V=/tmp/claude-1000/-home-philg-working-hass-euc-charging/742ed3e9-5147-4aa4-ad34-52005770c0f8/scratchpad/venv`
  (has `pytest`, `homeassistant`, `bleak` installed). Run from repo root
  `/home/philg/working/hass-euc-charging`.
- `tests/conftest.py` registers `custom_components/euc_charging` as package
  `euc_charging` (no `__init__.py` execution) and aliases `const` and
  `decoders`. New HA-free test modules import `euc_charging.<module>`.
  Tests that need HA must start with `pytest.importorskip("homeassistant")`.
- Payload decode (verbatim from spec): battery V = b0 × 0.01 + 1.22;
  % = clamp((V − 2.0) × 100, 0, 100); °C = b1 − 50; pressure raw = uint16
  big-endian b2..b3 (absolute kPa); gauge kPa = max(raw − 100, 0).
- Advertisement: name starts with `VD` (case-insensitive) AND manufacturer
  company ID `0x3000` (12288) present with ≥ 4 bytes.
- Pressure alarm: minimum only, configured in psi, default 30 psi.
  Low battery: battery % < 20.
- HA `local_name` matchers need ≥ 3 characters, so the manifest matcher is
  `{"manufacturer_id": 12288}` only; the config flow enforces the `VD` name.
- Entry data keys: `address`, `entry_type` (`"tpms"`), optional
  `wheel_address`. Entry options key: `min_pressure_psi`.
- Existing wheel entries have no `entry_type`; they must keep working
  unchanged.
- CI runs hassfest + HACS validation: manifest and `translations/en.json`
  must stay valid JSON and every new config/options step needs translations.

## File Structure

| File | Responsibility |
|---|---|
| `custom_components/euc_charging/const.py` (modify) | TPMS constants + `is_tpms_entry()` |
| `custom_components/euc_charging/tpms.py` (create) | Pure decode, advert matcher, alarm predicates |
| `custom_components/euc_charging/tpms_coordinator.py` (create) | Subscribes to one sensor's adverts, holds latest reading |
| `custom_components/euc_charging/tpms_entities.py` (create) | TPMS sensor/binary sensor entities + platform setup helpers |
| `custom_components/euc_charging/sensor.py` (modify) | Delegate TPMS entries to `tpms_entities` |
| `custom_components/euc_charging/binary_sensor.py` (modify) | Delegate TPMS entries to `tpms_entities` |
| `custom_components/euc_charging/__init__.py` (modify) | TPMS setup/unload branch |
| `custom_components/euc_charging/config_flow.py` (modify) | TPMS discovery confirm step + options flow |
| `custom_components/euc_charging/manifest.json` (modify) | Bluetooth matcher for company ID 12288 |
| `custom_components/euc_charging/translations/en.json` (modify) | Strings for new steps |
| `tests/test_tpms.py` (create) | Decoder/predicate tests (no HA) |
| `tests/test_tpms_ha.py` (create) | Coordinator + config-flow helper tests (needs HA) |

---

### Task 1: TPMS constants and pure decoder

**Files:**
- Modify: `custom_components/euc_charging/const.py` (append at end of file)
- Create: `custom_components/euc_charging/tpms.py`
- Test: `tests/test_tpms.py`

**Interfaces:**
- Produces (const.py): `CONF_ENTRY_TYPE = "entry_type"`, `ENTRY_TYPE_TPMS = "tpms"`, `CONF_WHEEL_ADDRESS = "wheel_address"`, `CONF_MIN_PRESSURE_PSI = "min_pressure_psi"`, `DEFAULT_MIN_PRESSURE_PSI = 30.0`, `TPMS_MANUFACTURER_ID = 0x3000`, `TPMS_LOW_BATTERY_PERCENT = 20`, `KPA_PER_PSI = 6.894757`, `is_tpms_entry(data: Mapping[str, Any]) -> bool`.
- Produces (tpms.py): `TpmsReading(battery_voltage: float, battery_percent: int, temperature: int, pressure_kpa: float, rssi: int | None)` (frozen dataclass); `decode_tpms(payload: bytes, rssi: int | None = None) -> TpmsReading | None`; `is_tpms_advertisement(name: str | None, manufacturer_data: Mapping[int, bytes]) -> bool`; `is_low_pressure(reading: TpmsReading, min_pressure_psi: float) -> bool`; `is_low_battery(reading: TpmsReading) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tpms.py`:

```python
"""Tests for Motoeye VD TPMS advertisement decoding (no Home Assistant)."""

import unittest

from euc_charging.const import ENTRY_TYPE_TPMS, is_tpms_entry
from euc_charging.tpms import (
    TpmsReading,
    decode_tpms,
    is_low_battery,
    is_low_pressure,
    is_tpms_advertisement,
)

# Worked example from MotoEyeFullScreenRemote README / TpmsBleMonitor.kt
README_PAYLOAD = bytes.fromhex("b0490136")


class TestDecodeTpms(unittest.TestCase):

    def test_readme_example(self):
        reading = decode_tpms(README_PAYLOAD, rssi=-70)
        self.assertAlmostEqual(reading.battery_voltage, 2.98, places=2)
        self.assertEqual(reading.battery_percent, 98)
        self.assertEqual(reading.temperature, 23)
        self.assertAlmostEqual(reading.pressure_kpa, 210.0)
        self.assertEqual(reading.rssi, -70)

    def test_pressure_below_atmospheric_clamps_to_zero(self):
        reading = decode_tpms(bytes([0xB0, 0x49, 0x00, 0x50]))  # 80 kPa abs
        self.assertEqual(reading.pressure_kpa, 0.0)

    def test_battery_percent_clamps(self):
        self.assertEqual(decode_tpms(bytes([0x00, 0x49, 0x01, 0x36])).battery_percent, 0)    # 1.22 V
        self.assertEqual(decode_tpms(bytes([0xFF, 0x49, 0x01, 0x36])).battery_percent, 100)  # 3.77 V

    def test_temperature_offset(self):
        self.assertEqual(decode_tpms(bytes([0xB0, 0x00, 0x01, 0x36])).temperature, -50)

    def test_short_payload(self):
        self.assertIsNone(decode_tpms(b"\xb0\x49\x01"))
        self.assertIsNone(decode_tpms(b""))


class TestIsTpmsAdvertisement(unittest.TestCase):

    def test_matches(self):
        self.assertTrue(is_tpms_advertisement("VD", {0x3000: README_PAYLOAD}))
        self.assertTrue(is_tpms_advertisement("vd", {0x3000: README_PAYLOAD}))

    def test_rejects(self):
        self.assertFalse(is_tpms_advertisement("VD", {}))
        self.assertFalse(is_tpms_advertisement("VD", {0x004C: README_PAYLOAD}))
        self.assertFalse(is_tpms_advertisement("VD", {0x3000: b"\x01\x02"}))
        self.assertFalse(is_tpms_advertisement("LK3336", {0x3000: README_PAYLOAD}))
        self.assertFalse(is_tpms_advertisement(None, {0x3000: README_PAYLOAD}))


class TestAlarms(unittest.TestCase):

    def reading(self, pressure_kpa=210.0, battery_percent=98):
        return TpmsReading(2.98, battery_percent, 23, pressure_kpa, None)

    def test_low_pressure(self):
        # 30 psi = 206.84 kPa
        self.assertFalse(is_low_pressure(self.reading(210.0), 30))
        self.assertTrue(is_low_pressure(self.reading(200.0), 30))

    def test_low_battery(self):
        self.assertFalse(is_low_battery(self.reading(battery_percent=20)))
        self.assertTrue(is_low_battery(self.reading(battery_percent=19)))


class TestIsTpmsEntry(unittest.TestCase):

    def test_entry_type(self):
        self.assertTrue(is_tpms_entry({"address": "B9:42:FB:00:02:A6", "entry_type": ENTRY_TYPE_TPMS}))
        self.assertFalse(is_tpms_entry({"address": "88:25:83:F3:5D:30"}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$V/bin/python -m pytest tests/test_tpms.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'euc_charging.tpms'` (or ImportError for `ENTRY_TYPE_TPMS`).

- [ ] **Step 3: Add constants to const.py**

Append to the end of `custom_components/euc_charging/const.py` (add `from collections.abc import Mapping` and `from typing import Any` to the imports at the top of the file):

```python
# TPMS (Motoeye "VD" BLE advertisement sensors)
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_TPMS = "tpms"
CONF_WHEEL_ADDRESS = "wheel_address"
CONF_MIN_PRESSURE_PSI = "min_pressure_psi"
DEFAULT_MIN_PRESSURE_PSI = 30.0
TPMS_MANUFACTURER_ID = 0x3000
TPMS_LOW_BATTERY_PERCENT = 20
KPA_PER_PSI = 6.894757


def is_tpms_entry(data: Mapping[str, Any]) -> bool:
    """Return True if config entry data describes a TPMS sensor."""
    return data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TPMS
```

- [ ] **Step 4: Create tpms.py**

Create `custom_components/euc_charging/tpms.py`:

```python
"""Decoding for Motoeye "VD" BLE tyre pressure sensors.

The sensors only advertise; there is no connection or pairing. Each advert
carries manufacturer data under company ID 0x3000 with a 4-byte payload:

  byte 0     battery: V = b0 * 0.01 + 1.22
  byte 1     temperature: C = b1 - 50
  bytes 2-3  pressure: uint16 big-endian, absolute kPa

Source: MotoEyeFullScreenRemote TpmsBleMonitor.kt (parseAndStore).
This module has no Home Assistant imports so it can be unit tested directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .const import KPA_PER_PSI, TPMS_LOW_BATTERY_PERCENT, TPMS_MANUFACTURER_ID

ATMOSPHERIC_KPA = 100
TPMS_NAME_PREFIX = "VD"


@dataclass(frozen=True)
class TpmsReading:
    """One decoded TPMS advertisement."""

    battery_voltage: float
    battery_percent: int
    temperature: int
    pressure_kpa: float  # gauge pressure
    rssi: int | None


def decode_tpms(payload: bytes, rssi: int | None = None) -> TpmsReading | None:
    """Decode a 0x3000 manufacturer data payload; None if too short."""
    if len(payload) < 4:
        return None
    voltage = round(payload[0] * 0.01 + 1.22, 2)
    percent = max(0, min(100, round((voltage - 2.0) * 100)))
    temperature = payload[1] - 50
    absolute_kpa = (payload[2] << 8) | payload[3]
    gauge_kpa = float(max(absolute_kpa - ATMOSPHERIC_KPA, 0))
    return TpmsReading(voltage, percent, temperature, gauge_kpa, rssi)


def is_tpms_advertisement(name: str | None, manufacturer_data: Mapping[int, bytes]) -> bool:
    """Return True if an advertisement comes from a VD TPMS sensor."""
    if not name or not name.upper().startswith(TPMS_NAME_PREFIX):
        return False
    payload = manufacturer_data.get(TPMS_MANUFACTURER_ID)
    return payload is not None and len(payload) >= 4


def is_low_pressure(reading: TpmsReading, min_pressure_psi: float) -> bool:
    """Return True if gauge pressure is below the configured minimum."""
    return reading.pressure_kpa < min_pressure_psi * KPA_PER_PSI


def is_low_battery(reading: TpmsReading) -> bool:
    """Return True if the sensor battery is below the low threshold."""
    return reading.battery_percent < TPMS_LOW_BATTERY_PERCENT
```

Note: `round()` (not `int()`) is deliberate — (2.98 − 2.0) × 100 is 97.999… in floating point.

- [ ] **Step 5: Run tests to verify they pass**

Run: `$V/bin/python -m pytest tests/test_tpms.py -q`
Expected: all tests PASS. Then run the full suite: `$V/bin/python -m pytest tests -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/euc_charging/const.py custom_components/euc_charging/tpms.py tests/test_tpms.py
git commit -m "feat: Add Motoeye VD TPMS advertisement decoder"
```

---

### Task 2: TPMS coordinator

**Files:**
- Create: `custom_components/euc_charging/tpms_coordinator.py`
- Test: `tests/test_tpms_ha.py`

**Interfaces:**
- Consumes: `decode_tpms`, `TpmsReading` (Task 1); `TPMS_MANUFACTURER_ID` (Task 1).
- Produces: `class TpmsCoordinator` with `__init__(self, hass: HomeAssistant, address: str)`, attributes `address: str`, `reading: TpmsReading | None`, `last_seen: datetime | None`; methods `async_start() -> None` (callback), `async_shutdown() -> None` (async), `async_add_listener(update_callback: Callable[[], None]) -> Callable[[], None]` (callback, returns remover), `handle_advertisement(service_info, change) -> None` (callback; public so tests can drive it).

- [ ] **Step 1: Write the failing test**

Create `tests/test_tpms_ha.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$V/bin/python -m pytest tests/test_tpms_ha.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'euc_charging.tpms_coordinator'`.

- [ ] **Step 3: Implement the coordinator**

Create `custom_components/euc_charging/tpms_coordinator.py`:

```python
"""Listens for one TPMS sensor's BLE advertisements."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import TPMS_MANUFACTURER_ID
from .tpms import TpmsReading, decode_tpms

_LOGGER = logging.getLogger(__name__)


class TpmsCoordinator:
    """Holds the latest reading for one sensor and notifies entities.

    Deliberately not a PassiveBluetoothProcessorCoordinator: sensors sleep
    between adverts, and entities must keep their last values rather than
    become unavailable.
    """

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self.reading: TpmsReading | None = None
        self.last_seen: datetime | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsub_advert: Callable[[], None] | None = None

    @callback
    def async_start(self) -> None:
        """Subscribe to this sensor's advertisements."""
        self._unsub_advert = bluetooth.async_register_callback(
            self.hass,
            self.handle_advertisement,
            bluetooth.BluetoothCallbackMatcher(
                address=self.address, manufacturer_id=TPMS_MANUFACTURER_ID
            ),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )

    async def async_shutdown(self) -> None:
        """Stop listening for advertisements."""
        if self._unsub_advert:
            self._unsub_advert()
            self._unsub_advert = None

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register an entity update callback; returns a remover."""
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            self._listeners.remove(update_callback)

        return remove

    @callback
    def handle_advertisement(self, service_info, change) -> None:
        """Decode an advertisement and notify listeners."""
        payload = service_info.manufacturer_data.get(TPMS_MANUFACTURER_ID)
        reading = decode_tpms(payload, service_info.rssi) if payload else None
        if reading is None:
            _LOGGER.debug("Ignoring TPMS advert from %s: %s", self.address, payload)
            return
        self.reading = reading
        self.last_seen = dt_util.utcnow()
        for update_callback in list(self._listeners):
            update_callback()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$V/bin/python -m pytest tests/test_tpms_ha.py -q` → PASS. Then `$V/bin/python -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/euc_charging/tpms_coordinator.py tests/test_tpms_ha.py
git commit -m "feat: Add TPMS advertisement coordinator"
```

---

### Task 3: TPMS entities and platform delegation

**Files:**
- Create: `custom_components/euc_charging/tpms_entities.py`
- Modify: `custom_components/euc_charging/sensor.py` (`async_setup_entry`, ~line 213)
- Modify: `custom_components/euc_charging/binary_sensor.py` (`async_setup_entry`, ~line 39)

**Interfaces:**
- Consumes: `TpmsCoordinator` (Task 2: `.address`, `.reading`, `.last_seen`, `.async_add_listener`); `is_low_pressure`, `is_low_battery` (Task 1); const keys (Task 1).
- Produces: `async_setup_tpms_sensors(hass, entry, async_add_entities) -> None` and `async_setup_tpms_binary_sensors(hass, entry, async_add_entities) -> None`. Both read the coordinator from `hass.data[DOMAIN][entry.entry_id]` (stored by Task 4).

- [ ] **Step 1: Create tpms_entities.py**

```python
"""Entities for Motoeye VD TPMS sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    STATE_ON,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_MIN_PRESSURE_PSI,
    CONF_WHEEL_ADDRESS,
    DEFAULT_MIN_PRESSURE_PSI,
    DOMAIN,
)
from .tpms import is_low_battery, is_low_pressure
from .tpms_coordinator import TpmsCoordinator


@dataclass(frozen=True, kw_only=True)
class TpmsSensorDescription(SensorEntityDescription):
    """Describes a TPMS sensor; value_fn reads from the coordinator."""

    value_fn: Callable[[TpmsCoordinator], Any]


TPMS_SENSORS: tuple[TpmsSensorDescription, ...] = (
    TpmsSensorDescription(
        key="pressure",
        name="Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.KPA,
        suggested_unit_of_measurement=UnitOfPressure.PSI,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.reading.pressure_kpa if c.reading else None,
    ),
    TpmsSensorDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.reading.temperature if c.reading else None,
    ),
    TpmsSensorDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.reading.battery_percent if c.reading else None,
    ),
    TpmsSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.reading.battery_voltage if c.reading else None,
    ),
    TpmsSensorDescription(
        key="rssi",
        name="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.reading.rssi if c.reading else None,
    ),
    TpmsSensorDescription(
        key="last_seen",
        name="Last Seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.last_seen,
    ),
)


class TpmsEntity(Entity):
    """Common device/unique-id/listener handling for TPMS entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: TpmsCoordinator, entry: ConfigEntry, key: str) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{coordinator.address}_{key}"
        wheel_address = entry.data.get(CONF_WHEEL_ADDRESS)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=entry.title,
            manufacturer="Motoeye",
            model="VD TPMS",
            via_device=(DOMAIN, wheel_address) if wheel_address else None,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self._update_from_coordinator()
        self.async_write_ha_state()

    def _update_from_coordinator(self) -> None:
        raise NotImplementedError


class TpmsSensor(TpmsEntity, RestoreSensor):
    """A TPMS reading that keeps its last value while the sensor sleeps."""

    entity_description: TpmsSensorDescription

    def __init__(self, coordinator: TpmsCoordinator, entry: ConfigEntry,
                 description: TpmsSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.reading is not None:
            self._update_from_coordinator()
        elif (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value

    def _update_from_coordinator(self) -> None:
        self._attr_native_value = self.entity_description.value_fn(self.coordinator)


class TpmsAlarm(TpmsEntity, BinarySensorEntity, RestoreEntity):
    """A TPMS alarm that keeps its last state while the sensor sleeps."""

    def __init__(self, coordinator: TpmsCoordinator, entry: ConfigEntry,
                 description: BinarySensorEntityDescription,
                 predicate: Callable[[TpmsCoordinator], bool]) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._predicate = predicate

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.reading is not None:
            self._update_from_coordinator()
        elif (last := await self.async_get_last_state()) is not None and last.state in ("on", "off"):
            self._attr_is_on = last.state == STATE_ON

    def _update_from_coordinator(self) -> None:
        self._attr_is_on = self._predicate(self.coordinator)


async def async_setup_tpms_sensors(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add TPMS sensors for a TPMS config entry."""
    coordinator: TpmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(TpmsSensor(coordinator, entry, d) for d in TPMS_SENSORS)


async def async_setup_tpms_binary_sensors(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Low Pressure / Low Battery alarms for a TPMS config entry."""
    coordinator: TpmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    min_psi = entry.options.get(CONF_MIN_PRESSURE_PSI, DEFAULT_MIN_PRESSURE_PSI)
    async_add_entities([
        TpmsAlarm(
            coordinator, entry,
            BinarySensorEntityDescription(
                key="low_pressure", name="Low Pressure",
                device_class=BinarySensorDeviceClass.PROBLEM,
            ),
            lambda c: is_low_pressure(c.reading, min_psi),
        ),
        TpmsAlarm(
            coordinator, entry,
            BinarySensorEntityDescription(
                key="low_battery", name="Low Battery",
                device_class=BinarySensorDeviceClass.BATTERY,
            ),
            lambda c: is_low_battery(c.reading),
        ),
    ])
```

- [ ] **Step 2: Delegate from sensor.py**

In `custom_components/euc_charging/sensor.py`, change the `.const` import line to
`from .const import DOMAIN, is_tpms_entry, sanitize_wheel_id`, add
`from .tpms_entities import async_setup_tpms_sensors`, and make the start of
`async_setup_entry` read:

```python
    """Set up the Leaperkim sensors."""
    if is_tpms_entry(entry.data):
        await async_setup_tpms_sensors(hass, entry, async_add_entities)
        return

    coordinator: EucChargingCoordinator = hass.data[DOMAIN][entry.entry_id]
```

- [ ] **Step 3: Delegate from binary_sensor.py**

In `custom_components/euc_charging/binary_sensor.py`, change the `.const` import line to
`from .const import DOMAIN, is_tpms_entry, sanitize_wheel_id`, add
`from .tpms_entities import async_setup_tpms_binary_sensors`, and make the start of
`async_setup_entry` read:

```python
    """Set up the Leaperkim binary sensors."""
    if is_tpms_entry(entry.data):
        await async_setup_tpms_binary_sensors(hass, entry, async_add_entities)
        return

    coordinator: EucChargingCoordinator = hass.data[DOMAIN][entry.entry_id]
```

- [ ] **Step 4: Verify imports under real HA**

Run:
```bash
$V/bin/python -c "
from custom_components.euc_charging import sensor, binary_sensor, tpms_entities
print([d.key for d in tpms_entities.TPMS_SENSORS])"
```
Expected: `['pressure', 'temperature', 'battery', 'battery_voltage', 'rssi', 'last_seen']`.
Then `$V/bin/python -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/euc_charging/tpms_entities.py custom_components/euc_charging/sensor.py custom_components/euc_charging/binary_sensor.py
git commit -m "feat: Add TPMS sensor and alarm entities"
```

---

### Task 4: Entry setup/unload for TPMS

**Files:**
- Modify: `custom_components/euc_charging/__init__.py`

**Interfaces:**
- Consumes: `TpmsCoordinator(hass, address)`, `.async_start()`, `.async_shutdown()` (Task 2); `is_tpms_entry` (Task 1).
- Produces: `hass.data[DOMAIN][entry.entry_id]` holds a `TpmsCoordinator` for TPMS entries (read by Task 3 setup helpers). Options changes reload the entry.

- [ ] **Step 1: Implement the branch**

Replace the body of `custom_components/euc_charging/__init__.py` from the
`PLATFORMS` line through `async_unload_entry` with:

```python
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]
TPMS_PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Leaperkim EUC from a config entry."""
    if is_tpms_entry(entry.data):
        return await _async_setup_tpms_entry(hass, entry)

    address = entry.data[CONF_ADDRESS]
```

(keep the rest of the existing wheel setup body unchanged), then add after
`async_setup_entry`:

```python
async def _async_setup_tpms_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a TPMS sensor entry (advertisement listener only)."""
    coordinator = TpmsCoordinator(hass, entry.data[CONF_ADDRESS])
    coordinator.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, TPMS_PLATFORMS)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a TPMS entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
```

and change `async_unload_entry` to:

```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = TPMS_PLATFORMS if is_tpms_entry(entry.data) else PLATFORMS
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
```

Update imports: `from .const import DOMAIN, STORAGE_VERSION, is_tpms_entry`
and add `from .tpms_coordinator import TpmsCoordinator`.

- [ ] **Step 2: Verify**

Run:
```bash
$V/bin/python -c "import custom_components.euc_charging as m; print(m.TPMS_PLATFORMS)"
$V/bin/python -m pytest tests -q
```
Expected: `[<Platform.SENSOR: 'sensor'>, <Platform.BINARY_SENSOR: 'binary_sensor'>]`; all tests pass.

- [ ] **Step 3: Commit**

```bash
git add custom_components/euc_charging/__init__.py
git commit -m "feat: Set up TPMS config entries"
```

---

### Task 5: Discovery config flow, options flow, manifest, translations

**Files:**
- Modify: `custom_components/euc_charging/config_flow.py` (imports; `async_step_bluetooth` ~line 192; new steps; options flow)
- Modify: `custom_components/euc_charging/manifest.json`
- Modify: `custom_components/euc_charging/translations/en.json`
- Test: `tests/test_tpms_ha.py` (append)

**Interfaces:**
- Consumes: `is_tpms_advertisement` (Task 1); const keys (Task 1).
- Produces: config entries with `data={address, entry_type:"tpms", wheel_address?}`, `options={min_pressure_psi}`; `TpmsOptionsFlow`; module-level helper `build_tpms_entry(address: str, user_input: dict) -> tuple[dict, dict]` returning `(data, options)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tpms_ha.py`:

```python
from euc_charging.config_flow import NO_WHEEL, build_tpms_entry  # noqa: E402


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$V/bin/python -m pytest tests/test_tpms_ha.py -q`
Expected: ImportError — `cannot import name 'NO_WHEEL'`.

- [ ] **Step 3: Implement the config flow changes**

In `custom_components/euc_charging/config_flow.py`:

Imports — change to:

```python
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    ALL_SERVICE_UUIDS,
    CONF_ENTRY_TYPE,
    CONF_MIN_PRESSURE_PSI,
    CONF_WHEEL_ADDRESS,
    DEFAULT_MIN_PRESSURE_PSI,
    DEVICE_NAMES,
    DOMAIN,
    ENTRY_TYPE_TPMS,
    SERVICE_UUID,
    is_tpms_entry,
    match_brand_by_name,
)
from .tpms import is_tpms_advertisement
```

Module-level, after `_LOGGER`:

```python
NO_WHEEL = "none"
MIN_PRESSURE_SCHEMA = vol.All(vol.Coerce(float), vol.Range(min=1, max=150))


def build_tpms_entry(address: str, user_input: dict[str, Any]) -> tuple[dict, dict]:
    """Return (data, options) for a TPMS config entry from the confirm form."""
    data: dict[str, Any] = {CONF_ADDRESS: address, CONF_ENTRY_TYPE: ENTRY_TYPE_TPMS}
    wheel = user_input.get(CONF_WHEEL_ADDRESS)
    if wheel and wheel != NO_WHEEL:
        data[CONF_WHEEL_ADDRESS] = wheel
    options = {CONF_MIN_PRESSURE_PSI: float(user_input[CONF_MIN_PRESSURE_PSI])}
    return data, options
```

In `async_step_bluetooth`, insert right after `self._abort_if_unique_id_configured()`:

```python
        if is_tpms_advertisement(discovery_info.name, discovery_info.manufacturer_data):
            self._discovered_device = discovery_info
            return await self.async_step_tpms_confirm()
```

Add these methods to `EucChargingConfigFlow`:

```python
    async def async_step_tpms_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a discovered TPMS sensor: name, wheel link, minimum pressure."""
        assert self._discovered_device is not None
        address = self._discovered_device.address

        if user_input is not None:
            data, options = build_tpms_entry(address, user_input)
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=data, options=options
            )

        wheel_options = [SelectOptionDict(value=NO_WHEEL, label="None")] + [
            SelectOptionDict(value=entry.data[CONF_ADDRESS], label=entry.title)
            for entry in self._async_current_entries()
            if not is_tpms_entry(entry.data)
        ]
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=f"TPMS {address[-5:]}"): str,
            vol.Required(CONF_WHEEL_ADDRESS, default=NO_WHEEL): SelectSelector(
                SelectSelectorConfig(options=wheel_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_MIN_PRESSURE_PSI, default=DEFAULT_MIN_PRESSURE_PSI): MIN_PRESSURE_SCHEMA,
        })
        return self.async_show_form(
            step_id="tpms_confirm",
            data_schema=schema,
            description_placeholders={"address": address},
        )

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        """Only TPMS entries have options."""
        return is_tpms_entry(config_entry.data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the TPMS options flow."""
        return TpmsOptionsFlow()
```

Add at the end of the module:

```python
class TpmsOptionsFlow(OptionsFlow):
    """Edit a TPMS sensor's minimum pressure."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_MIN_PRESSURE_PSI: float(user_input[CONF_MIN_PRESSURE_PSI])}
            )

        current = self.config_entry.options.get(CONF_MIN_PRESSURE_PSI, DEFAULT_MIN_PRESSURE_PSI)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_MIN_PRESSURE_PSI, default=current): MIN_PRESSURE_SCHEMA,
            }),
        )
```

- [ ] **Step 4: Manifest matcher**

In `custom_components/euc_charging/manifest.json`, append to the `"bluetooth"` array:

```json
    {
      "manufacturer_id": 12288,
      "connectable": false
    }
```

- [ ] **Step 5: Translations**

In `custom_components/euc_charging/translations/en.json`, add inside `config.step` (after `bluetooth_confirm`):

```json
            "tpms_confirm": {
                "title": "Add TPMS Sensor",
                "description": "Found a Motoeye TPMS sensor ({address}). Name it, optionally link it to a wheel, and set the minimum tyre pressure for the Low Pressure alarm.",
                "data": {
                    "name": "Name",
                    "wheel_address": "Wheel",
                    "min_pressure_psi": "Minimum pressure (psi)"
                }
            }
```

and add a top-level `options` block (sibling of `config`):

```json
    "options": {
        "step": {
            "init": {
                "title": "TPMS Sensor Options",
                "data": {
                    "min_pressure_psi": "Minimum pressure (psi)"
                }
            }
        }
    },
```

Validate: `python3 -m json.tool custom_components/euc_charging/translations/en.json > /dev/null && python3 -m json.tool custom_components/euc_charging/manifest.json > /dev/null && echo ok`

- [ ] **Step 6: Run tests and import check**

Run:
```bash
$V/bin/python -m pytest tests -q
$V/bin/python -c "from custom_components.euc_charging import config_flow; print(config_flow.TpmsOptionsFlow)"
```
Expected: all tests pass; class printed.

- [ ] **Step 7: Commit**

```bash
git add custom_components/euc_charging/config_flow.py custom_components/euc_charging/manifest.json custom_components/euc_charging/translations/en.json tests/test_tpms_ha.py
git commit -m "feat: Discover TPMS sensors with config and options flows"
```

---

### Task 6: Spec correction and final verification

**Files:**
- Modify: `docs/superpowers/specs/2026-10-16-tpms-sensor-design.md` (Config flow section, manifest matcher line)

- [ ] **Step 1: Correct the spec's manifest matcher**

Replace the line ``- `manifest.json` adds a Bluetooth matcher:`` and the following
matcher line with:

```markdown
- `manifest.json` adds a Bluetooth matcher `{"manufacturer_id": 12288}`.
  HA requires `local_name` matchers to have ≥ 3 characters, so `VD` cannot
  be matched there; the config flow checks the name and aborts otherwise.
```

- [ ] **Step 2: Full verification**

Run:
```bash
$V/bin/python -m pytest tests -q
$V/bin/python -c "
from custom_components.euc_charging import config_flow, sensor, binary_sensor, tpms_entities, tpms_coordinator
import custom_components.euc_charging as pkg
print('imports ok')"
python3 -m json.tool custom_components/euc_charging/manifest.json > /dev/null && echo manifest ok
```
Expected: all tests pass, `imports ok`, `manifest ok`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-16-tpms-sensor-design.md
git commit -m "docs: Note manufacturer-id-only TPMS matcher in spec"
```

Live verification (after deploying to HA, outside this plan): when a VD sensor wakes near a proxy, HA shows a "TPMS sensor discovered" flow; after adding, Pressure ≈ the reading EUC World / MotoEye shows.
