# Contributing to STR Concierge

**Short-term rental hosts run their lives on a lot of different tools.** Host Tools, Hostfully, Guesty, Lodgify, Smoobu, OwnerRez, Hospitable, Beds24 — the list keeps going, and every host swears by a different one. STR Concierge has a few providers built in, but it only really becomes useful for *your* setup if your PMS is one of them.

**That's where you come in.** If your PMS isn't supported yet, you're probably the right person to add it — you already have an account, you already know what the booking flow looks like, and you probably already know which fields contain what. Adding a provider is a self-contained ~50–100 line file with a clear interface, and we'll help you over the line.

This doc covers:

1. [Adding a new PMS provider](#adding-a-new-pms-provider)
2. [What to do when your PMS doesn't support everything](#what-if-the-pms-doesnt-support-everything)
3. [Development lifecycle — how to test changes against a real HA](#development-lifecycle)
4. [Code style and PR checklist](#code-style-and-pr-checklist)

---

## Adding a new PMS provider

A provider's job is small and well-bounded:

> Given an API key (and optionally a base URL), give me back the list of properties this account owns, and for any one property tell me who the current and next guest are.

That's literally two methods. Two optional methods on top of that let the integration push status updates back into the PMS when the user manually marks a guest arrived/departed.

### The interface

Every provider subclasses `STRProvider` from [`custom_components/str_concierge/providers/base.py`](custom_components/str_concierge/providers/base.py):

```python
class STRProvider(ABC):
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        ...

    @abstractmethod
    async def get_properties(self) -> list[Property]:
        """All properties this account can see."""

    @abstractmethod
    async def get_property_data(self, property_id: str) -> PropertyData:
        """Current and next booking for one property."""

    # Optional — providers raise NotImplementedError if unsupported.
    async def mark_arrived(self, booking_id: str) -> bool: ...
    async def mark_checked_out(self, booking_id: str) -> bool: ...
```

The data models are dead simple ([`providers/base.py`](custom_components/str_concierge/providers/base.py)):

```python
@dataclass
class Guest:
    booking_id: str          # whatever uniquely identifies a booking in your PMS
    name: str                # display name
    checkin: datetime        # timezone-aware
    checkout: datetime       # timezone-aware
    door_code: str | None    # optional

@dataclass
class Property:
    id: str
    name: str

@dataclass
class PropertyData:
    property_id: str
    property_name: str
    current_guest: Guest | None
    next_guest: Guest | None
```

Note: phone, email, and reservation status are intentionally NOT in the model. The integration derives status from the lock event + the booking calendar, and contacting the guest is the host's job, not the integration's.

### Five-step recipe

1. **Create the file**: `custom_components/str_concierge/providers/your_pms.py`
2. **Subclass `STRProvider`** and implement `get_properties()` and `get_property_data()`
3. **Add a constant** in [`const.py`](custom_components/str_concierge/const.py) — e.g. `PROVIDER_YOUR_PMS = "your_pms"`, append it to `PROVIDER_OPTIONS`
4. **Register the factory** in [`providers/__init__.py`](custom_components/str_concierge/providers/__init__.py) — one `if provider_type == ...: return YourPMSProvider(...)` line
5. **Add the display label** in `config_flow.py`'s `_PROVIDER_LABELS` dict

That's it — the config flow, coordinator, entities, services, and events all pick the new provider up automatically.

### Look at the existing providers

The cleanest template to copy is [`providers/custom_endpoint.py`](custom_components/str_concierge/providers/custom_endpoint.py) — it's small, it shows the field-aliasing pattern (`_first(raw, ["camelCase", "snake_case", "alias"])`) we use everywhere to be resilient to API quirks, and it doesn't have provider-specific auth complexity.

- [`host_tools.py`](custom_components/str_concierge/providers/host_tools.py) — Bearer auth, simple REST
- [`hostfully.py`](custom_components/str_concierge/providers/hostfully.py) — API-key in header, slightly chattier
- [`guesty.py`](custom_components/str_concierge/providers/guesty.py) — OAuth2 client-credentials with token caching/refresh

If your PMS uses OAuth2, `guesty.py` is your reference. If it's Bearer/API-key, copy `host_tools.py`.

---

## What if the PMS doesn't support everything?

**Not every PMS exposes everything we'd ideally like.** Some don't have a "list all my properties" endpoint. Some don't return door codes. Some don't accept programmatic status updates. **All of that is fine** — the integration is designed to degrade gracefully, and your provider can just mock or omit the bits that aren't available. Here's the playbook:

### Missing `get_properties()`
Some PMS APIs expect you to know your listing ID up front (e.g. you got it from the PMS dashboard URL). In that case, just return a synthetic list with a single placeholder so the config flow has something to show:

```python
async def get_properties(self) -> list[Property]:
    # PMS has no list endpoint — return a placeholder. User can rename
    # the property in HA's device registry after setup.
    return [Property(id="default", name="My Property")]
```

Or, if the user has to paste in their listing ID during setup, add a config-flow field for it and return that:

```python
async def get_properties(self) -> list[Property]:
    return [Property(id=self._listing_id, name=self._listing_id)]
```

### No door code in the API
Just leave `door_code=None`. The integration will skip writing it to Keymaster. Hosts who want a door code can set it manually via input_text in HA and reference that in their automations.

### No `mark_arrived` / `mark_checked_out` endpoints
Don't implement them. The base class raises `NotImplementedError` and the integration treats those calls as no-ops (the local state still latches correctly). Users get a warning in the log; that's fine.

### Status field uses different vocabulary
Doesn't matter. STR Concierge no longer reads booking status from the PMS — it derives the lifecycle from the booking calendar plus the door-lock event. As long as `get_property_data()` returns the right `current_guest` for "right now", you're done.

### Polling rate-limit too aggressive
The user controls the poll interval in the config flow (60–3600 seconds). If your PMS only supports, say, 1 request/minute, document that in your provider's docstring and recommend a minimum poll interval in your PR.

### Some bookings are "blocks" / "owner stays" / etc.
Filter them out in `_parse_reservation` — return `None` for entries the host doesn't want surfaced as a paying-guest booking. The integration ignores `None` parses.

### Webhooks instead of polling
If your PMS pushes webhooks, you can still implement the polling path first (lower bar to merge) and we can layer a webhook receiver on top later. Webhook support is on the roadmap and not blocked on any one provider.

---

## Development lifecycle

The fastest workflow is **symlink the integration into a local HA, edit files in your IDE, reload the integration from HA's UI.** No copying, no rebuilding.

### One-time setup

```bash
git clone https://github.com/chschafl/ha-str-concierge.git
cd ha-str-concierge
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
make symlink         # links custom_components/str_concierge → ~/.homeassistant/custom_components/str_concierge
```

Then restart Home Assistant **once** to pick up the symlink. From that point on, every edit to a source file is immediately reflected in HA — just **Settings → Devices & Services → STR Concierge → ⋮ → Reload** to apply changes.

### Remote HA over SSH

If your HA runs on a Pi or a separate box, put your SSH target in a `.env` file:

```bash
# .env
HASS_SSH=user@homeassistant.local
HASS_CONFIG=/config
```

Then:

```bash
make deploy-ssh         # rsync once
make deploy-ssh-reload  # rsync + restart HA
make deploy-watch       # auto-rsync on every save (macOS: fswatch, Linux: inotifywait)
```

### Run the test suite

```bash
make test          # all tests
make test-cov      # with coverage report
pytest tests/providers/test_host_tools.py -v   # one provider
```

The tests mock HTTP with `aioresponses` and the HA core with `pytest-homeassistant-custom-component` — **no live PMS credentials needed**. Aim to add tests for your provider in `tests/providers/test_your_pms.py` covering at minimum:

- `get_properties()` happy path
- `get_property_data()` returning a current guest
- `get_property_data()` with no reservations → `current_guest=None`
- One alternate-field-name case to verify the field-aliasing

### Lint & format

```bash
make lint     # ruff check + mypy
make format   # ruff format
```

PRs run the same checks in CI — clean locally before pushing.

### Watch the integration in HA

```bash
make logs     # tails ~/.homeassistant/home-assistant.log filtered to str_concierge
```

Or in HA: **Settings → System → Logs**, filter by `custom_components.str_concierge`.

### Trigger state transitions during testing

The integration polls every 5 minutes by default. To force a refresh on demand:

- **Settings → Devices & Services → STR Concierge → ⋮ → Reload** — full reload, picks up code changes too
- Call the service `homeassistant.update_entity` on any STR Concierge sensor — triggers an immediate coordinator refresh
- For lock-event testing without a real lock: fire the `keymaster_lock_state_changed` event manually from **Developer Tools → Events**, or use **Developer Tools → States** to set your configured `lock.*` entity to `unlocked`

### Dev container (VS Code)

Open the repo in VS Code and accept the "Reopen in Container" prompt. The container pre-installs all test dependencies. Run tests from the integrated test runner or `make test` in the terminal.

---

## Code style and PR checklist

Before opening a PR:

- [ ] `make lint` passes
- [ ] `make test` passes (or 4 pre-existing aioresponses URL-matching failures — not your problem)
- [ ] New provider has at least 4 tests in `tests/providers/test_your_pms.py`
- [ ] Provider file has a docstring at the top documenting auth, base URL, key endpoints, and any quirks ("rate limited to 1 req/min", "doesn't support mark_arrived", etc.)
- [ ] If your provider needs a different config-flow field (e.g. an extra `account_id`), add the form schema in `config_flow.py` gated by `if self._provider == YOUR_PROVIDER`
- [ ] Provider label added to `_PROVIDER_LABELS` and to translations (`strings.json`, `translations/*.json`) if user-facing
- [ ] No secrets in commits — credentials are config-entry data, never logged at INFO level

### A few conventions worth knowing

- **Field aliasing**: use the `_first(raw, ["primaryKey", "alternate_key", "another_alias"])` pattern. PMSes change field names without notice, and aliasing means a future bug is a one-line fix.
- **Timezone-aware datetimes only**: every `checkin` / `checkout` must have `tzinfo`. Use the `_parse_dt()` helper or write your own; if the API returns naive datetimes, assume UTC and stamp it.
- **Log levels**: `_LOGGER.info` for things the user might want to see (guest changes), `_LOGGER.debug` for parsing details, `_LOGGER.warning` for genuine problems (couldn't parse, missing required field). Never log credentials or door codes at INFO.
- **No `print()`**, no `assert` in production code paths, no bare `except:`.

---

## Questions, ideas, or stuck on something?

Open an issue with the `provider-request` label — even a one-liner ("trying to add Lodgify, their auth is weird") is enough to start a conversation. We'd rather help you get it merged than have you give up halfway through.

Thanks for making STR Concierge useful for more hosts. 🏡
