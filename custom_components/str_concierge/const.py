"""Constants for the STR Concierge integration."""

DOMAIN = "str_concierge"
PLATFORMS = ["sensor", "binary_sensor", "button"]

# ── Config entry keys ─────────────────────────────────────────────────
CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_PROPERTY_ID = "property_id"
CONF_POLL_INTERVAL = "poll_interval"

# Per-provider extras. Host Tools has no listings-list endpoint, so the user
# supplies their listing ID during setup; we store it in config entry data.
CONF_HOST_TOOLS_LISTING_ID = "host_tools_listing_id"

# ── Options keys (editable after setup) ───────────────────────────────
CONF_ARRIVAL_WINDOW_HOURS = "arrival_window_hours"
CONF_LOCK_MINUTES_BEFORE_CHECKIN = "lock_minutes_before_checkin"
CONF_LOCK_MINUTES_AFTER_CHECKOUT = "lock_minutes_after_checkout"
CONF_LOCK_TRIGGER_SOURCE = "lock_trigger_source"
CONF_LOCK_ENTITY_ID = "lock_entity_id"
CONF_LOCK_UNLOCK_STATES = "lock_unlock_states"
CONF_KEYMASTER_SLOT = "keymaster_slot"

LOCK_TRIGGER_KEYMASTER = "keymaster"
LOCK_TRIGGER_ENTITY = "entity"

# ── Provider identifiers ──────────────────────────────────────────────
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

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_POLL_INTERVAL = 300  # 5 minutes
DEFAULT_ARRIVAL_WINDOW_HOURS = 4
DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN = 0
DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT = 60
DEFAULT_LOCK_UNLOCK_STATES = ["unlocked"]

# How long the `departed` state is observable before the coordinator rotates
# to the next guest. Gives HA automations a deterministic window to react.
DEPARTED_DWELL_SECONDS = 10

# ── Storage ───────────────────────────────────────────────────────────
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_state"

# ── HA events ─────────────────────────────────────────────────────────
EVENT_GUEST_CHANGED = f"{DOMAIN}_guest_changed"
EVENT_GUEST_STATUS_CHANGED = f"{DOMAIN}_guest_status_changed"
EVENT_HOUSE_STATE_CHANGED = f"{DOMAIN}_house_state_changed"

# ── Guest lifecycle states ────────────────────────────────────────────
GUEST_RESERVED = "reserved"
GUEST_DUE_IN = "due_in"
GUEST_IN_HOUSE = "in_house"
GUEST_DEPARTED = "departed"
GUEST_VACANT = "vacant"

GUEST_STATES = [
    GUEST_RESERVED,
    GUEST_DUE_IN,
    GUEST_IN_HOUSE,
    GUEST_DEPARTED,
    GUEST_VACANT,
]

# ── House (housekeeping) states ───────────────────────────────────────
HOUSE_READY = "ready"
HOUSE_OCCUPIED = "occupied"
HOUSE_DIRTY = "dirty"
HOUSE_CLEANING = "cleaning"

HOUSE_STATES = [HOUSE_READY, HOUSE_OCCUPIED, HOUSE_DIRTY, HOUSE_CLEANING]

# ── Keymaster integration ─────────────────────────────────────────────
KEYMASTER_CODE_SLOT_PATTERN = "input_text.keymaster_{slot}_pin"
KEYMASTER_ENABLED_PATTERN = "input_boolean.keymaster_{slot}_enabled"
KEYMASTER_DATE_START_PATTERN = "input_datetime.keymaster_{slot}_date_start_date"
KEYMASTER_DATE_END_PATTERN = "input_datetime.keymaster_{slot}_date_end_date"

# Keymaster fires this event when a PIN is entered on the lock
KEYMASTER_LOCK_EVENT = "keymaster_lock_state_changed"
