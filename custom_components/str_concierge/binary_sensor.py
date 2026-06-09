"""Binary sensors:

- `Guest Present` — `on` while the guest is in-house.
- `Lock Active`   — `on` while the lock-access window is open (between
  lock_access_start and lock_access_end). Drives "should the door code be
  active right now" automations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, GUEST_IN_HOUSE
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
            GuestPresentSensor(coordinator, entry.entry_id),
            LockActiveSensor(coordinator, entry.entry_id),
        ]
    )


class GuestPresentSensor(STREntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_translation_key = "guest_present"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_guest_present"

    @property
    def is_on(self) -> bool:
        s = self.state_data
        return bool(s and s.guest_status == GUEST_IN_HOUSE)


class LockActiveSensor(STREntity, BinarySensorEntity):
    # State depends on wall-clock time crossing the lock-access window edges,
    # not just on coordinator data, so we re-check every minute on our own
    # timer in addition to following coordinator updates.
    _REEVAL_INTERVAL = timedelta(minutes=1)

    _attr_translation_key = "lock_active"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_lock_active"

    @property
    def is_on(self) -> bool:
        s = self.state_data
        if s is None or s.lock_access_start is None or s.lock_access_end is None:
            return False
        now = datetime.now(UTC)
        return s.lock_access_start <= now <= s.lock_access_end

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _tick(_now: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_time_interval(self.hass, _tick, self._REEVAL_INTERVAL)
        )
