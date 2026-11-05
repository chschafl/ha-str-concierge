"""Config flow for STR Concierge."""

from __future__ import annotations

import logging
from collections.abc import Mapping
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
    CONF_PROPERTY_NAME,
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
from .providers.base import Property, is_auth_error

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


def _api_key_hint(provider: str | None) -> str:
    if provider == PROVIDER_GUESTY:
        return "Format: client_id:client_secret"
    if provider == PROVIDER_HOSTFULLY:
        return "Your Hostfully API key"
    return "Your API token / key"


async def _async_fetch_properties(
    provider_type: str | None, api_key: str, base_url: str | None
) -> tuple[list[Property], str | None]:
    """Validate credentials by listing properties.

    Returns ``(properties, error_key)``; ``error_key`` is ``None`` on success.
    """
    try:
        provider = create_provider(provider_type, api_key, base_url)
        return await provider.get_properties(), None
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Credential validation error: %s", err)
        return [], "invalid_auth" if is_auth_error(err) else "cannot_connect"


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
    ) -> config_entries.ConfigFlowResult:
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
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            self._base_url = user_input.get(CONF_BASE_URL)

            props, error = await _async_fetch_properties(
                self._provider, self._api_key, self._base_url
            )
            if error:
                errors["base"] = error
            else:
                self._available_properties = [
                    {"id": p.id, "name": p.name} for p in props
                ]
                return await self.async_step_property()

        needs_url = self._provider in _NEEDS_BASE_URL
        schema_dict: dict = {vol.Required(CONF_API_KEY): str}
        if needs_url:
            schema_dict[vol.Required(CONF_BASE_URL)] = str

        description_placeholders = {"api_key_hint": _api_key_hint(self._provider)}

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_property(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            picked_id = user_input[CONF_PROPERTY_ID]
            # Look up the picked property's friendly name so the HA device
            # registry shows "Beach House" rather than an opaque listing ID.
            picked_name = next(
                (p["name"] for p in self._available_properties if p["id"] == picked_id),
                picked_id,
            )
            return self.async_create_entry(
                title=self._entry_title(),
                data={
                    CONF_PROVIDER: self._provider,
                    CONF_API_KEY: self._api_key,
                    CONF_BASE_URL: self._base_url,
                    CONF_PROPERTY_ID: picked_id,
                    CONF_PROPERTY_NAME: picked_name,
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

    # ── Reconfigure (Settings → Devices & Services → ⋮ → Reconfigure) ──

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user replace the API key (and base URL) of an existing entry."""
        entry = self._get_reconfigure_entry()
        return await self._async_update_credentials(
            "reconfigure", entry, user_input, allow_base_url=True
        )

    # ── Reauth (triggered automatically when the provider returns 401/403) ──

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        entry = self._get_reauth_entry()
        return await self._async_update_credentials(
            "reauth_confirm", entry, user_input, allow_base_url=False
        )

    async def _async_update_credentials(
        self,
        step_id: str,
        entry: config_entries.ConfigEntry,
        user_input: dict[str, Any] | None,
        *,
        allow_base_url: bool,
    ) -> config_entries.ConfigFlowResult:
        """Shared form for reconfigure + reauth.

        Validates the new credential against the provider and makes sure it
        still sees the property this entry tracks, then updates the entry in
        place — entity IDs, history, and options are preserved.
        """
        provider_type = entry.data[CONF_PROVIDER]
        property_id = entry.data[CONF_PROPERTY_ID]
        needs_url = allow_base_url and provider_type in _NEEDS_BASE_URL
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            base_url = (
                user_input.get(CONF_BASE_URL)
                if needs_url
                else entry.data.get(CONF_BASE_URL)
            )
            props, error = await _async_fetch_properties(
                provider_type, api_key, base_url
            )
            if error:
                errors["base"] = error
            elif not any(p.id == property_id for p in props):
                errors["base"] = "property_not_found"
            else:
                data_updates: dict[str, Any] = {CONF_API_KEY: api_key}
                if needs_url:
                    data_updates[CONF_BASE_URL] = base_url
                return self.async_update_reload_and_abort(
                    entry, data_updates=data_updates
                )

        schema_dict: dict = {vol.Required(CONF_API_KEY): str}
        if needs_url:
            schema_dict[
                vol.Required(
                    CONF_BASE_URL, default=entry.data.get(CONF_BASE_URL) or ""
                )
            ] = str

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "api_key_hint": _api_key_hint(provider_type),
                "property_name": entry.data.get(CONF_PROPERTY_NAME, property_id),
            },
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
    ) -> config_entries.ConfigFlowResult:
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
