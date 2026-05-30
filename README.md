# 🏡 STR Concierge for Home Assistant

[![HACS Custom][hacs-badge]][hacs-url]
[![GitHub release][release-badge]][release-url]
[![License: MIT][license-badge]][license-url]

**Bring your short-term rental guests into Home Assistant.**

STR Concierge syncs real-time booking data from your property management system — current guest, next guest, door codes, check-in/out times — and turns it all into automatable HA entities. When a new guest checks in, your home reacts automatically.

---

## What it does

```
Your PMS ──► STR Concierge ──► Home Assistant entities
                                      │
                    ┌─────────────────┼────────────────────┐
                    ▼                 ▼                     ▼
              Automations        Dashboard             Keymaster
          “Welcome, Alice!”   Guest info card     Door code synced
          Lights scene on     Check-in time       Access window set
          Thermostat preset   Door code shown     Lock enabled
```

No more manually programming door codes, no more forgetting to change the thermostat between guests. STR Concierge is the glue between your bookings and your smart home.

---

## Features at a glance

| Feature | Details |
|---|---|
| **Current & next guest** | Name, phone, email, check-in/out time, door code |
| **Guest Present sensor** | Binary sensor — perfect for occupancy automations |
| **Lock window sensors** | Configurable offsets: lock opens N min before check-in, closes N min after check-out |
| **Action buttons** | Mark Arrived / Mark Checked Out — calls back into your PMS |
| **Keymaster integration** | One service call writes door code + access window to your Z-Wave/ZigBee lock |
| **Multiple properties** | Track as many listings as you want |
| **Guest change events** | Fire HA automations the moment a new guest becomes current |
| **Polling + planned webhooks** | Default 5-min polling; webhook push coming soon |

---

## Supported backends

| Provider | Auth type | Arrived | Checked out |
|---|---|---|---|
| [Host Tools](https://hosttools.com) | Bearer token | ✅ | ✅ |
| Custom / Homebrew API | Bearer token | ✅ | ✅ |
| [Hostfully](https://hostfully.com) | API key | ✅ | ✅ |
| [Guesty](https://guesty.com) | OAuth2 client credentials | ✅ | ✅ |

**Adding a new provider** takes about 50 lines of Python — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ menu → **Custom repositories**
2. Add URL: `https://github.com/chschafl/str-ha` — type **Integration**
3. Find **STR Concierge** and click **Download**
4. Restart Home Assistant
5. **Settings → Devices & Services → Add Integration → STR Concierge**

### Manual

```bash
# From your HA config directory:
git clone https://github.com/chschafl/str-ha.git /tmp/str-ha
cp -r /tmp/str-ha/custom_components/str_ha config/custom_components/
# Restart Home Assistant
```

---

## Setup walkthrough

### Step 1 — Choose your provider

Pick which property management system you use. If you run your own booking backend, choose **Custom Endpoint**.

### Step 2 — Enter credentials

| Provider | What to enter |
|---|---|
| Host Tools | Your Host Tools API access token |
| Custom Endpoint | Your API token **and** your server’s base URL |
| Hostfully | Your Hostfully API key |
| Guesty | `client_id:client_secret` (copy both from the Guesty developer portal, join with a colon) |

The integration validates your credentials live — if it can’t connect, you’ll see a clear error message.

### Step 3 — Select properties

The integration fetches your listing/property list and lets you pick which ones to sync. You can add more later by setting up another integration entry. Set the polling interval (default: 5 minutes — go lower if your PMS rate limits allow it).

### Options (always editable)

After setup, click **Configure** on the integration card to adjust:

- **Lock enabled N minutes before check-in** — e.g. `60` means the door code works from 1 hour before the official check-in time
- **Lock remains active N minutes after check-out** — e.g. `60` keeps the code valid for 1 hour of grace time after checkout
- **Keymaster slot name** — set this once and door codes sync automatically on every guest change

---

## Entities reference

For each property you’ll get a **device** grouping all its entities:

### 📊 Sensors

| Entity | Example value | Notes |
|---|---|---|
| `Current Guest Name` | `Alice Smith` | |
| `Current Guest Phone` | `+1-555-0100` | |
| `Current Guest Email` | `alice@example.com` | |
| `Current Guest Door Code` | `1234` | Keep this off your public dashboard! |
| `Current Guest Status` | `confirmed` / `arrived` / `checked_out` | |
| `Current Guest Check-in` | `2025-06-01T15:00:00+00:00` | Timestamp sensor |
| `Current Guest Check-out` | `2025-06-07T11:00:00+00:00` | Timestamp sensor |
| `Next Guest Name` | `Bob Jones` | |
| `Next Guest Phone` | `+1-555-0200` | |
| `Next Guest Email` | `bob@example.com` | |
| `Next Guest Door Code` | `5678` | |
| `Next Guest Check-in` | `2025-06-08T15:00:00+00:00` | |
| `Next Guest Check-out` | `2025-06-10T11:00:00+00:00` | |
| `Lock Access Start` | `2025-06-01T14:00:00+00:00` | check-in − offset |
| `Lock Access End` | `2025-06-07T12:00:00+00:00` | check-out + offset |

### 🔵 Binary Sensors

| Entity | `on` when… |
|---|---|
| `Guest Present` | A current booking exists and the guest hasn’t checked out |

### 🔘 Buttons

| Entity | What it does |
|---|---|
| `Mark Guest Arrived` | Calls your PMS to mark the booking as checked in |
| `Mark Guest Checked Out` | Calls your PMS to mark the booking as checked out |

---

## Automations

### Welcome new guests

```yaml
automation:
  alias: "STR – Welcome message on guest change"
  trigger:
    - platform: event
      event_type: str_ha_guest_changed
  condition:
    - condition: template
      value_template: "{{ trigger.event.data.current_guest is not none }}"
  action:
    - service: notify.mobile_app_my_phone
      data:
        title: "New guest checked in 🏡"
        message: >
          {{ trigger.event.data.current_guest }} is now at
          {{ trigger.event.data.property_name }}.
```

### Set thermostat for arriving guest

```yaml
automation:
  alias: "STR – Pre-heat/cool before check-in"
  trigger:
    - platform: template
      # Triggers 2 hours before lock_access_start
      value_template: >
        {{ (as_timestamp(states('sensor.beach_house_lock_access_start'))
            - as_timestamp(now())) | int < 7200 }}
  action:
    - service: climate.set_temperature
      target:
        entity_id: climate.beach_house_thermostat
      data:
        temperature: 72
```

### Turn lights on when guest arrives

```yaml
automation:
  alias: "STR – Lights on when guest present"
  trigger:
    - platform: state
      entity_id: binary_sensor.beach_house_guest_present
      to: "on"
  action:
    - service: scene.turn_on
      target:
        entity_id: scene.welcome_lighting
```

### Lock down after checkout

```yaml
automation:
  alias: "STR – Reset home after checkout"
  trigger:
    - platform: template
      value_template: >
        {{ now() > states('sensor.beach_house_lock_access_end') | as_datetime }}
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

---

## Keymaster integration

[Keymaster](https://github.com/FutureTense/keymaster) manages Z-Wave and ZigBee lock code slots. STR Concierge can write the door code and access window into a Keymaster slot automatically.

### Setup (one-time)

1. In Keymaster, create a code slot named e.g. `str_guest`
2. In STR Concierge options, set **Keymaster slot name** → `str_guest`

That’s it. From now on, every time the current guest changes, STR Concierge calls the `str_ha.sync_keymaster` service automatically, which sets:

- `input_text.keymaster_str_guest_pin` → guest’s door code
- `input_boolean.keymaster_str_guest_enabled` → `on`
- `input_datetime.keymaster_str_guest_date_start_date` → Lock Access Start
- `input_datetime.keymaster_str_guest_date_end_date` → Lock Access End

### Manual sync

You can also call it yourself (useful in automations or scripts):

```yaml
service: str_ha.sync_keymaster
data:
  entry_id: "your_config_entry_id"   # find this in Settings → Devices & Services
  property_id: "your_property_id"
  slot: "str_guest"
```

---

## Host Tools notes

STR Concierge targets `https://app.hosttools.com/api/v1` with Bearer auth. Get your API token from the Host Tools dashboard under **Settings → API**.

The integration uses a flexible field-name map (`_RESERVATION_FIELD_MAP` in `providers/host_tools.py`) that tries multiple candidate JSON keys for each field. If Host Tools ever changes their API response format, you can add the new key name to the list without changing any other code.

---

## Custom backend API contract

If you run your own booking system, expose these endpoints:

```
GET  /properties
     → [{"id": "string", "name": "string"}]

GET  /reservations?propertyId={id}
     → [
         {
           "id": "string",
           "guestName": "string",
           "guestEmail": "string",
           "guestPhone": "string",
           "checkIn": "2025-06-01T15:00:00Z",
           "checkOut": "2025-06-07T11:00:00Z",
           "doorCode": "string",
           "status": "confirmed|arrived|checked_out"
         }
       ]

POST /reservations/{id}/arrive    → {"ok": true}
POST /reservations/{id}/checkout  → {"ok": true}
```

Authentication: `Authorization: Bearer {token}` on every request.

Field names are flexible — the provider tries snake_case, camelCase and several aliases for each field. See `providers/custom_endpoint.py` for the full list.

---

## Security

- **Credentials stored safely** — API keys live in HA’s config entry store. If you have HA’s storage encryption enabled, they’re encrypted at rest.
- **No secrets in logs** — the integration never logs API keys or door codes at INFO level.
- **Network isolation** — the only outbound calls are to your configured PMS endpoint. No telemetry.
- **Token auth today, OAuth2 ready** — Guesty already uses OAuth2 client credentials with automatic token refresh. The config flow is structured to add authorization-code OAuth2 flows for other providers without breaking existing setups.

---

## Development

### Quick deploy to local HA

The fastest workflow is a symlink — edits to source files are **immediately** reflected in HA without any copy step:

```bash
# One-time setup:
make symlink   # creates ~/.homeassistant/custom_components/str_ha → ./custom_components/str_ha

# Then restart HA once:
make restart   # requires 'ha' CLI (Home Assistant OS / Supervised)

# After that, edit → reload integration in HA UI. No copy needed.
```

For a remote HA instance, edit `.env`:
```bash
# .env
HASS_SSH=user@homeassistant.local
HASS_CONFIG=/config
```

Then:
```bash
make deploy-ssh        # rsync to remote
make deploy-ssh-reload # rsync + restart
make deploy-watch      # auto-rsync on every file save (macOS: fswatch, Linux: inotifywait)
```

### Run the tests

```bash
pip install -r requirements_test.txt
make test
```

Tests use `aioresponses` to mock HTTP calls — no live PMS credentials needed:

```bash
pytest tests/ -v
# tests/providers/test_host_tools.py::TestGetProperties::test_returns_property_list PASSED
# tests/providers/test_host_tools.py::TestFieldMapping::test_alternate_field_names PASSED
# tests/test_coordinator.py::TestEventFiring::test_guest_changed_event_fires PASSED
# ...
```

### Dev container (VS Code)

Open the repo in VS Code and accept the “Reopen in Container” prompt. The container installs all test dependencies automatically. Run tests with the built-in test runner or `make test` in the integrated terminal.

### Adding a new PMS provider

1. Create `custom_components/str_ha/providers/my_pms.py`
2. Subclass `STRProvider` from `providers/base.py`
3. Implement `get_properties()` and `get_property_data()` (and optionally `mark_arrived()` / `mark_checked_out()`)
4. Add a constant to `const.py` and register it in `providers/__init__.py`
5. Add a label in `config_flow.py`’s `_PROVIDER_LABELS`

That’s all — the config flow, coordinator, entities, and services all pick it up automatically.

---

## Roadmap

- [ ] **Webhook receiver** — replace polling with real-time push for supported providers
- [ ] **OAuth2 config flow** — full authorization-code flow for providers that support it
- [ ] **Per-property Keymaster slot** — different slot per listing
- [ ] **Lovelace card** — pre-built guest info card for dashboards
- [ ] **Cleaning schedule sensor** — expose turnover window between checkout and next check-in

---

## Contributing

Pull requests are welcome! Please open an issue first to discuss larger changes.

---

## License

MIT © [chschafl](https://github.com/chschafl)

<!-- Badges -->
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/chschafl/str-ha
[release-url]: https://github.com/chschafl/str-ha/releases
[license-badge]: https://img.shields.io/badge/License-MIT-yellow.svg
[license-url]: LICENSE
