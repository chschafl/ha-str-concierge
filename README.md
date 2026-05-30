# 🏡 STR Concierge for Home Assistant

[![HACS Custom][hacs-badge]][hacs-url]
[![GitHub release][release-badge]][release-url]
[![License: MIT][license-badge]][license-url]

**Your smart home, but it actually knows when guests arrive.**

STR Concierge connects your short-term rental's booking calendar to Home Assistant. When a guest unlocks the door, your home knows it. When they check out, the lock relocks, lights go off, the thermostat goes to away mode, and your cleaner gets a notification — all automatically.

No more programming door codes by hand. No more forgetting to reset the thermostat between guests. No more wondering if the cleaner has finished.

---

## What it does

```
        Booking syncs from           Guest unlocks
        your PMS                     the door
                │                              │
                ▼                              ▼
        ┌────────────────────────────────────────────┐
        │             STR Concierge                  │
        │                                            │
        │   Knows who's coming, when,                │
        │   whether they're inside,                  │
        │   and whether the house is clean.          │
        └────────────────────────────────────────────┘
                            │
                            ▼
                  Your automations run
            (lights · climate · locks · notifications)
```

Out of the box you get:

- **A "Guest Status" sensor** — `reserved` (booked, not here yet) → `due_in` (arriving soon) → `in_house` (currently here) → `departed` (just checked out) → `vacant` (nobody home)
- **A "House State" sensor** — `ready` for the next guest, `occupied`, `dirty` (needs cleaning), `cleaning` (cleaner is on it)
- **Current guest info** — name, check-in / check-out times, door code, calculated lock-access window
- **Buttons for the cleaner** — "Mark Cleaning Started" and "Mark Ready" go right on a dashboard or HA mobile app
- **Reliable automation triggers** — the `departed` state is held for a deterministic window so auto-lock and away-mode automations fire every time

---

## Which property management systems work?

| Provider | Status |
|---|---|
| [Host Tools](https://hosttools.com) | ✅ Supported |
| [Hostfully](https://hostfully.com) | ✅ Supported |
| [Guesty](https://guesty.com) | ✅ Supported |
| Your own booking backend | ✅ via Custom Endpoint |
| Lodgify, Smoobu, OwnerRez, Hospitable, Beds24, …? | Not yet — [community help wanted](CONTRIBUTING.md) |

If your PMS isn't listed and you'd like to use STR Concierge, the integration is designed so that adding a new backend is a short, self-contained task. See [CONTRIBUTING.md](CONTRIBUTING.md) — even if you don't write the code yourself, opening an issue with details about your PMS's API is a great start.

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ menu → **Custom repositories**
2. Add the URL `https://github.com/chschafl/ha-str-concierge` and select type **Integration**
3. Find **STR Concierge** in the HACS list and click **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration → STR Concierge**

### Manual

```bash
# From your HA config directory
git clone https://github.com/chschafl/ha-str-concierge.git /tmp/strc
cp -r /tmp/strc/custom_components/str_concierge config/custom_components/
# Then restart Home Assistant and add the integration from the UI.
```

---

## Setup walkthrough

The setup wizard takes about a minute.

### 1 · Choose your provider
Pick which PMS you use. If you run your own backend, choose **Custom Endpoint**.

### 2 · Enter credentials

| Provider | What to paste in |
|---|---|
| Host Tools | Your Host Tools API token (from **Settings → API** in Host Tools) |
| Hostfully | Your Hostfully API key |
| Guesty | `client_id:client_secret` joined with a colon (from the Guesty developer portal) |
| Custom Endpoint | Your token **and** your server's base URL |

The integration validates your credentials live — if it can't connect, you'll get a clear error before you continue.

### 3 · Pick the property
Choose which property this integration entry should track. (One property per entry — if you have multiple listings, add another integration entry per listing.) Set how often to check for booking updates (default: 5 minutes).

### 4 · Configure the door-lock trigger

Open the integration's **Configure** panel any time after setup:

| Option | What it does |
|---|---|
| **Arrival window** (default: 4 hours) | How long before check-in time the guest status flips from `reserved` to `due_in` |
| **Lock minutes before check-in** (default: 0) | How early the door code becomes valid |
| **Lock minutes after check-out** (default: 60) | Courtesy window after checkout before the guest goes `departed` |
| **Lock trigger source** | How STR Concierge detects "guest just entered". Pick **Lock entity** if you want to listen to any HA lock or door sensor, or **Keymaster slot event** if you're using Keymaster |
| **Lock entity ID** | When trigger source is **Lock entity** — e.g. `lock.front_door` or `binary_sensor.front_door_unlocked` |
| **Unlock states** | Which states of that entity count as "unlocked" (default: `unlocked`). Comma-separated |
| **Keymaster slot name** | When trigger source is **Keymaster slot event** — the slot name (e.g. `str_guest`) |

---

## What you get in Home Assistant

The integration creates a single **device** per property, with these entities grouped under it:

### Sensors

| Entity | What you see |
|---|---|
| **Guest** | `Alice Smith` (the current booking's guest name) |
| **Guest Status** | `reserved` / `due_in` / `in_house` / `departed` / `vacant` |
| **House State** | `ready` / `occupied` / `dirty` / `cleaning` |
| **Door Code** | `1234` (hidden from dashboards by default — keep PINs private) |
| **Check-in** | When the booking starts |
| **Check-out** | When the booking ends |
| **Lock Access Start** | check-in − "lock minutes before" |
| **Lock Access End** | check-out + "lock minutes after" |

### Binary sensor

| Entity | `on` when |
|---|---|
| **Guest Present** | Guest Status is `in_house` |

### Buttons

| Entity | What it does |
|---|---|
| **Mark Guest Arrived** | Manual override if the lock event was missed |
| **Mark Guest Departed** | Force the current guest to `departed` (auto-locks and notifies cleaner, same as a natural checkout) |
| **Mark Cleaning Started** | House `dirty` → `cleaning` |
| **Mark Ready** | House `cleaning` → `ready` |

The cleaning buttons are designed to be put right on a dashboard or the HA mobile app — your cleaner can tap them on arrival and departure.

---

## Automation recipes

### Auto-lock and switch to away mode when a guest leaves

The `departed` state is held for a deterministic window so this triggers every time:

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

### Tell the cleaner the house is ready to clean

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
        message: "Guest just checked out — house is yours."
```

### Welcome the guest when they unlock the door

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

### Pre-heat / pre-cool a few hours before arrival

```yaml
automation:
  alias: "STR – Get the house ready"
  trigger:
    - platform: state
      entity_id: sensor.beach_house_guest_status
      to: "due_in"
  action:
    - service: climate.set_preset_mode
      target:
        entity_id: climate.beach_house_thermostat
      data:
        preset_mode: comfort
```

---

## Door code automation with Keymaster

[Keymaster](https://github.com/FutureTense/keymaster) is a popular HA integration for managing Z-Wave and Zigbee door-lock PIN codes. STR Concierge integrates with it in two complementary ways:

1. **As a lock trigger source** — listen for the "PIN entered" event so the integration knows the guest just walked in
2. **As a sync target** — automatically push the current booking's PIN and validity window into a Keymaster code slot

### Step-by-step: hook up Keymaster end-to-end

This recipe writes the booking's door code into a Keymaster slot the moment a new guest becomes the "current" booking, and removes it after they leave.

**Step 1 — In Keymaster, create a slot.**

In your Keymaster device's configuration, create a code slot dedicated to STR Concierge — for example, name it `str_guest`. This creates the helper entities Keymaster uses to manage that slot:

- `input_text.keymaster_str_guest_pin`
- `input_boolean.keymaster_str_guest_enabled`
- `input_datetime.keymaster_str_guest_date_start_date`
- `input_datetime.keymaster_str_guest_date_end_date`

**Step 2 — Tell STR Concierge to listen for Keymaster events.**

In **Settings → Devices & Services → STR Concierge → Configure**:

- Set **Lock trigger source** to `Keymaster slot event`
- Set **Keymaster slot name** to `str_guest` (or whatever name you used in step 1)

Now when the guest enters their PIN on the lock, Keymaster fires an event, STR Concierge sees it, and the guest's status flips to `in_house`.

**Step 3 — Automatically push the door code into the slot when a new guest checks in.**

Add this automation:

```yaml
automation:
  alias: "STR – Sync door code to Keymaster"
  trigger:
    - platform: event
      event_type: str_concierge_guest_changed
  action:
    - service: str_concierge.sync_keymaster
      data:
        entry_id: "{{ trigger.event.data.entry_id }}"
        slot: "str_guest"
```

That's it. From now on, every time a new booking becomes the current one (whether through PMS rotation or because the previous guest just departed), STR Concierge will automatically:

- Write the new guest's PIN to `input_text.keymaster_str_guest_pin`
- Enable the slot via `input_boolean.keymaster_str_guest_enabled`
- Set the validity window (`input_datetime.keymaster_str_guest_date_start_date` and `_end_date`) to match the calculated lock-access window

You don't have to touch the lock again. The next guest's code shows up by itself.

**Step 4 (optional) — Disable the slot when the house is vacant.**

```yaml
automation:
  alias: "STR – Disable Keymaster slot when vacant"
  trigger:
    - platform: state
      entity_id: sensor.beach_house_guest_status
      to: "vacant"
  action:
    - service: input_boolean.turn_off
      target:
        entity_id: input_boolean.keymaster_str_guest_enabled
```

### Manual sync

You can also call the sync service yourself from a script or developer tools:

```yaml
service: str_concierge.sync_keymaster
data:
  entry_id: "your_config_entry_id"   # find this in Settings → Devices & Services
  slot: "str_guest"
```

---

## Events fired by the integration

You can build automations on top of these.

| Event | When it fires |
|---|---|
| `str_concierge_guest_changed` | The "current" booking rotated to a different guest |
| `str_concierge_guest_status_changed` | Guest status transitioned (`due_in` → `in_house`, etc.) |
| `str_concierge_house_state_changed` | House state transitioned |

Each event includes `entry_id`, `property_id`, and the previous + new values.

---

## Contributing & developer docs

- **Adding a PMS provider, dev workflow, testing**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Per-provider implementation notes** (auth, endpoints, quirks): [docs/providers/](docs/providers/)

If your PMS isn't supported yet, the integration is structured to make adding new providers a clean, self-contained task — and we're keen to help. Open an issue or read CONTRIBUTING.md to get started.

---

## Roadmap

- [ ] Webhook receivers — replace polling for providers that push updates
- [ ] Lovelace card — pre-built dashboard for guest + house status at a glance
- [ ] Cleaner geofence auto-trigger (`cleaning` → `ready` when cleaner leaves the property)

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
