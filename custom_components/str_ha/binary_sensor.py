"""Binary sensor platform for STR HA."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import STRCoordinator
from .entity import STREntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: STRCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    property_ids: list[str] = hass.data[DOMAIN][entry.entry_id]["property_ids"]

    async_add_entities(
        GuestPresentSensor(coordinator, prop_id, entry.entry_id)
        for prop_id in property_ids
    )


class GuestPresentSensor(STREntity, BinarySensorEntity):
    """True when the current guest has marked as arrived (or is within stay window)."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_name = "Guest Present"

    def __init__(
        self,
        coordinator: STRCoordinator,
        property_id: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, property_id, entry_id)
        self._attr_unique_id = f"{entry_id}_{property_id}_guest_present"

    @property
    def is_on(self) -> bool:
        pd = self.property_data
        if pd is None or pd.current_guest is None:
            return False
        return pd.current_guest.status in ("arrived", "confirmed") and pd.current_guest.is_active
