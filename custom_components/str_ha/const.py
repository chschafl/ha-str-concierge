"""Constants for the Short-Term Rental Manager integration."""

DOMAIN = "str_ha"
PLATFORMS = ["sensor", "binary_sensor", "button"]

# Config entry keys
CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_PROPERTY_IDS = "property_ids"
CONF_POLL_INTERVAL = "poll_interval"

# Options keys (editable after setup)
CONF_CHECKIN_OFFSET_MINUTES = "checkin_offset_minutes"
CONF_CHECKOUT_OFFSET_MINUTES = "checkout_offset_minutes"
CONF_KEYMASTER_SLOT = "keymaster_slot"

# Provider identifiers
PROVIDER_HOST_TOOLS = "host_tools"
PROVIDER_CUSTOM = "custom_endpoint"
PROVIDER_HOSTFULLY = "hostfully"
PROVIDER_GUESTY = "guesty"

PROVIDER_OPTIONS = [
    PROVIDER_HOST_TOOLS,
    PROVIDER_CUSTOM,
    PROVIDER_HOSTFULLY,
    PROVIDER_GUESTY,
]

# Defaults
DEFAULT_POLL_INTERVAL = 300  # 5 minutes
DEFAULT_CHECKIN_OFFSET_MINUTES = 0
DEFAULT_CHECKOUT_OFFSET_MINUTES = 60  # allow lock 1h after checkout by default

# HA events fired when guest data changes
EVENT_GUEST_CHANGED = f"{DOMAIN}_guest_changed"
EVENT_NEXT_GUEST_CHANGED = f"{DOMAIN}_next_guest_changed"

# Booking status values
STATUS_CONFIRMED = "confirmed"
STATUS_ARRIVED = "arrived"
STATUS_CHECKED_OUT = "checked_out"

# Keymaster entity pattern
KEYMASTER_CODE_SLOT_PATTERN = "input_text.keymaster_{slot}_pin"
KEYMASTER_ENABLED_PATTERN = "input_boolean.keymaster_{slot}_enabled"
KEYMASTER_DATE_START_PATTERN = "input_datetime.keymaster_{slot}_date_start_date"
KEYMASTER_DATE_END_PATTERN = "input_datetime.keymaster_{slot}_date_end_date"
