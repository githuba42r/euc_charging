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
