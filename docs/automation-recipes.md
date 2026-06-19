# Automation recipes

This page collects ready-to-paste Home Assistant automations that build on the sensors, binary sensors, and events exposed by STR Concierge.

All recipes assume your config entry was named **Beach House** so the entities are `sensor.beach_house_guest_status`, `binary_sensor.beach_house_guest_present`, etc. Substitute your own entity IDs.

## Contents

- [The basics](#the-basics)
  - [Auto-lock and switch to away mode when a guest leaves](#auto-lock-and-switch-to-away-mode-when-a-guest-leaves)
  - [Tell the cleaner the house is ready to clean](#tell-the-cleaner-the-house-is-ready-to-clean)
  - [Welcome the guest when they unlock the door](#welcome-the-guest-when-they-unlock-the-door)
  - [Pre-heat / pre-cool a few hours before arrival](#pre-heat--pre-cool-a-few-hours-before-arrival)
- [Climate](#climate)
  - [Nest thermostat: home when a guest is here or arriving, away otherwise](#nest-thermostat-home-when-a-guest-is-here-or-arriving-away-otherwise)
  - [Reset hot tub and thermostat setpoints between guests](#reset-hot-tub-and-thermostat-setpoints-between-guests)
- [Door locks](#door-locks)
  - [Sync the door code straight to a Z-Wave lock](#sync-the-door-code-straight-to-a-z-wave-lock)
  - [Door code automation with Keymaster](#door-code-automation-with-keymaster)
  - [Driving a Z-Wave lock directly (no Keymaster)](#driving-a-z-wave-lock-directly-no-keymaster)
- [Events fired by the integration](#events-fired-by-the-integration)

---

## The basics

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

## Climate

### Nest thermostat: home when a guest is here or arriving, away otherwise

Flip the thermostat to **home** while the guest is `in_house` *or* on their way (`due_in`), and back to **away** for every other state (`reserved`, `departed`, `vacant`). A single automation handles both directions by watching the Guest Status sensor on every transition.

```yaml
alias: "STR – Nest follows guest status"
description: Set the Nest thermostat to home while a guest is present or arriving, away otherwise.
triggers:
  - trigger: state
    entity_id: sensor.beach_house_guest_status
actions:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.to_state.state in ['in_house', 'due_in'] }}"
        sequence:
          - action: climate.set_preset_mode
            target:
              entity_id: climate.beach_house_nest
            data:
              preset_mode: home
    default:
      - action: climate.set_preset_mode
        target:
          entity_id: climate.beach_house_nest
        data:
          preset_mode: away
mode: single
```

> **Note.** The Google Nest integration exposes `home` and `eco` as presets on most thermostats, while the legacy Nest integration uses `home` / `away`. If `away` errors out, try `eco` (or whatever your thermostat's "developer tools → services" shows under `climate.set_preset_mode`).

### Reset hot tub and thermostat setpoints between guests

Guests love nudging the hot tub up to 40 °C and the thermostat to "Caribbean". This recipe puts everything back to your house defaults at two natural reset points:

1. **When a new guest is arriving** (`reserved → due_in`) — the previous guest is gone and you want the home in a known state before the next one walks in.
2. **When the lock-access window closes** (`binary_sensor.beach_house_lock_active` flips `off`) — belt-and-braces in case the guest somehow stays past their window, or in case the booking rotates without going through `due_in`.

The thermostat is set with both `target_temp_low` (heat) and `target_temp_high` (cool) so it works for thermostats in `heat_cool` / `auto` mode.

```yaml
alias: "STR – Reset climate between guests"
description: Snap the hot tub and thermostat back to house defaults when a new guest is arriving or the access window closes.
triggers:
  - trigger: state
    entity_id: sensor.beach_house_guest_status
    to: "due_in"
    id: arriving
  - trigger: state
    entity_id: binary_sensor.beach_house_lock_active
    to: "off"
    id: access_ended
variables:
  hot_tub_default_c: 38
  thermostat_heat_default_c: 19
  thermostat_cool_default_c: 24
actions:
  - action: climate.set_temperature
    target:
      entity_id: climate.beach_house_hot_tub
    data:
      temperature: "{{ hot_tub_default_c }}"
  - action: climate.set_temperature
    target:
      entity_id: climate.beach_house_thermostat
    data:
      target_temp_low: "{{ thermostat_heat_default_c }}"
      target_temp_high: "{{ thermostat_cool_default_c }}"
mode: single
```

A few things to notice:

- Both triggers funnel into the same action block, so there's no copy-paste. If you want different behaviour per trigger, wrap the actions in a `choose:` keyed on `trigger.id`.
- Defaults are pulled into `variables:` at the top so you can edit them in one place.
- If your thermostat is in single-setpoint mode (`heat` only or `cool` only), use `temperature:` instead of the low/high pair.
- The hot tub `climate.set_temperature` call assumes your tub is exposed as a `climate` entity (Balboa, MySpa, etc.). If it's a `water_heater` entity, swap the service for `water_heater.set_temperature`.

---

## Door locks

### Sync the door code straight to a Z-Wave lock

The simplest possible door-code workflow: whenever the `Door Code` sensor changes, write the new value into a fixed user-code slot on one or more Z-Wave locks. No Keymaster, no separate window automation — the integration's own `Lock Active` binary sensor (or the lock-access window dates) can gate access separately if you want.

This pattern works well when you have **multiple locks** that should share the same guest code (front door + back door + garage), and you're happy to leave the slot installed across the gap between bookings — the next guest's code simply overwrites it.

```yaml
alias: "STR – Sync door code to Z-Wave locks"
description: Write the current door code into a dedicated slot on every guest-accessible lock.
triggers:
  - trigger: state
    entity_id: sensor.beach_house_door_code
conditions:
  - condition: template
    value_template: "{{ desired_code is match('^[0-9]{4,8}$') }}"
actions:
  - action: zwave_js.set_lock_usercode
    target:
      entity_id: lock.front_door
    data:
      code_slot: 3
      usercode: "{{ desired_code }}"
  - action: zwave_js.set_lock_usercode
    target:
      entity_id: lock.back_door
    data:
      code_slot: 3
      usercode: "{{ desired_code }}"
variables:
  desired_code: "{{ states('sensor.beach_house_door_code') }}"
mode: single
```

A few things to notice:

- The `is match` template condition rejects `unknown`, `unavailable`, empty strings, and any other non-numeric value — so the automation only fires when the sensor really holds a clean PIN.
- The regex `^[0-9]{4,8}$` matches the door-code lengths most Z-Wave locks accept. Tighten or loosen it to match what your lock supports.
- `mode: single` means a flurry of state updates won't queue duplicate writes. The latest value always wins.
- Slot 3 is just an example — pick a slot that's free on your lock (slot 1 is usually the owner's master code).

If you want the slot to be **cleared between guests** rather than overwritten, see [Driving a Z-Wave lock directly (no Keymaster)](#driving-a-z-wave-lock-directly-no-keymaster) below.

### Door code automation with Keymaster

[Keymaster](https://github.com/FutureTense/keymaster) is a popular HA integration for managing Z-Wave and Zigbee door-lock PIN codes. STR Concierge integrates with it in two complementary ways:

1. **As a lock trigger source** — listen for the "PIN entered" event so the integration knows the guest just walked in
2. **As a sync target** — automatically push the current booking's PIN and validity window into a Keymaster code slot

#### Step-by-step: hook up Keymaster end-to-end

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

**Step 5 (optional) — Give the cleaner their own Keymaster slot.**

Create a second Keymaster code slot dedicated to your cleaner (e.g. `str_cleaner`) and give them a personal PIN. Then in **Settings → Devices & Services → STR Concierge → Configure**, set **Keymaster slot name (cleaner arrival)** to `str_cleaner`.

From then on, when the cleaner enters their PIN and the house is `dirty`, the house state automatically flips to `cleaning` — your "house ready for cleaning" notification stops nagging you, and you have a timestamp of when work actually started. The cleaner still needs to press **Mark House Ready** when they finish (or you can wire an automation off a geofence / NFC tag).

The cleaner slot listener is independent of the **Lock trigger source** setting. You can leave that on **Disabled** and still get the cleaner auto-detect — they're separate concerns.

#### Manual sync

You can also call the sync service yourself from a script or developer tools:

```yaml
service: str_concierge.sync_keymaster
data:
  entry_id: "your_config_entry_id"   # find this in Settings → Devices & Services
  slot: "str_guest"
```

### Driving a Z-Wave lock directly (no Keymaster)

If you don't use Keymaster but your lock is exposed through the Z-Wave JS integration (e.g. a Yale, Schlage Connect, or Kwikset Z-Wave smart lock), you can write the guest's PIN straight into a user-code slot and gate it on the `Lock Active` binary sensor — `on` while the lock-access window is open, `off` otherwise.

The two services involved come from Z-Wave JS:

- `zwave_js.set_lock_usercode` — write a PIN into a numbered slot
- `zwave_js.clear_lock_usercode` — erase the PIN from that slot

This recipe uses **slot 2** as the dedicated "current STR guest" slot. Pick any slot number that's free on your lock; slot 1 is usually reserved for the owner's master code.

**Step 1 — Push the new guest's PIN into slot 2 when the booking rotates.**

```yaml
automation:
  alias: "STR – Z-Wave: write guest code on booking change"
  trigger:
    - platform: event
      event_type: str_concierge_guest_changed
  condition:
    # Only write a PIN when there's actually a guest (skip rotations to vacant)
    - condition: template
      value_template: "{{ trigger.event.data.current_guest_id is not none }}"
    - condition: template
      value_template: "{{ states('sensor.beach_house_door_code') not in ('unknown', 'unavailable', '') }}"
  action:
    - service: zwave_js.set_lock_usercode
      target:
        entity_id: lock.front_door
      data:
        code_slot: 2
        usercode: "{{ states('sensor.beach_house_door_code') }}"
```

**Step 2 — Activate the slot only inside the lock-access window.**

The `Lock Active` binary sensor flips `on` at `Lock Access Start` (check-in − `lock_minutes_before_checkin`) and `off` again at `Lock Access End` (check-out + `lock_minutes_after_checkout`). Drive the user-code in/out on those edges:

```yaml
automation:
  alias: "STR – Z-Wave: enable code at start of access window"
  trigger:
    - platform: state
      entity_id: binary_sensor.beach_house_lock_active
      to: "on"
  condition:
    - condition: template
      value_template: "{{ states('sensor.beach_house_door_code') not in ('unknown', 'unavailable', '') }}"
  action:
    - service: zwave_js.set_lock_usercode
      target:
        entity_id: lock.front_door
      data:
        code_slot: 2
        usercode: "{{ states('sensor.beach_house_door_code') }}"

automation:
  alias: "STR – Z-Wave: clear code at end of access window"
  trigger:
    - platform: state
      entity_id: binary_sensor.beach_house_lock_active
      to: "off"
  action:
    - service: zwave_js.clear_lock_usercode
      target:
        entity_id: lock.front_door
      data:
        code_slot: 2
    - service: lock.lock
      target:
        entity_id: lock.front_door
```

What you get end-to-end:

1. A new booking rotates in → the PIN is written into slot 2 (it's installed but the window may not be open yet).
2. `Lock Access Start` arrives → `binary_sensor.beach_house_lock_active` flips `on` → the PIN is (re-)written and now actively opens the door.
3. The guest unlocks with that PIN — if you've wired `Lock entity ID` to `lock.front_door` in the **Configure** panel, that unlock event also flips Guest Status to `in_house`.
4. `Lock Access End` arrives → `binary_sensor.beach_house_lock_active` flips `off` → the slot is cleared and the door is relocked. The PIN no longer works.

> **Tip.** Writing the same PIN twice (once on `guest_changed`, once on lock-active `on`) is idempotent and intentional — it covers both the "booking rotates while the window is already open" case and the normal "booking arrives hours before check-in" case without you having to think about which one fired first.

> **Caveat.** Some Z-Wave locks reject 4-digit PINs that start with `0`, or require exactly N digits. If your PMS-supplied door code doesn't match what your lock accepts, normalise it in the template (`{{ states('sensor.beach_house_door_code') | string | int }}` or a fixed-width pad) before writing.

---

## Events fired by the integration

You can build automations on top of these.

| Event | When it fires |
|---|---|
| `str_concierge_guest_changed` | The "current" booking rotated to a different guest |
| `str_concierge_guest_status_changed` | Guest status transitioned (`due_in` → `in_house`, etc.) |
| `str_concierge_house_state_changed` | House state transitioned |

Each event includes `entry_id`, `property_id`, and the previous + new values.
