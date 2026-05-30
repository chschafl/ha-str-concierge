"""Sensor platform for STR HA.

Exposes guest info and lock window times as HA sensor entities.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CHECKIN_OFFSET_MINUTES,
    CONF_CHECKOUT_OFFSET_MINUTES,
    DEFAULT_CHECKIN_OFFSET_MINUTES,
    DEFAULT_CHECKOUT_OFFSET_MINUTES,
    DOMAIN,
)
from .coordinator import STRCoordinator
from .entity import STREntity
from .providers.base import Guest

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: STRCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    property_ids: list[str] = hass.data[DOMAIN][entry.entry_id]["property_ids"]

    checkin_offset = entry.options.get(CONF_CHECKIN_OFFSET_MINUTES, DEFAULT_CHECKIN_OFFSET_MINUTES)
    checkout_offset = entry.options.get(CONF_CHECKOUT_OFFSET_MINUTES, DEFAULT_CHECKOUT_OFFSET_MINUTES)

    entities: list[SensorEntity] = []
    for prop_id in property_ids:
        for attr in ("name", "phone", "email", "door_code", "status"):
            entities.append(GuestSensor(coordinator, prop_id, entry.entry_id, "current", attr))
        entities.append(GuestDatetimeSensor(coordinator, prop_id, entry.entry_id, "current", "checkin"))
        entities.append(GuestDatetimeSensor(coordinator, prop_id, entry.entry_id, "current", "checkout"))

        for attr in ("name", "phone", "email", "door_code"):
            entities.append(GuestSensor(coordinator, prop_id, entry.entry_id, "next", attr))
        entities.append(GuestDatetimeSensor(coordinator, prop_id, entry.entry_id, "next", "checkin"))
        entities.append(GuestDatetimeSensor(coordinator, prop_id, entry.entry_id, "next", "checkout"))

        entities.append(LockWindowSensor(coordinator, prop_id, entry.entry_id, "start", checkin_offset))
        entities.append(LockWindowSensor(coordinator, prop_id, entry.entry_id, "end", checkout_offset))

    async_add_entities(entities)


class GuestSensor(STREntity, SensorEntity):
    """A plain text sensor for a guest attribute."""

    _LABELS = {
        "name": "Name",
        "phone": "Phone",
        "email": "Email",
        "door_code": "Door Code",
        "status": "Status",
    }

    def __init__(
        self,
        coordinator: STRCoordinator,
        property_id: str,
        entry_id: str,
        slot: str,
        attribute: str,
    ) -> None:
        super().__init__(coordinator, property_id, entry_id)
        self._slot = slot
        self._attribute = attribute
        label = self._LABELS.get(attribute, attribute.replace("_", " ").title())
        self._attr_name = f"{slot.title()} Guest {label}"
        self._attr_unique_id = f"{entry_id}_{property_id}_{slot}_guest_{attribute}"

    def _guest(self) -> Guest | None:
        pd = self.property_data
        if pd is None:
            return None
        return pd.current_guest if self._slot == "current" else pd.next_guest

    @property
    def native_value(self) -> str | None:
        guest = self._guest()
        if guest is None:
            return None
        return getattr(guest, self._attribute, None)

    @property
    def extra_state_attributes(self) -> dict:
        guest = self._guest()
        if guest is None:
            return {}
        return {"booking_id": guest.booking_id}


class GuestDatetimeSensor(STREntity, SensorEntity):
    """A datetime sensor for checkin/checkout times."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: STRCoordinator,
        property_id: str,
        entry_id: str,
        slot: str,
        timing: str,
    ) -> None:
        super().__init__(coordinator, property_id, entry_id)
        self._slot = slot
        self._timing = timing
        label = "Check-in" if timing == "checkin" else "Check-out"
        self._attr_name = f"{slot.title()} Guest {label}"
        self._attr_unique_id = f"{entry_id}_{property_id}_{slot}_guest_{timing}"

    def _guest(self) -> Guest | None:
        pd = self.property_data
        if pd is None:
            return None
        return pd.current_guest if self._slot == "current" else pd.next_guest

    @property
    def native_value(self) -> datetime | None:
        guest = self._guest()
        if guest is None:
            return None
        return getattr(guest, self._timing, None)


class LockWindowSensor(STREntity, SensorEntity):
    """Exposes the calculated lock access window start/end as a timestamp."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: STRCoordinator,
        property_id: str,
        entry_id: str,
        edge: str,
        offset_minutes: int,
    ) -> None:
        super().__init__(coordinator, property_id, entry_id)
        self._edge = edge
        self._offset = timedelta(minutes=offset_minutes)
        label = "Lock Access Start" if edge == "start" else "Lock Access End"
        self._attr_name = label
        self._attr_unique_id = f"{entry_id}_{property_id}_lock_{edge}"

    @property
    def native_value(self) -> datetime | None:
        pd = self.property_data
        if pd is None:
            return None

        if self._edge == "start":
            guest = pd.current_guest or pd.next_guest
            if guest is None:
                return None
            return guest.checkin - self._offset
        else:
            if pd.current_guest is None:
                return None
            return pd.current_guest.checkout + self._offset

    @property
    def extra_state_attributes(self) -> dict:
        return {"offset_minutes": int(self._offset.total_seconds() / 60)}
