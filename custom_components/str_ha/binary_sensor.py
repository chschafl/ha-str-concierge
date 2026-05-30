"""Binary sensor: `Guest Present` — strictly `on` when the guest is in-house."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, GUEST_IN_HOUSE
from .coordinator import STRCoordinator
from .entity import STREntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: STRCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([GuestPresentSensor(coordinator, entry.entry_id)])


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
