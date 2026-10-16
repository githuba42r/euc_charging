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
    return is_below_min_pressure(reading.pressure_kpa, min_pressure_psi)


def is_below_min_pressure(pressure_kpa: float, min_pressure_psi: float) -> bool:
    """Return True if a gauge pressure in kPa is below a minimum in psi."""
    return pressure_kpa < min_pressure_psi * KPA_PER_PSI


def is_low_battery(reading: TpmsReading) -> bool:
    """Return True if the sensor battery is below the low threshold."""
    return reading.battery_percent < TPMS_LOW_BATTERY_PERCENT
