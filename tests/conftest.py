"""Shared pytest fixtures for STR Concierge tests."""
from __future__ import annotations

pytest_plugins = "pytest_homeassistant_custom_component"

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.str_concierge.const import (
    CONF_API_KEY,
    CONF_ARRIVAL_WINDOW_MINUTES,
    CONF_LOCK_MINUTES_AFTER_CHECKOUT,
    CONF_LOCK_MINUTES_BEFORE_CHECKIN,
    CONF_POLL_INTERVAL,
    CONF_PROPERTY_ID,
    CONF_PROVIDER,
    CONF_VACANCY_THRESHOLD_DAYS,
    DEFAULT_ARRIVAL_WINDOW_MINUTES,
    DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT,
    DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN,
    DEFAULT_VACANCY_THRESHOLD_DAYS,
    DOMAIN,
    PROVIDER_CUSTOM,
    PROVIDER_HOST_TOOLS,
)
from custom_components.str_concierge.providers.base import Guest, Property, PropertyData

# ── Datetime helpers ──────────────────────────────────────────────────

def dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


# ── Sample data ───────────────────────────────────────────────────────

CURRENT_GUEST = Guest(
    booking_id="booking-001",
    name="Alice Smith",
    checkin=dt("2025-06-01T15:00:00"),
    checkout=dt("2025-06-07T11:00:00"),
    door_code="1234",
)

NEXT_GUEST = Guest(
    booking_id="booking-002",
    name="Bob Jones",
    checkin=dt("2025-06-08T15:00:00"),
    checkout=dt("2025-06-10T11:00:00"),
    door_code="5678",
)

SAMPLE_PROPERTY = Property(id="prop-001", name="Beach House")

SAMPLE_PROPERTY_DATA = PropertyData(
    property_id="prop-001",
    property_name="Beach House",
    current_guest=CURRENT_GUEST,
    next_guest=NEXT_GUEST,
)


# ── Config entry fixtures ─────────────────────────────────────────────

@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="test-entry",
        data={
            CONF_PROVIDER: PROVIDER_HOST_TOOLS,
            CONF_API_KEY: "test-api-key",
            CONF_PROPERTY_ID: "prop-001",
            CONF_POLL_INTERVAL: 300,
        },
        options={
            CONF_ARRIVAL_WINDOW_MINUTES: DEFAULT_ARRIVAL_WINDOW_MINUTES,
            CONF_VACANCY_THRESHOLD_DAYS: DEFAULT_VACANCY_THRESHOLD_DAYS,
            CONF_LOCK_MINUTES_BEFORE_CHECKIN: DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN,
            CONF_LOCK_MINUTES_AFTER_CHECKOUT: DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT,
        },
    )


@pytest.fixture
def mock_custom_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="test-custom-entry",
        data={
            CONF_PROVIDER: PROVIDER_CUSTOM,
            CONF_API_KEY: "test-token",
            "base_url": "https://my-backend.example.com/api",
            CONF_PROPERTY_ID: "prop-001",
            CONF_POLL_INTERVAL: 300,
        },
        options={
            CONF_ARRIVAL_WINDOW_MINUTES: 240,
            CONF_VACANCY_THRESHOLD_DAYS: 30,
            CONF_LOCK_MINUTES_BEFORE_CHECKIN: 60,
            CONF_LOCK_MINUTES_AFTER_CHECKOUT: 60,
        },
    )


# ── Provider mock ─────────────────────────────────────────────────────

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.get_properties = AsyncMock(return_value=[SAMPLE_PROPERTY])
    provider.get_property_data = AsyncMock(return_value=SAMPLE_PROPERTY_DATA)
    provider.mark_arrived = AsyncMock(return_value=True)
    provider.mark_checked_out = AsyncMock(return_value=True)
    return provider
