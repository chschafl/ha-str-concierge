"""DataUpdateCoordinator for STR Concierge.

Owns the merged view: PMS booking data (refreshed every poll) + locally-stored
lifecycle state (`entered_at`, `house_state`). Derives the guest lifecycle
status (reserved / due_in / in_house / departed / vacant) on every tick.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEPARTED_DWELL_SECONDS,
    DOMAIN,
    EVENT_GUEST_CHANGED,
    EVENT_GUEST_STATUS_CHANGED,
    EVENT_HOUSE_STATE_CHANGED,
    GUEST_DEPARTED,
    GUEST_DUE_IN,
    GUEST_IN_HOUSE,
    GUEST_RESERVED,
    GUEST_VACANT,
    HOUSE_CLEANING,
    HOUSE_DIRTY,
    HOUSE_OCCUPIED,
    HOUSE_READY,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .providers.base import Guest, PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)


@dataclass
class STRState:
    """Merged view of PMS data + local lifecycle. What the entities read."""

    property_id: str
    property_name: str
    current_guest: Guest | None
    next_guest: Guest | None
    guest_status: str
    house_state: str
    lock_access_start: datetime | None
    lock_access_end: datetime | None
    entered_at: datetime | None


@dataclass
class _StoredState:
    """Persisted lifecycle bits. Single-property scope."""

    current_booking_id: str | None = None
    entered_at: str | None = None  # ISO string
    dismissed_booking_id: str | None = None  # set after dwell; treated as departed/skipped
    house_state: str = HOUSE_READY
    house_state_changed_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "current_booking_id": self.current_booking_id,
            "entered_at": self.entered_at,
            "dismissed_booking_id": self.dismissed_booking_id,
            "house_state": self.house_state,
            "house_state_changed_at": self.house_state_changed_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "_StoredState":
        if not raw:
            return cls()
        return cls(
            current_booking_id=raw.get("current_booking_id"),
            entered_at=raw.get("entered_at"),
            dismissed_booking_id=raw.get("dismissed_booking_id"),
            house_state=raw.get("house_state", HOUSE_READY),
            house_state_changed_at=raw.get("house_state_changed_at"),
        )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _booking_summary(guest: Guest | None) -> str:
    """One-line representation of a booking for log lines."""
    if guest is None:
        return "None"
    return (
        f"{guest.name!r} (id={guest.booking_id}, "
        f"checkin={guest.checkin.isoformat()}, "
        f"checkout={guest.checkout.isoformat()})"
    )


class STRCoordinator(DataUpdateCoordinator[STRState]):
    """Single-property coordinator: polls PMS, merges with local state."""

    def __init__(
        self,
        hass: HomeAssistant,
        provider: STRProvider,
        property_id: str,
        poll_interval: int,
        entry_id: str,
        arrival_window_hours: int,
        lock_minutes_before_checkin: int,
        lock_minutes_after_checkout: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._provider = provider
        self._property_id = property_id
        self._entry_id = entry_id
        self._arrival_window = timedelta(hours=arrival_window_hours)
        self._lock_before = timedelta(minutes=lock_minutes_before_checkin)
        self._lock_after = timedelta(minutes=lock_minutes_after_checkout)

        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self._stored = _StoredState()
        self._dwell_cancel: CALLBACK_TYPE | None = None
        self._previous_guest_id: str | None = None
        self._previous_status: str | None = None
        self._previous_house_state: str | None = None

    @property
    def provider(self) -> STRProvider:
        return self._provider

    @property
    def property_id(self) -> str:
        return self._property_id

    # ── Storage ───────────────────────────────────────────────────────

    async def async_load_store(self) -> None:
        raw = await self._store.async_load()
        self._stored = _StoredState.from_dict(raw)

    async def _persist(self) -> None:
        await self._store.async_save(self._stored.as_dict())

    # ── Lock event handler (called by listeners in __init__) ──────────

    async def async_handle_lock_unlocked(self) -> None:
        """Called when the configured lock entity / Keymaster slot reports unlock.

        Latches `entered_at` only if there's a current booking, we're inside
        the lock-access window, and we haven't latched it already.
        """
        data = self.data
        if data is None or data.current_guest is None:
            return
        if self._stored.entered_at is not None:
            return
        now = _now_utc()
        if data.lock_access_start and now < data.lock_access_start:
            return
        if data.lock_access_end and now > data.lock_access_end:
            return

        await self._latch_arrival(data.current_guest)

    # ── Manual overrides (called by buttons) ──────────────────────────

    async def async_manual_mark_arrived(self) -> None:
        data = self.data
        if data is None or data.current_guest is None:
            return
        if self._stored.entered_at is not None:
            return
        await self._latch_arrival(data.current_guest)

    async def async_manual_mark_departed(self) -> None:
        """Force the current guest into `departed`, hold for dwell, then rotate."""
        data = self.data
        if data is None or data.current_guest is None:
            return
        guest = data.current_guest
        # Ensure we have a latch so the dwell rotation has something to clear.
        self._stored.current_booking_id = guest.booking_id
        if self._stored.entered_at is None:
            self._stored.entered_at = _now_utc().isoformat()
        await self._persist()
        try:
            await self._provider.mark_checked_out(guest.booking_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("mark_checked_out failed: %s", err)
        # Fire a synthetic refresh that lands on `departed` and schedules dwell.
        # We override the lock_after to zero by stamping the dwell immediately.
        if self._dwell_cancel is None:
            self._begin_departed_dwell()
        # Force entities to re-read with `departed` derivation.
        await self.async_request_refresh()

    async def async_set_house_state(self, new_state: str) -> None:
        if new_state == self._stored.house_state:
            return
        self._stored.house_state = new_state
        self._stored.house_state_changed_at = _now_utc().isoformat()
        await self._persist()
        await self.async_request_refresh()

    async def async_handle_cleaner_arrived(self) -> None:
        """Cleaner unlocked the door — flip `dirty` → `cleaning`.

        Anything else (occupied, ready, already cleaning) is left alone — we
        don't want a cleaner entering while a guest is in-house to silently
        reset the workflow.
        """
        if self._stored.house_state == HOUSE_DIRTY:
            _LOGGER.info("Cleaner arrival detected — flipping house: dirty → cleaning")
            await self.async_set_house_state(HOUSE_CLEANING)
        else:
            _LOGGER.debug(
                "Cleaner arrival detected but house state is %s — no change "
                "(only auto-flips from `dirty`)",
                self._stored.house_state,
            )

    # ── Internal helpers ──────────────────────────────────────────────

    async def _latch_arrival(self, guest: Guest) -> None:
        self._stored.current_booking_id = guest.booking_id
        self._stored.entered_at = _now_utc().isoformat()
        self._stored.dismissed_booking_id = None
        await self._persist()
        try:
            await self._provider.mark_arrived(guest.booking_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("mark_arrived skipped/failed: %s", err)
        await self.async_request_refresh()

    def _begin_departed_dwell(self) -> None:
        """Schedule a one-shot rotation after DEPARTED_DWELL_SECONDS."""

        async def _rotate(_now: datetime) -> None:
            self._dwell_cancel = None
            old_id = self._stored.current_booking_id
            if old_id is not None:
                self._stored.dismissed_booking_id = old_id
            self._stored.entered_at = None
            if self._stored.house_state == HOUSE_OCCUPIED:
                self._stored.house_state = HOUSE_DIRTY
                self._stored.house_state_changed_at = _now_utc().isoformat()
            await self._persist()
            await self.async_request_refresh()

        @callback
        def _schedule(now: datetime) -> None:
            self.hass.async_create_task(_rotate(now))

        self._dwell_cancel = async_call_later(
            self.hass, DEPARTED_DWELL_SECONDS, _schedule
        )

    # ── Main poll ─────────────────────────────────────────────────────

    async def _async_update_data(self) -> STRState:
        try:
            pd = await self._provider.get_property_data(self._property_id)
        except Exception as err:
            raise UpdateFailed(f"Error fetching property {self._property_id}: {err}") from err

        _LOGGER.debug(
            "Poll: provider returned current=%s, next=%s",
            _booking_summary(pd.current_guest),
            _booking_summary(pd.next_guest),
        )

        # If PMS still surfaces the dismissed booking as current, skip past it
        # by promoting the next booking into the current slot.
        pd = self._apply_dismissal(pd)

        # Promote next_guest → current_guest when their arrival window has
        # opened but the PMS hasn't started the booking yet (PMS only marks
        # a booking "current" between checkin and checkout). Without this,
        # an upcoming guest would sit in `next` forever and the integration
        # would just show `vacant`.
        pd = self._promote_upcoming(pd)

        new_current_id = pd.current_guest.booking_id if pd.current_guest else None

        # Detect PMS-side booking rotation.
        if new_current_id != self._stored.current_booking_id:
            self._stored.current_booking_id = new_current_id
            self._stored.entered_at = None
            # If the PMS has rotated past the dismissed booking, drop the dismissal.
            if (
                self._stored.dismissed_booking_id is not None
                and new_current_id != self._stored.dismissed_booking_id
            ):
                self._stored.dismissed_booking_id = None
            await self._persist()

        state = self._derive_state(pd)

        _LOGGER.debug(
            "Poll: derived status=%s, house=%s, current=%s, next=%s, "
            "lock_window=[%s .. %s], entered_at=%s",
            state.guest_status,
            state.house_state,
            _booking_summary(state.current_guest),
            _booking_summary(state.next_guest),
            state.lock_access_start.isoformat() if state.lock_access_start else None,
            state.lock_access_end.isoformat() if state.lock_access_end else None,
            state.entered_at.isoformat() if state.entered_at else None,
        )

        # Schedule departed-dwell when the lock window has expired post-arrival.
        if state.guest_status == GUEST_DEPARTED and self._dwell_cancel is None:
            self._begin_departed_dwell()

        await self._fire_change_events(state)
        return state

    def _apply_dismissal(self, pd: PropertyData) -> PropertyData:
        dismissed = self._stored.dismissed_booking_id
        if (
            dismissed is None
            or pd.current_guest is None
            or pd.current_guest.booking_id != dismissed
        ):
            return pd
        return PropertyData(
            property_id=pd.property_id,
            property_name=pd.property_name,
            current_guest=pd.next_guest,
            next_guest=None,
        )

    def _promote_upcoming(self, pd: PropertyData) -> PropertyData:
        """When current is empty but next is within the arrival window, promote.

        We surface the upcoming guest as `current` so all the entities
        (name, door code, check-in/out, lock window, status) populate the
        moment we cross into `due_in`. This is what the README's "next booking
        takes the Current Guest slot automatically" promise relies on.
        """
        if pd.current_guest is not None or pd.next_guest is None:
            return pd
        now = _now_utc()
        if now < pd.next_guest.checkin - self._arrival_window:
            return pd
        return PropertyData(
            property_id=pd.property_id,
            property_name=pd.property_name,
            current_guest=pd.next_guest,
            next_guest=None,
        )

    # ── State derivation ──────────────────────────────────────────────

    def _derive_state(self, pd: PropertyData) -> STRState:
        now = _now_utc()
        entered_at = _parse_iso(self._stored.entered_at)

        guest = pd.current_guest
        lock_start = (guest.checkin - self._lock_before) if guest else None
        lock_end = (guest.checkout + self._lock_after) if guest else None

        if guest is None:
            guest_status = GUEST_VACANT
        elif entered_at is not None:
            if lock_end and now >= lock_end:
                guest_status = GUEST_DEPARTED
            else:
                guest_status = GUEST_IN_HOUSE
        elif now >= guest.checkin - self._arrival_window:
            guest_status = GUEST_DUE_IN
        else:
            guest_status = GUEST_RESERVED

        if guest_status == GUEST_IN_HOUSE:
            house_state = HOUSE_OCCUPIED
        else:
            house_state = self._stored.house_state

        return STRState(
            property_id=pd.property_id,
            property_name=pd.property_name,
            current_guest=guest,
            next_guest=pd.next_guest,
            guest_status=guest_status,
            house_state=house_state,
            lock_access_start=lock_start,
            lock_access_end=lock_end,
            entered_at=entered_at,
        )

    # ── Event firing ──────────────────────────────────────────────────

    async def _fire_change_events(self, state: STRState) -> None:
        current_id = state.current_guest.booking_id if state.current_guest else None

        if current_id != self._previous_guest_id:
            _LOGGER.info(
                "Guest changed: %s → %s",
                self._previous_guest_id,
                _booking_summary(state.current_guest),
            )
            self.hass.bus.async_fire(
                EVENT_GUEST_CHANGED,
                {
                    "entry_id": self._entry_id,
                    "property_id": state.property_id,
                    "property_name": state.property_name,
                    "previous_guest_id": self._previous_guest_id,
                    "current_guest_id": current_id,
                    "current_guest": state.current_guest.name if state.current_guest else None,
                },
            )
            self._previous_guest_id = current_id

        if state.guest_status != self._previous_status:
            _LOGGER.info(
                "Guest status: %s → %s",
                self._previous_status,
                state.guest_status,
            )
            self.hass.bus.async_fire(
                EVENT_GUEST_STATUS_CHANGED,
                {
                    "entry_id": self._entry_id,
                    "property_id": state.property_id,
                    "previous_status": self._previous_status,
                    "status": state.guest_status,
                },
            )
            self._previous_status = state.guest_status

        if state.house_state != self._previous_house_state:
            _LOGGER.info(
                "House state: %s → %s",
                self._previous_house_state,
                state.house_state,
            )
            self.hass.bus.async_fire(
                EVENT_HOUSE_STATE_CHANGED,
                {
                    "entry_id": self._entry_id,
                    "property_id": state.property_id,
                    "previous_state": self._previous_house_state,
                    "state": state.house_state,
                },
            )
            # Persist live-derived house state (so `occupied` survives a restart).
            if state.house_state != self._stored.house_state:
                self._stored.house_state = state.house_state
                self._stored.house_state_changed_at = _now_utc().isoformat()
                await self._persist()
            self._previous_house_state = state.house_state
