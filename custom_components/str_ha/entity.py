"""Base entity for STR HA."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import STRCoordinator


class STREntity(CoordinatorEntity[STRCoordinator]):
    """Base class shared by all STR HA entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: STRCoordinator,
        property_id: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._property_id = property_id
        self._entry_id = entry_id

    @property
    def property_data(self):
        """Return this entity's PropertyData from the coordinator."""
        return self.coordinator.data.get(self._property_id)

    @property
    def device_info(self):
        """Group all entities for a property under one device."""
        prop_data = self.property_data
        name = prop_data.property_name if prop_data else self._property_id
        return {
            "identifiers": {("str_ha", self._entry_id, self._property_id)},
            "name": name,
            "manufacturer": "STR HA",
            "model": "Short-Term Rental",
        }
