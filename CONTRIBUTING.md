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

### Getting Python set up on macOS

You need Python **3.13 or newer** to run the test suite (the pinned `pytest-homeassistant-custom-component` requires it). macOS ships with a Python in `/usr/bin/python3`, but it's locked to whatever version Apple decided, and you really don't want to `pip install` into it. Pick one of these instead:

#### Option A — VS Code Dev Container (zero Python install on your Mac)

If you have Docker Desktop installed and use VS Code, this is the lowest-friction option. Open the repo, accept "Reopen in Container", and everything — Python, deps, ruff, mypy — comes preconfigured. You never touch your Mac's Python.

```bash
brew install --cask docker visual-studio-code
code /path/to/ha-str-concierge   # then click "Reopen in Container" when prompted
```

Best for: people who already use Docker, or who don't want to manage Python versions on the host. Trade-off: container startup adds a few seconds, and running an HA instance against the symlinked code happens outside the container.

#### Option B — pyenv (recommended for serious work)

Home Assistant bumps its minimum Python version regularly, and you'll eventually want to run multiple versions side-by-side (e.g. one for HA, one for some other project). `pyenv` makes that painless:

```bash
brew install pyenv
echo 'eval "$(pyenv init -)"' >> ~/.zshrc   # or ~/.bash_profile
exec $SHELL                                  # reload your shell

pyenv install 3.13                           # download + build Python 3.13
cd /path/to/ha-str-concierge
pyenv local 3.13                             # pins this repo to 3.13 via a .python-version file
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
```

Best for: regular contributors. You get a per-project Python version, isolated venvs, and you can bump versions without breaking anything else.

#### Option C — Homebrew (simplest if you don't care about version juggling)

```bash
brew install python@3.13
cd /path/to/ha-str-concierge
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
```

Best for: one-off contributions. Trade-off: when Home Assistant requires a newer Python in a year, you'll be back to `brew install python@3.14` and rebuilding venvs.

#### What we don't recommend

- **`/usr/bin/python3`** (system Python) — too old, breaks on Apple updates, no clean way to install packages
- **Anaconda / Miniconda** — works, but adds a layer of abstraction that's overkill here and tends to conflict with system tooling
- **`pip install --user`** without a venv — pollutes your global site-packages and makes future cleanup painful

### One-time setup

Once you've got Python sorted (see above), clone the repo and wire it into your local HA:

```bash
git clone https://github.com/chschafl/ha-str-concierge.git
cd ha-str-concierge
python -m venv .venv && source .venv/bin/activate    # skip if using the dev container
pip install -r requirements_test.txt
make symlink         # links custom_components/str_concierge → ~/.homeassistant/custom_components/str_concierge
```

Then restart Home Assistant **once** to pick up the symlink. From that point on, every edit to a source file is immediately reflected in HA — just **Settings → Devices & Services → STR Concierge → ⋮ → Reload** to apply changes.

### Configuring the Makefile (`HASS_CONFIG` and `HASS_SSH`)

The Makefile reads two variables to know **where** your Home Assistant lives. Set them once in a `.env` file at the repo root and forget about them:

```bash
# .env  (gitignored — your local config only)
HASS_CONFIG=/config
HASS_SSH=root@homeassistant.local
```

#### `HASS_CONFIG` — path to HA's config directory

This is the directory that contains `configuration.yaml`. Where it lives depends on how you run HA:

| HA installation | Typical path |
|---|---|
| HA OS / Supervised (running on a Pi, NUC, VM) | `/config` (as seen from inside HA / over SSH) |
| HA Container (Docker) | Whatever you mounted to `/config` |
| HA Core (venv install) | `~/.homeassistant` (the default) |
| Running HA on the same Mac as your dev machine | `~/.homeassistant` |

If you're not sure: in the HA UI, **Settings → System → Repairs → ⋮ → System Information** shows the config dir path.

#### `HASS_SSH` — SSH target for a remote HA

Only needed if HA runs on a different machine. Format is `user@host` or `user@host:port`. Examples:

- HA OS via the **SSH & Web Terminal** add-on: `root@homeassistant.local` (or its IP)
- A custom Linux install: `pi@192.168.1.42`
- Non-standard port: `root@homeassistant.local:22222`

Skip this entirely if you're developing on the same machine as HA.

### Setting up SSH access to Home Assistant

If `make deploy-ssh` gives you `Connection refused` or `Permission denied`, SSH isn't set up on the HA side yet. Here's how to fix it for each install type.

#### HA OS / Supervised (the most common case)

HA OS doesn't have SSH enabled by default — you install it as an add-on.

1. In HA: **Settings → Add-ons → Add-on Store**
2. Install **Advanced SSH & Web Terminal** (the community one by Frenck, not the official one — the official add-on locks you into a restricted shell that breaks `rsync`)
3. Open the add-on's **Configuration** tab. The YAML config matters in three places:
   ```yaml
   ssh:
     username: root
     password: ""             # leave blank, we use keys
     authorized_keys:
       - "ssh-ed25519 AAAA…your-public-key… your-comment"
     sftp: false
     compatibility_mode: false
     port: 22                 # ⚠️ if this is 0 the SSH server is DISABLED
   packages:
     - rsync                  # required for `make deploy-ssh` — not installed by default
   ```
   - **`ssh.port`** must be `22` (or another port). **A value of `0` disables the SSH server entirely** — you'll get `Connection refused` even though the add-on appears to be running. The add-on log will say `WARNING: SSH port is disabled. Prevent start of SSH server.`
   - **`packages: [rsync]`** is required for `make deploy-ssh` to work — the add-on doesn't ship rsync by default, and installs Alpine packages listed here on every start.
   - **`authorized_keys`** is a YAML list, one entry per public key.
4. Generate an SSH key on your Mac if you don't already have one — and see ["When you're running inside the VS Code dev container"](#when-youre-running-inside-the-vs-code-dev-container) below for the equivalent flow in a container:
   ```bash
   ssh-keygen -t ed25519 -C "ha-dev"        # press Enter through the prompts
   cat ~/.ssh/id_ed25519.pub                # paste this into authorized_keys above
   ```
5. **Start** (or restart) the add-on. Enable **Start on boot** and **Watchdog**. Watch the log — you want to see `Starting OpenSSH daemon` and `Server listening on 0.0.0.0 port 22`.
6. Test from your Mac:
   ```bash
   ssh root@homeassistant.local
   ssh root@homeassistant.local "rsync --version"   # confirms rsync is on PATH
   ```
   Both should work. If so, `make deploy-ssh` will too.

#### When you're running inside the VS Code dev container

The dev container is its own little Linux box with no SSH keys of its own. If you try to `ssh root@homeassistant.local` from a container terminal, you'll get `Permission denied (publickey)` even though your Mac's keys work fine — the container can't see them.

Two options:

**Option 1 — generate a key inside the container** (quickest, but the key disappears on container rebuild):
```bash
# inside the dev container
ssh-keygen -t ed25519 -C "ha-dev-container" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```
Paste the public key into HA's `authorized_keys` (as a new entry — keep your Mac's key too).

**Option 2 — bind-mount your Mac's `~/.ssh` into the container** (permanent, survives rebuilds):
Add this to `.devcontainer/devcontainer.json`:
```json
"mounts": [
  "source=${localEnv:HOME}/.ssh,target=/home/vscode/.ssh,type=bind,readonly"
]
```
Rebuild the container. Now your Mac's keys are visible inside the container, and you only need your Mac's pubkey in HA.

#### HA Container (Docker)

Containers don't usually have SSH inside them. Two options:

- **SSH to the host** and set `HASS_CONFIG` to the path that's bind-mounted into the container. The Makefile rsyncs to the host filesystem; HA picks up the file changes on the next reload because of the bind mount.
- Or, use `docker cp` instead of rsync — not built into the Makefile, but doable as a one-liner: `docker cp custom_components/str_concierge homeassistant:/config/custom_components/`.

#### HA Core (Linux venv)

Standard `sshd` on the host. Same setup as any Linux box — make sure `sshd` is running (`sudo systemctl status ssh`) and your public key is in `~/.ssh/authorized_keys` on the HA side.

### Troubleshooting `make deploy` / `make deploy-ssh`

| Symptom | Likely cause | Fix |
|---|---|---|
| `Connection refused` and add-on log says `SSH port is disabled` | `ssh.port: 0` in the add-on config | Set `ssh.port: 22` and restart the add-on |
| `Connection refused` (no add-on log message) | SSH add-on not installed or not started | Install **Advanced SSH & Web Terminal**, start it, enable "Start on boot" |
| `Could not resolve hostname homeassistant.local` | mDNS not working on your network | Use HA's IP address instead: `HASS_SSH=root@192.168.1.42` |
| `Permission denied (publickey)` from your Mac | Your Mac's public key isn't in the add-on's `authorized_keys` | Append `~/.ssh/id_ed25519.pub` to `authorized_keys` in the add-on config, restart the add-on |
| `Permission denied (publickey)` from inside the dev container | Container has no keys, or the host's keys aren't mounted in | Generate a key inside the container OR bind-mount `~/.ssh` (see ["dev container" section above](#when-youre-running-inside-the-vs-code-dev-container)) |
| `bash: rsync: command not found` after SSH succeeds | rsync isn't installed in the add-on | Add `packages: [rsync]` to the add-on config and restart |
| `rsync: command not found` and you can't shell out at all | You're on the **official** "SSH" add-on, which uses a sandboxed shell | Switch to **Advanced SSH & Web Terminal** |
| `make deploy` (no `-ssh`) fails with "No such file or directory" | `HASS_CONFIG` points at a path that doesn't exist on your Mac | Either fix the path or use `make deploy-ssh` for remote HA |
| Changes don't show up after deploy | HA cached the old code | **Settings → Devices & Services → STR Concierge → ⋮ → Reload** (or restart HA) |

### Remote HA over SSH — quick reference

Once SSH is working:

```bash
make deploy-ssh         # rsync once
make deploy-ssh-reload  # rsync + restart HA
make deploy-watch       # auto-rsync on every save (macOS: fswatch, Linux: inotifywait)
make restart-ssh        # restart HA without redeploying
make logs               # tail HA logs (uses HASS_SSH if set, otherwise local file)
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
