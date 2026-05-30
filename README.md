# STR HA — Short-Term Rental Manager for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that syncs guest data from your property management system (PMS) and exposes it as entities you can use in automations, dashboards, and lock integrations.

---

## Features

- **Current & next guest** — name, phone, email, check-in/out times, door code
- **Guest Present** binary sensor — triggers automations on guest change
- **Lock window sensors** — configurable offsets before check-in and after check-out, ready for Keymaster
- **Action buttons** — Mark Guest Arrived / Mark Guest Checked Out (calls back into your PMS)
- **Keymaster integration** — one service call to sync door code + access window into a Keymaster slot
- **Multiple properties** — one config entry per PMS account, unlimited properties per entry

---

## Supported Backends

| Provider | Auth | mark_arrived | mark_checked_out |
|---|---|---|---|
| **Host Tools** | Bearer token | ✅ | ✅ |
| **Custom Endpoint** | Bearer token | ✅ | ✅ |
| **Hostfully** | API key header | ✅ | ✅ |
| **Guesty** | OAuth2 client credentials | ✅ | ✅ |

### Adding a new provider

1. Create `custom_components/str_ha/providers/my_provider.py`
2. Subclass `STRProvider` from `providers/base.py`
3. Implement `get_properties()` and `get_property_data()`
4. Register it in `providers/__init__.py` and `const.py`

---

## Installation

### HACS (recommended)

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/chschafl/str-ha` as an **Integration**
3. Install **Short-Term Rental Manager**
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → Short-Term Rental Manager

### Manual

Copy `custom_components/str_ha/` into your HA `config/custom_components/` directory and restart.

---

## Configuration

The integration is configured through the UI (Settings → Devices & Services).

### Step 1 — Choose provider

Select Host Tools, Custom Endpoint, Hostfully, or Guesty.

### Step 2 — Credentials

| Provider | API Key field |
|---|---|
| Host Tools | Your Host Tools API access token (Bearer) |
| Custom Endpoint | Your token + the base URL of your API |
| Hostfully | Your Hostfully API key (`X-HOSTFULLY-APIKEY`) |
| Guesty | `client_id:client_secret` (colon-separated) |

### Step 3 — Select properties & polling interval

Pick which listings to sync. Default polling is every 5 minutes.

### Options (editable after setup)

- **Lock enabled N minutes BEFORE check-in** — e.g. `60` to allow lock 1 h early
- **Lock remains active N minutes AFTER check-out** — e.g. `60` to keep code valid 1 h after checkout
- **Keymaster slot name** — if set, the `sync_keymaster` service is called automatically on guest change

---

## Entities

For each property the following entities are created:

### Sensors
| Entity | Description |
|---|---|
| `sensor.{property}_current_guest_name` | Current guest's full name |
| `sensor.{property}_current_guest_phone` | Phone number |
| `sensor.{property}_current_guest_email` | Email address |
| `sensor.{property}_current_guest_door_code` | Door / access code |
| `sensor.{property}_current_guest_status` | `confirmed` / `arrived` / `checked_out` |
| `sensor.{property}_current_guest_check_in` | Check-in datetime |
| `sensor.{property}_current_guest_check_out` | Check-out datetime |
| `sensor.{property}_next_guest_name` | Next guest's name |
| `sensor.{property}_next_guest_*` | Same fields as current |
| `sensor.{property}_lock_access_start` | check-in − offset |
| `sensor.{property}_lock_access_end` | check-out + offset |

### Binary Sensors
| Entity | Description |
|---|---|
| `binary_sensor.{property}_guest_present` | `on` when a guest is in-stay |

### Buttons
| Entity | Action |
|---|---|
| `button.{property}_mark_guest_arrived` | Calls mark_arrived in your PMS |
| `button.{property}_mark_guest_checked_out` | Calls mark_checked_out in your PMS |

---

## Events

| Event | Fired when |
|---|---|
| `str_ha_guest_changed` | The current guest booking changes |
| `str_ha_next_guest_changed` | The next guest booking changes |

Event data includes `property_id`, `property_name`, and guest name(s).

Use these in automations:

```yaml
automation:
  trigger:
    - platform: event
      event_type: str_ha_guest_changed
  action:
    - service: notify.mobile_app_my_phone
      data:
        message: "New guest: {{ trigger.event.data.current_guest }}"
```

---

## Keymaster Integration

[Keymaster](https://github.com/FutureTense/keymaster) manages Z-Wave/ZigBee lock code slots. STR HA can write the guest door code and access window directly into a Keymaster slot.

### Automatic (via options)

Set the **Keymaster slot name** in the integration options. The `sync_keymaster` service will be called automatically whenever the current guest changes.

### Manual service call

```yaml
service: str_ha.sync_keymaster
data:
  entry_id: "your_config_entry_id"
  property_id: "your_property_id"
  slot: "str_guest"
```

This sets:
- `input_text.keymaster_str_guest_pin` → door code
- `input_boolean.keymaster_str_guest_enabled` → on
- `input_datetime.keymaster_str_guest_date_start_date` → lock_access_start
- `input_datetime.keymaster_str_guest_date_end_date` → lock_access_end

---

## Host Tools API Notes

The integration targets `https://app.hosttools.com/api/v1`. Official docs:
https://help.hosttools.com/en/articles/10118922-host-tools-api-docs

If Host Tools uses different field names in their API response, adjust
`_RESERVATION_FIELD_MAP` in `providers/host_tools.py` — each key maps
to a prioritised list of candidate JSON field names.

---

## Custom Endpoint API Contract

Your custom backend must expose:

```
GET  /properties                      → [{id, name}]
GET  /reservations?propertyId={id}    → [{id, guestName, guestEmail,
                                          guestPhone, checkIn, checkOut,
                                          doorCode, status}]
POST /reservations/{id}/arrive        → {ok: true}
POST /reservations/{id}/checkout      → {ok: true}
```

Authentication: `Authorization: Bearer {token}` header.

---

## Security

- API keys are stored in Home Assistant's config entry storage (encrypted at rest if HA encryption is enabled).
- No keys are logged at INFO level; debug logs only show errors, never secrets.
- Token-based auth is enforced on all provider requests; OAuth2 is supported natively by Guesty.
- The integration makes no outbound connections except to the configured PMS endpoint.

---

## Roadmap

- [ ] Webhook receiver (replace polling with push for supported providers)
- [ ] OAuth2 config flow for providers that support it
- [ ] Per-property Keymaster slot configuration
- [ ] Multiple properties per dashboard card

---

## License

MIT
