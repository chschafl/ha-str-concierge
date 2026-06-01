"""Base entity for STR Concierge."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import STRCoordinator, STRState


class STREntity(CoordinatorEntity[STRCoordinator]):
    """Base class shared by all STR Concierge entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def state_data(self) -> STRState | None:
        return self.coordinator.data

    @property
    def device_info(self):
        # Prefer the live PMS-supplied name; fall back to the friendly name
        # we captured during config flow (e.g. "Beach House"). Last resort
        # is the opaque property ID — only reached for entries created
        # before CONF_PROPERTY_NAME existed.
        state = self.state_data
        name = self.coordinator.property_name
        if state and state.property_name and state.property_name != self.coordinator.property_id:
            name = state.property_name
        return {
            "identifiers": {("str_concierge", self._entry_id, self.coordinator.property_id)},
            "name": name,
            "manufacturer": "STR Concierge",
            "model": "Short-Term Rental",
        }
