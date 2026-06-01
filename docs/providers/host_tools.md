# Host Tools provider — implementation notes

Source: [`custom_components/str_concierge/providers/host_tools.py`](../../custom_components/str_concierge/providers/host_tools.py)
API reference: <https://help.hosttools.com/en/articles/10118922-host-tools-api-docs>

## Auth

Host Tools uses a **custom header** — **not** standard Bearer auth:

```
authToken: <your-token>
```

If you try `Authorization: Bearer <token>` against Host Tools you'll get back the marketing site HTML instead of an API response (the request is silently routed to the React app shell). The custom `authToken` header is the only one that wakes up the API layer.

Get your token from the Host Tools dashboard under **Settings → API**.

## Base URL

```
https://app.hosttools.com/api
```

No `/v1` path segment. Overridable via the provider's `base_url` constructor argument (not exposed in the config flow — it's a hook for tests and custom deployments).

## Endpoints used

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/getListings` | All listings accessible with this token |
| `GET` | `/getReservations/{listingId}/{startDate}/{endDate}` | All reservations whose `[checkIn, checkOut]` overlaps the date window |

The config flow calls `/getListings` to populate the property picker (which doubles as credential validation — if it returns a 401, the config flow shows `cannot_connect`).

The coordinator calls `/getReservations` every poll. Dates in the path are formatted as `YYYY-MM-DD` (UTC); we query a rolling window from "yesterday" through "+180 days" — enough to surface the still-active checkout from earlier today, the current guest, and the next several months of upcoming bookings without pulling the entire calendar.

## Response handling

Both endpoints return either:

- A raw JSON array: `[ {...}, {...} ]`
- A wrapped envelope: `{ "listings": [...] }` / `{ "reservations": [...] }` / `{ "data": [...] }`

All shapes are unwrapped transparently.

## Status filtering

Host Tools includes calendar blocks and cancelled bookings in the same response stream as real reservations. The provider filters by the `status` (or `reservationStatus`) field:

| Bucket | Values | What we do |
|---|---|---|
| **Active** | `accepted`, `confirmed`, `pending`, `inquiry` | Surface as a guest |
| **Skip** | `cancelled`, `canceled`, `declined`, `blocked` | Drop silently |
| **Unknown** | anything else | Drop with a DEBUG log line |

## Field mapping

Host Tools is inconsistent across endpoints and integration sources, so each of our fields tries multiple candidate keys in order:

**Reservations (`Guest`)**:

| Our field | Host Tools keys (in order) |
|---|---|
| `booking_id` | `_id`, `id`, `confirmationCode`, `confirmation_code` |
| `name` | `guestFirstName + ' ' + guestLastName`, falling back to `firstName + ' ' + lastName`, falling back to `guestName` or `name` |
| `checkin` *(date)* | `checkIn`, `startDate`, `start_date` |
| `checkin` *(time of day)* | `checkInTime`, `checkin_time`, `startTime` — combined with the date above |
| `checkout` *(date)* | `checkOut`, `endDate`, `end_date` |
| `checkout` *(time of day)* | `checkOutTime`, `checkout_time`, `endTime` |
| `door_code` | `lockCode`, `doorCode`, `door_code`, `accessCode`, `access_code` |

### Date + time-of-day handling

Host Tools sends the check-in date and the check-in time-of-day as **separate fields** — `checkIn` is just `"2026-06-01"`, with `checkInTime` carrying the hour. The provider combines them so the integration's lock-window and `due_in` calculations use the real arrival clock, not midnight UTC.

The time field is parsed in any of these forms:

| Input | Interpretation |
|---|---|
| `16` (number) | `16:00` |
| `15.5` (number) | `15:30` |
| `"16"` (string) | `16:00` |
| `"15:30"` (string) | `15:30` |
| `"4:00 PM"` / `"4 PM"` | `16:00` |
| ISO timestamp containing `T16:00` | `16:00` |

#### Timezone semantics

Host Tools sends times in **property-local wall-clock**, regardless of how the field is formatted. Critically, **even when `checkIn` looks like a UTC ISO timestamp with a `Z` suffix** (e.g. `"2026-06-01T11:00:00Z"`), the time portion is still local — the `Z` is misleading. The reference TypeScript implementation handles this by always extracting just the time portion and ignoring any embedded offset; this provider does the same.

So the rule is uniform: pull the date and the time-of-day out of whatever fields are present, stamp HA's configured timezone (`dt_util.DEFAULT_TIME_ZONE`) on the result, and convert to UTC for storage. Example walk-through, HA set to `America/Los_Angeles` (PDT in summer, UTC-7):

| Host Tools sends | Interpreted as | Stored as | HA renders to user |
|---|---|---|---|
| `checkIn: "2026-06-01"`, `checkInTime: 11` | `2026-06-01 11:00` local | `2026-06-01 18:00 UTC` | `11:00 AM` |
| `checkIn: "2026-06-01T11:00:00Z"` (no explicit time field) | `2026-06-01 11:00` local (Z ignored) | `2026-06-01 18:00 UTC` | `11:00 AM` |
| `checkIn: "2026-06-01"`, no time at all | `2026-06-01 00:00` local | `2026-06-01 07:00 UTC` | `12:00 AM` |

Caveat: this assumes HA's configured timezone matches the property's timezone. For most short-term-rental setups (HA running on a device at or near the property) that's the case. If you manage a remote property from a different timezone, configure HA to the property's timezone — **not** your own — or set the lock-window offsets to compensate.

### Door code

The canonical Host Tools field is **`lockCode`**. The provider also accepts `doorCode`, `door_code`, `accessCode`, and `access_code` defensively, since variant integration payloads sometimes use those instead. When a reservation parses successfully but no door code is found, the provider logs the full payload key list at DEBUG so you can see what's actually there.

**Listings (`Property`)**:

| Our field | Host Tools keys (in order) |
|---|---|
| `id` | `_id`, `id`, `listingId` |
| `name` | `nickname`, `name`, `title` |

If Host Tools changes a key name, the fix is to append the new name to the matching list in `_parse_reservation` / `_parse_listing` — no other code changes required.

## Datetime parsing

Tries these formats in order:

1. `%Y-%m-%dT%H:%M:%S.%fZ` — ISO-8601 with milliseconds, UTC Z
2. `%Y-%m-%dT%H:%M:%SZ` — ISO-8601, UTC Z
3. `%Y-%m-%dT%H:%M:%S%z` — ISO-8601 with offset
4. `%Y-%m-%d` — date only (treated as midnight UTC)

Naive datetimes get stamped UTC.

## `mark_arrived` / `mark_checked_out`

**Not implemented.** Host Tools' API has `POST /setreservation/{id}` for writing fields like `doorCode` and `guideBookURL`, but there isn't a clean "advance the reservation status" call that maps to STR Concierge's arrived/departed lifecycle. The integration's local state is the source of truth for the guest lifecycle anyway — the lock event drives `in_house`, time + courtesy window drives `departed` — so the missing write-back doesn't degrade behavior.

If a future Host Tools API release adds proper status transitions, this is the place to wire them in.

## Known quirks

- **The wrong base URL silently returns HTML.** `https://app.hosttools.com/api/v1/listings` (which a previous version of this provider used) returns the React marketing-site HTML instead of a 404, because `app.hosttools.com` serves both the dashboard SPA and the API and falls through to the SPA on unknown paths. If you see HTML in a debug log, the base URL or path is wrong.
- **`Authorization: Bearer` is silently ignored.** Same failure mode as above — Host Tools doesn't 401 on the wrong header, it just returns the SPA. The custom `authToken` header is mandatory.
- **`property_name` mirrors `property_id`.** Host Tools doesn't include the listing name in the reservation payload, and we'd need a second HTTP call to look it up. HA's device registry lets the user rename the device, so this is rarely user-visible.
- **Bookings with missing `checkin`, `checkout`, or `booking_id` are silently skipped** (logged at DEBUG). This guards against partial blocks / drafts in the calendar.

## Testing

See [`tests/providers/test_host_tools.py`](../../tests/providers/test_host_tools.py). Tests use `aioresponses` to mock the HTTP layer — no live token needed.

```bash
pytest tests/providers/test_host_tools.py -v
```
