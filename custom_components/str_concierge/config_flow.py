"""Config flow for STR Concierge."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_ARRIVAL_WINDOW_MINUTES,
    CONF_BASE_URL,
    CONF_CLEANER_KEYMASTER_SLOT,
    CONF_KEYMASTER_SLOT,
    CONF_LOCK_ENTITY_ID,
    CONF_LOCK_MINUTES_AFTER_CHECKOUT,
    CONF_LOCK_MINUTES_BEFORE_CHECKIN,
    CONF_LOCK_TRIGGER_SOURCE,
    CONF_LOCK_UNLOCK_STATES,
    CONF_POLL_INTERVAL,
    CONF_PROPERTY_ID,
    CONF_PROVIDER,
    CONF_VACANCY_THRESHOLD_DAYS,
    DEFAULT_ARRIVAL_WINDOW_MINUTES,
    DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT,
    DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN,
    DEFAULT_LOCK_TRIGGER_SOURCE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VACANCY_THRESHOLD_DAYS,
    DOMAIN,
    LOCK_TRIGGER_DISABLED,
    LOCK_TRIGGER_ENTITY,
    LOCK_TRIGGER_KEYMASTER,
    PROVIDER_CUSTOM,
    PROVIDER_GUESTY,
    PROVIDER_HOST_TOOLS,
    PROVIDER_HOSTFULLY,
    PROVIDER_OPTIONS,
)
from .providers import create_provider

_LOGGER = logging.getLogger(__name__)

_PROVIDER_LABELS = {
    PROVIDER_HOST_TOOLS: "Host Tools",
    PROVIDER_CUSTOM: "Custom Endpoint",
    PROVIDER_HOSTFULLY: "Hostfully",
    PROVIDER_GUESTY: "Guesty",
}

_LOCK_TRIGGER_LABELS = {
    LOCK_TRIGGER_ENTITY: "Lock / sensor entity state change",
    LOCK_TRIGGER_KEYMASTER: "Keymaster slot event",
    LOCK_TRIGGER_DISABLED: "Disabled — manual buttons only",
}

_NEEDS_BASE_URL = {PROVIDER_CUSTOM}


class STRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step config flow: provider → credentials → property."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider: str | None = None
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._available_properties: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_credentials()

        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER): vol.In(
                    {k: _PROVIDER_LABELS[k] for k in PROVIDER_OPTIONS}
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            self._base_url = user_input.get(CONF_BASE_URL)

            try:
                provider = create_provider(
                    self._provider, self._api_key, self._base_url
                )
                props = await provider.get_properties()
            except Exception as err:
                _LOGGER.debug("Credential validation error: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._available_properties = [
                    {"id": p.id, "name": p.name} for p in props
                ]
                return await self.async_step_property()

        needs_url = self._provider in _NEEDS_BASE_URL
        schema_dict: dict = {vol.Required(CONF_API_KEY): str}
        if needs_url:
            schema_dict[vol.Required(CONF_BASE_URL)] = str

        description_placeholders = {}
        if self._provider == PROVIDER_GUESTY:
            description_placeholders["api_key_hint"] = "Format: client_id:client_secret"
        elif self._provider == PROVIDER_HOSTFULLY:
            description_placeholders["api_key_hint"] = "Your Hostfully API key"
        else:
            description_placeholders["api_key_hint"] = "Your API token / key"

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_property(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title=self._entry_title(),
                data={
                    CONF_PROVIDER: self._provider,
                    CONF_API_KEY: self._api_key,
                    CONF_BASE_URL: self._base_url,
                    CONF_PROPERTY_ID: user_input[CONF_PROPERTY_ID],
                    CONF_POLL_INTERVAL: user_input.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                },
                options={
                    CONF_ARRIVAL_WINDOW_MINUTES: DEFAULT_ARRIVAL_WINDOW_MINUTES,
                    CONF_VACANCY_THRESHOLD_DAYS: DEFAULT_VACANCY_THRESHOLD_DAYS,
                    CONF_LOCK_MINUTES_BEFORE_CHECKIN: DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN,
                    CONF_LOCK_MINUTES_AFTER_CHECKOUT: DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT,
                    CONF_LOCK_TRIGGER_SOURCE: DEFAULT_LOCK_TRIGGER_SOURCE,
                },
            )

        prop_choices = {p["id"]: p["name"] for p in self._available_properties}
        if not prop_choices:
            return self.async_abort(reason="no_properties")

        schema = vol.Schema(
            {
                vol.Required(CONF_PROPERTY_ID): vol.In(prop_choices),
                vol.Optional(
                    CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                ): vol.All(int, vol.Range(min=60, max=3600)),
            }
        )
        return self.async_show_form(
            step_id="property",
            data_schema=schema,
            errors=errors,
        )

    def _entry_title(self) -> str:
        provider_label = _PROVIDER_LABELS.get(self._provider, self._provider)
        if self._base_url:
            return f"{provider_label} ({self._base_url})"
        return provider_label

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return STROptionsFlow(config_entry)


class STROptionsFlow(config_entries.OptionsFlow):
    """Edit arrival window, lock window, and lock trigger source after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            # Normalize unlock states (comma-separated string → list).
            raw_states = user_input.get(CONF_LOCK_UNLOCK_STATES, "")
            if isinstance(raw_states, str):
                user_input[CONF_LOCK_UNLOCK_STATES] = [
                    s.strip() for s in raw_states.split(",") if s.strip()
                ] or ["unlocked"]
            # NumberSelector returns floats; coerce numeric fields back to int.
            for key in (
                CONF_ARRIVAL_WINDOW_MINUTES,
                CONF_VACANCY_THRESHOLD_DAYS,
                CONF_LOCK_MINUTES_BEFORE_CHECKIN,
                CONF_LOCK_MINUTES_AFTER_CHECKOUT,
            ):
                if key in user_input and user_input[key] is not None:
                    user_input[key] = int(user_input[key])
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options
        current_unlock_states = current.get(CONF_LOCK_UNLOCK_STATES, ["unlocked"])
        if isinstance(current_unlock_states, list):
            current_unlock_states = ", ".join(current_unlock_states)

        # Use a text-box number input (not a slider) for every integer field.
        minutes_box = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=10080, step=1, mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="min",
            )
        )
        days_box = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=365, step=1, mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="d",
            )
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ARRIVAL_WINDOW_MINUTES,
                    default=current.get(
                        CONF_ARRIVAL_WINDOW_MINUTES, DEFAULT_ARRIVAL_WINDOW_MINUTES
                    ),
                ): minutes_box,
                vol.Required(
                    CONF_VACANCY_THRESHOLD_DAYS,
                    default=current.get(
                        CONF_VACANCY_THRESHOLD_DAYS, DEFAULT_VACANCY_THRESHOLD_DAYS
                    ),
                ): days_box,
                vol.Required(
                    CONF_LOCK_MINUTES_BEFORE_CHECKIN,
                    default=current.get(
                        CONF_LOCK_MINUTES_BEFORE_CHECKIN,
                        DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN,
                    ),
                ): minutes_box,
                vol.Required(
                    CONF_LOCK_MINUTES_AFTER_CHECKOUT,
                    default=current.get(
                        CONF_LOCK_MINUTES_AFTER_CHECKOUT,
                        DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT,
                    ),
                ): minutes_box,
                vol.Required(
                    CONF_LOCK_TRIGGER_SOURCE,
                    default=current.get(
                        CONF_LOCK_TRIGGER_SOURCE, DEFAULT_LOCK_TRIGGER_SOURCE
                    ),
                ): vol.In(_LOCK_TRIGGER_LABELS),
                vol.Optional(
                    CONF_LOCK_ENTITY_ID,
                    default=current.get(CONF_LOCK_ENTITY_ID, ""),
                ): str,
                vol.Optional(
                    CONF_LOCK_UNLOCK_STATES,
                    default=current_unlock_states,
                ): str,
                vol.Optional(
                    CONF_KEYMASTER_SLOT,
                    default=current.get(CONF_KEYMASTER_SLOT, ""),
                ): str,
                vol.Optional(
                    CONF_CLEANER_KEYMASTER_SLOT,
                    default=current.get(CONF_CLEANER_KEYMASTER_SLOT, ""),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
