# TPMS Sensor Support — Design

Date: 2026-10-16
Branch: `feature/charging-current`

## Goal

Expose Motoeye "VD" BLE tyre-pressure sensors (as used on EUCs, and read by
EUC World / MotoEyeFullScreenRemote) in Home Assistant: live pressure,
temperature and sensor battery, plus low-pressure and low-battery alarms.

## Sensor protocol

Source: `MotoEyeFullScreenRemote/app/src/main/java/com/motoeye/remote/tpms/TpmsBleMonitor.kt`
(`scanWindow()` filter, `parseAndStore()` decode) and its README.

- Passive BLE advertisements only — no connection, pairing or commands.
- Local name `VD`; manufacturer data company ID `0x3000` (12288) with a
  4-byte payload. No service UUIDs. Identity is the MAC address only — no
  sensor ID or wheel position in the payload.
- Sensors sleep; they advertise on motion, pressure change or a periodic wake.

| Bytes | Encoding | Value |
|---|---|---|
| 0 | uint8 | battery V = b0 × 0.01 + 1.22; % = clamp((V − 2.0) × 100, 0, 100) |
| 1 | uint8, offset | temperature °C = b1 − 50 |
| 2–3 | uint16 big-endian, absolute kPa | gauge kPa = max(raw − 100, 0) |

Worked example (README): payload `b0 49 01 36` → 2.98 V (98 %), 23 °C,
310 kPa abs → 210 kPa gauge (30.46 psi).

## Decisions

- **Device model:** each sensor is its own HA device, discovered by HA's
  Bluetooth stack (works through ESPHome proxies). Optionally linked to a
  configured wheel, shown via that wheel (`via_device_id`).
- **Alarms:** pressure alarm is **minimum only** — on when gauge pressure is
  below a per-sensor minimum (entered in psi, default 30 psi). Low-battery
  alarm uses a fixed threshold: battery below 20 % (2.2 V).
- **Sleeping sensors keep their last values** (not `unavailable`), with a
  Last Seen timestamp; values are restored across HA restarts.
- **Out of scope:** the HUD JSON relay path, other TPMS vendors,
  target ± tolerance alarms, staleness alarms.

## Approach

A custom advertisement listener rather than HA's
`PassiveBluetoothProcessorCoordinator`, because the latter marks entities
unavailable once advertisements stop — a parked wheel's sensor would flap to
unavailable and blank the alarm.

## Components

### `tpms.py` (new)

- `TpmsReading` dataclass: `battery_voltage`, `battery_percent`,
  `temperature`, `pressure_kpa` (gauge), `rssi`.
- `decode_tpms(payload: bytes) -> TpmsReading | None` — pure function, no HA
  imports; returns `None` for payloads shorter than 4 bytes.
- `is_tpms_advertisement(name, manufacturer_data) -> bool` — name starts with
  `VD` (case-insensitive) and company ID `0x3000` present.
- `TpmsCoordinator` — one per TPMS config entry. Registers
  `bluetooth.async_register_callback` for the entry's address
  (`BluetoothScanningMode.PASSIVE`), decodes each advert, stores
  `reading` + `last_seen`, and notifies listeners. No polling, no timeouts.

### Config flow (`config_flow.py`)

- `manifest.json` adds a Bluetooth matcher `{"manufacturer_id": 12288, "connectable": false}`.
  HA requires `local_name` matchers to have ≥ 3 characters, so `VD` cannot
  be matched there; the config flow checks the name and aborts otherwise.
- `async_step_bluetooth` branches: if the discovery is a TPMS advert →
  `async_step_tpms_confirm`; otherwise the existing wheel path.
- `tpms_confirm` form: name (default `TPMS <last 5 of MAC>`), optional wheel
  (select from existing wheel config entries of this domain), minimum
  pressure (psi, default 30).
- Entry data: `{address, entry_type: "tpms", wheel_address?}`; options:
  `{min_pressure_psi}`. Unique ID = sensor MAC.
- Options flow for TPMS entries: edit minimum pressure. (Wheel entries keep
  no options flow.)

### Setup (`__init__.py`)

- If `entry.data["entry_type"] == "tpms"`: create `TpmsCoordinator`, forward
  `SENSOR` + `BINARY_SENSOR` only; reload on options update. Otherwise the
  existing wheel setup unchanged. Existing wheel entries have no
  `entry_type` and default to the wheel path (no migration needed).

### Entities

`sensor.py` / `binary_sensor.py` `async_setup_entry` delegate to TPMS entity
classes when the entry is a TPMS entry. TPMS entities are
`CoordinatorEntity`-style listeners that also `RestoreEntity`, always
available once a value exists.

Device: name from entry title, manufacturer "Motoeye", model "VD TPMS". When linked, `via_device_id` is the wheel's device-registry id, resolved with `async_get_device_by_identifier((DOMAIN, wheel_address), <wheel config entry id>)` (HA 2026.10 deprecates `via_device` and `async_get_device`); omitted when the wheel device isn't found.

| Entity | Type | Details |
|---|---|---|
| Pressure | sensor | PRESSURE, native kPa (gauge), suggested unit psi |
| Temperature | sensor | TEMPERATURE, °C |
| Battery | sensor | BATTERY, % |
| Battery Voltage | sensor | VOLTAGE, V, disabled by default |
| Signal Strength | sensor | SIGNAL_STRENGTH, dBm, disabled by default |
| Last Seen | sensor | TIMESTAMP |
| Low Pressure | binary_sensor | PROBLEM; on when pressure < min (psi→kPa) |
| Low Battery | binary_sensor | BATTERY; on when battery % < 20 |

Binary sensors are `None` (unknown) until a first reading exists.

## Error handling

- Short/invalid payloads are ignored (logged at debug).
- Adverts from other MACs never reach a coordinator (callback is
  address-filtered).
- A linked wheel that is later removed leaves the TPMS device standing
  (via_device is cosmetic).

## Testing

- `tests/test_tpms.py` (no HA): README vector; pressure below atmospheric
  clamps to 0; battery % clamps at 0/100; short payload → `None`;
  advertisement matcher (name case, missing company ID, other names);
  alarm predicate helpers (`is_low_pressure(reading, min_psi)`,
  `is_low_battery(reading)`).
- Import check of `config_flow`, `sensor`, `binary_sensor` under real HA.
- Live check when a sensor next wakes near a proxy.
