"""Shared pytest fixtures for STR HA tests."""
from __future__ import annotations

pytest_plugins = "pytest_homeassistant_custom_component"

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.str_ha.const import (
    CONF_API_KEY,
    CONF_POLL_INTERVAL,
    CONF_PROPERTY_IDS,
    CONF_PROVIDER,
    DEFAULT_CHECKIN_OFFSET_MINUTES,
    DEFAULT_CHECKOUT_OFFSET_MINUTES,
    CONF_CHECKIN_OFFSET_MINUTES,
    CONF_CHECKOUT_OFFSET_MINUTES,
    DOMAIN,
    PROVIDER_HOST_TOOLS,
    PROVIDER_CUSTOM,
)
from custom_components.str_ha.providers.base import Guest, Property, PropertyData


# ── Datetime helpers ──────────────────────────────────────────────────

def dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


# ── Sample data ──────────────────────────────────────────────────

CURRENT_GUEST = Guest(
    booking_id="booking-001",
    name="Alice Smith",
    phone="+1-555-0100",
    email="alice@example.com",
    checkin=dt("2025-06-01T15:00:00"),
    checkout=dt("2025-06-07T11:00:00"),
    door_code="1234",
    status="confirmed",
)

NEXT_GUEST = Guest(
    booking_id="booking-002",
    name="Bob Jones",
    phone="+1-555-0200",
    email="bob@example.com",
    checkin=dt("2025-06-08T15:00:00"),
    checkout=dt("2025-06-10T11:00:00"),
    door_code="5678",
    status="confirmed",
)

SAMPLE_PROPERTY = Property(id="prop-001", name="Beach House")

SAMPLE_PROPERTY_DATA = PropertyData(
    property_id="prop-001",
    property_name="Beach House",
    current_guest=CURRENT_GUEST,
    next_guest=NEXT_GUEST,
)


# ── Config entry fixtures ───────────────────────────────────────────────

@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="test-entry",
        data={
            CONF_PROVIDER: PROVIDER_HOST_TOOLS,
            CONF_API_KEY: "test-api-key",
            CONF_PROPERTY_IDS: ["prop-001"],
            CONF_POLL_INTERVAL: 300,
        },
        options={
            CONF_CHECKIN_OFFSET_MINUTES: DEFAULT_CHECKIN_OFFSET_MINUTES,
            CONF_CHECKOUT_OFFSET_MINUTES: DEFAULT_CHECKOUT_OFFSET_MINUTES,
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
            CONF_PROPERTY_IDS: ["prop-001"],
            CONF_POLL_INTERVAL: 300,
        },
        options={
            CONF_CHECKIN_OFFSET_MINUTES: 60,
            CONF_CHECKOUT_OFFSET_MINUTES: 60,
        },
    )


# ── Provider mock ───────────────────────────────────────────────────

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.get_properties = AsyncMock(return_value=[SAMPLE_PROPERTY])
    provider.get_property_data = AsyncMock(return_value=SAMPLE_PROPERTY_DATA)
    provider.mark_arrived = AsyncMock(return_value=True)
    provider.mark_checked_out = AsyncMock(return_value=True)
    return provider
