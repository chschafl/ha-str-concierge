# 🏡 STR Concierge for Home Assistant

[![HACS Custom][hacs-badge]][hacs-url]
[![GitHub release][release-badge]][release-url]
[![License: MIT][license-badge]][license-url]

**A door-lock-aware guest lifecycle for your short-term rental.**

STR Concierge syncs the current booking from your property management system, latches a real-time "in-house" state when the guest unlocks the door, and surfaces a separate housekeeping state (`ready` / `occupied` / `dirty` / `cleaning`) so your home — and your cleaner — always know what's going on.

---

## How it works

```
        PMS booking calendar           Lock unlock event
                │                              │
                ▼                              ▼
        ┌────────────────────────────────────────────┐
        │             STR Concierge                  │
        │                                            │
        │   Guest status:  reserved → due_in →       │
        │                   in_house → departed →    │
        │                   vacant                   │
        │                                            │
        │   House state:   ready  ↔  occupied        │
        │                       ↓                    │
        │                    dirty → cleaning → ready│
        └────────────────────────────────────────────┘
                            │
                            ▼
                  HA sensors + events
                (automations, dashboards)
```

Guest status transitions:

| State | Trigger |
|---|---|
| `reserved` | Booking is in the future, outside the arrival window |
| `due_in` | Now ≥ check-in − arrival window (configurable, default 4 hours) |
| `in_house` | Lock unlock event observed inside the lock-access window |
| `departed` | Past check-out + lock courtesy window — held for 10s so automations can react |
| `vacant` | No current booking, or current guest has fully departed |

House state transitions:

| From → To | Trigger |
|---|---|
| `ready` → `occupied` | Guest enters `in_house` |
| `occupied` → `dirty` | Guest enters `departed` (automatic) |
| `dirty` → `cleaning` | "Mark Cleaning Started" button |
| `cleaning` → `ready` | "Mark Ready" button |

---

## Features

| Feature | Details |
|---|---|
| **Current guest only** | Single source of truth: name, door code, check-in/out, lifecycle status |
| **Door-lock-driven arrival** | Listens to a configured lock entity or Keymaster slot — latches `in_house` |
| **Predictable `departed` window** | 10-second observable transition so automations (auto-lock, away mode) fire reliably before rotation |
| **Housekeeping workflow** | `dirty` / `cleaning` / `ready` with cleaner-facing buttons |
| **Persistent state** | Uses HA's storage helper so the lock latch survives restarts |
| **Keymaster integration** | Optional: syncs door code + access window to a Keymaster code slot |
| **Single property scope** | One integration entry = one property. Add another entry for a second listing |

---

## Supported backends

| Provider | Auth type |
|---|---|
| [Host Tools](https://hosttools.com) | Bearer token |
| Custom / Homebrew API | Bearer token |
| [Hostfully](https://hostfully.com) | API key |
| [Guesty](https://guesty.com) | OAuth2 client credentials |

---

## Setup

### 1. Choose your provider
Pick which PMS you use. If you run your own booking backend, choose **Custom Endpoint**.

### 2. Enter credentials
The integration validates your credentials live before continuing.

### 3. Pick the property
One config entry tracks one property. Set the polling interval (default: 5 minutes).

### 4. Configure (after setup)

| Option | Default | Description |
|---|---|---|
| Arrival window (hours) | 4 | When the guest transitions from `reserved` → `due_in` |
| Lock minutes before check-in | 0 | How early the lock access window opens |
| Lock minutes after check-out | 60 | Courtesy window before guest goes `departed` |
| Lock trigger source | Entity | `entity` (any HA lock/sensor) or `keymaster` (slot events) |
| Lock entity ID | — | e.g. `lock.front_door` (when trigger source is `entity`) |
| Unlock states | `unlocked` | Comma-separated states that count as "guest entered" |
| Keymaster slot | — | Slot name when trigger source is `keymaster` |

---

## Entities

A single device groups all entities for the property.

### Sensors

| Entity | Example |
|---|---|
| `Guest` | `Alice Smith` |
| `Door Code` | `1234` (hidden from dashboards by default) |
| `Guest Status` | `reserved` / `due_in` / `in_house` / `departed` / `vacant` |
| `House State` | `ready` / `occupied` / `dirty` / `cleaning` |
| `Check-in` | `2025-06-01T15:00:00+00:00` |
| `Check-out` | `2025-06-07T11:00:00+00:00` |
| `Lock Access Start` | check-in − offset |
| `Lock Access End` | check-out + offset |

### Binary sensors

| Entity | `on` when |
|---|---|
| `Guest Present` | Guest Status is `in_house` |

### Buttons

| Entity | What it does |
|---|---|
| `Mark Guest Arrived` | Manual override when the lock event was missed |
| `Mark Guest Departed` | Force `departed`, hold 10s, then rotate |
| `Mark Cleaning Started` | House `dirty` → `cleaning` |
| `Mark Ready` | House `cleaning` → `ready` |

---

## Events

| Event | When it fires |
|---|---|
| `str_concierge_guest_changed` | Current booking rotated (different `booking_id`) |
| `str_concierge_guest_status_changed` | Guest status transitioned |
| `str_concierge_house_state_changed` | House state transitioned |

All events include `entry_id`, `property_id`, and the previous + new values.

---

## Automations

### Auto-lock and away mode on departure
The `departed` state is held for 10 seconds so this triggers reliably:

```yaml
automation:
  alias: "STR – Lock down on guest departure"
  trigger:
    - platform: state
      entity_id: sensor.beach_house_guest_status
      to: "departed"
  action:
    - service: lock.lock
      target:
        entity_id: lock.front_door
    - service: climate.set_preset_mode
      target:
        entity_id: climate.beach_house_thermostat
      data:
        preset_mode: away
```

### Notify cleaner when the house needs cleaning
```yaml
automation:
  alias: "STR – Cleaner notification"
  trigger:
    - platform: state
      entity_id: sensor.beach_house_house_state
      to: "dirty"
  action:
    - service: notify.cleaner_phone
      data:
        title: "Beach House ready for cleaning"
        message: "Guest just checked out."
```

### Welcome scene when guest unlocks the door
```yaml
automation:
  alias: "STR – Welcome lights"
  trigger:
    - platform: state
      entity_id: binary_sensor.beach_house_guest_present
      to: "on"
  action:
    - service: scene.turn_on
      target:
        entity_id: scene.welcome_lighting
```

---

## State storage

The integration uses HA's `helpers.storage.Store` to persist:

- `current_booking_id` — which PMS booking we're tracking
- `entered_at` — when the lock latched (`in_house` flag)
- `dismissed_booking_id` — set after a guest has fully departed, so the PMS calendar can catch up without re-deriving `due_in`
- `house_state` + `house_state_changed_at`

State survives HA restarts. The 10-second departed-dwell timer is in-memory only; on the unlucky restart mid-dwell, the next poll completes the rotation.

---

## Keymaster integration

[Keymaster](https://github.com/FutureTense/keymaster) can be either the **lock trigger source** (the integration listens for Keymaster's PIN-entered event for a specific slot) or just a **sync target** for door codes.

To sync the current guest's PIN and lock-access window into a Keymaster slot:

```yaml
service: str_concierge.sync_keymaster
data:
  entry_id: "your_config_entry_id"
  slot: "str_guest"
```

This sets:
- `input_text.keymaster_str_guest_pin` → guest's door code
- `input_boolean.keymaster_str_guest_enabled` → on
- `input_datetime.keymaster_str_guest_date_start_date` → Lock Access Start
- `input_datetime.keymaster_str_guest_date_end_date` → Lock Access End

---

## Custom backend API contract

```
GET  /properties
     → [{"id": "string", "name": "string"}]

GET  /reservations?propertyId={id}
     → [
         {
           "id": "string",
           "guestName": "string",
           "checkIn": "2025-06-01T15:00:00Z",
           "checkOut": "2025-06-07T11:00:00Z",
           "doorCode": "string"
         }
       ]

POST /reservations/{id}/arrive    → {"ok": true}
POST /reservations/{id}/checkout  → {"ok": true}
```

Authentication: `Authorization: Bearer {token}`.

Field names are flexible — see `providers/custom_endpoint.py` for the alias list.

---

## Development

### Quick deploy to local HA
```bash
make symlink   # one-time: link custom_components/str_concierge → ~/.homeassistant/custom_components/str_concierge
make restart   # ha CLI restart
```

### Run the tests
```bash
pip install -r requirements_test.txt
make test
```

Tests mock the PMS HTTP layer with `aioresponses` and the lock/store/coordinator with `pytest-homeassistant-custom-component`. No live credentials needed.

---

## Roadmap

- [ ] Webhook receiver (replace polling for supported providers)
- [ ] Per-entity translation strings for guest/house status values
- [ ] Lovelace card with current guest + house state at a glance
- [ ] Cleaner geofence auto-trigger (`cleaning` → `ready`)

---

## License

MIT © [chschafl](https://github.com/chschafl)

<!-- Badges -->
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/chschafl/ha-str-concierge
[release-url]: https://github.com/chschafl/ha-str-concierge/releases
[license-badge]: https://img.shields.io/badge/License-MIT-yellow.svg
[license-url]: LICENSE
