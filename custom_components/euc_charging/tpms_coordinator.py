"""Listens for one TPMS sensor's BLE advertisements."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

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
        """Subscribe to this sensor's advertisements.

        async_register_advertisement_callback fires for every advert from the
        address, connectable or not and even when the data is unchanged, so
        Last Seen and RSSI stay current. (async_register_callback without
        ``connectable`` in its matcher only sees connectable adverts, which
        these sensors never send.) The last advert already heard is replayed
        first so entities have a value straight after setup.
        """
        self._unsub_advert = bluetooth.async_register_advertisement_callback(
            self.hass, self.handle_advertisement, self.address
        )
        last = bluetooth.async_last_service_info(self.hass, self.address, connectable=False)
        if last is not None:
            self.handle_advertisement(last)

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
    def handle_advertisement(self, service_info) -> None:
        """Decode an advertisement and notify listeners.

        ``last_seen`` comes from the advert's own monotonic receive time, so a
        replayed (older) advert is not stamped as just received.
        """
        payload = service_info.manufacturer_data.get(TPMS_MANUFACTURER_ID)
        reading = decode_tpms(payload, service_info.rssi) if payload else None
        if reading is None:
            _LOGGER.debug("Ignoring TPMS advert from %s: %s", self.address, payload)
            return
        self.reading = reading
        age = max(0.0, bluetooth.MONOTONIC_TIME() - service_info.time)
        self.last_seen = dt_util.utcnow() - timedelta(seconds=age)
        self.async_notify_listeners()

    @callback
    def async_notify_listeners(self) -> None:
        """Tell entities to refresh (new reading, or options changed)."""
        for update_callback in list(self._listeners):
            update_callback()
