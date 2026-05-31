"""Sensor platform for STR Concierge.

Exposes the guest, guest lifecycle status, house (housekeeping) state,
and lock-access window as HA sensors. Single-guest scope — when the booking
rotates, the new guest takes the same `Guest` entity.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, GUEST_STATES, HOUSE_STATES
from .coordinator import STRCoordinator
from .entity import STREntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: STRCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities(
        [
            GuestNameSensor(coordinator, entry.entry_id),
            GuestDoorCodeSensor(coordinator, entry.entry_id),
            GuestStatusSensor(coordinator, entry.entry_id),
            HouseStateSensor(coordinator, entry.entry_id),
            GuestCheckinSensor(coordinator, entry.entry_id),
            GuestCheckoutSensor(coordinator, entry.entry_id),
            LockAccessStartSensor(coordinator, entry.entry_id),
            LockAccessEndSensor(coordinator, entry.entry_id),
        ]
    )


class GuestNameSensor(STREntity, SensorEntity):
    _attr_translation_key = "guest"
    _attr_icon = "mdi:account"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_guest_name"

    @property
    def native_value(self) -> str | None:
        s = self.state_data
        return s.current_guest.name if s and s.current_guest else None

    @property
    def extra_state_attributes(self) -> dict:
        s = self.state_data
        if not s or not s.current_guest:
            return {}
        return {"booking_id": s.current_guest.booking_id}


class GuestDoorCodeSensor(STREntity, SensorEntity):
    _attr_translation_key = "door_code"
    _attr_icon = "mdi:lock-smart"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_door_code"

    @property
    def native_value(self) -> str | None:
        s = self.state_data
        return s.current_guest.door_code if s and s.current_guest else None


class GuestStatusSensor(STREntity, SensorEntity):
    _attr_translation_key = "guest_status"
    _attr_icon = "mdi:account-clock"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = GUEST_STATES

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_guest_status"

    @property
    def native_value(self) -> str | None:
        s = self.state_data
        return s.guest_status if s else None

    @property
    def extra_state_attributes(self) -> dict:
        s = self.state_data
        if not s:
            return {}
        return {"entered_at": s.entered_at.isoformat() if s.entered_at else None}


class HouseStateSensor(STREntity, SensorEntity):
    _attr_translation_key = "house_state"
    _attr_icon = "mdi:home-variant"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = HOUSE_STATES

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_house_state"

    @property
    def native_value(self) -> str | None:
        s = self.state_data
        return s.house_state if s else None


class _GuestTimestampSensor(STREntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP


class GuestCheckinSensor(_GuestTimestampSensor):
    _attr_translation_key = "checkin"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_checkin"

    @property
    def native_value(self) -> datetime | None:
        s = self.state_data
        return s.current_guest.checkin if s and s.current_guest else None


class GuestCheckoutSensor(_GuestTimestampSensor):
    _attr_translation_key = "checkout"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_checkout"

    @property
    def native_value(self) -> datetime | None:
        s = self.state_data
        return s.current_guest.checkout if s and s.current_guest else None


class LockAccessStartSensor(_GuestTimestampSensor):
    _attr_translation_key = "lock_access_start"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_lock_access_start"

    @property
    def native_value(self) -> datetime | None:
        s = self.state_data
        return s.lock_access_start if s else None


class LockAccessEndSensor(_GuestTimestampSensor):
    _attr_translation_key = "lock_access_end"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_lock_access_end"

    @property
    def native_value(self) -> datetime | None:
        s = self.state_data
        return s.lock_access_end if s else None
