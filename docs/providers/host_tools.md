# Host Tools provider — implementation notes

Source: [`custom_components/str_concierge/providers/host_tools.py`](../../custom_components/str_concierge/providers/host_tools.py)
API reference: <https://help.hosttools.com/en/articles/10118922-host-tools-api-docs>

## Auth

Bearer token passed as the `Authorization` header on every request:

```
Authorization: Bearer <token>
```

Get your token from the Host Tools dashboard under **Settings → API**.

## Base URL

```
https://app.hosttools.com/api/v1
```

Overridable via the provider's `base_url` constructor argument (the integration's config flow doesn't expose this — it's a hook for tests and custom deployments).

## Endpoints used

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/listings` | List all properties accessible with this token |
| `GET` | `/reservations?listingId={id}` | Active + upcoming bookings for one listing |
| `PATCH` | `/reservations/{id}` | Update reservation status (used for `mark_arrived` / `mark_checked_out`) |

The integration polls `/reservations` every `poll_interval` seconds (default 300) and runs `_pick_current_and_next()` over the result to figure out which booking is `current` and which is `next`.

## Response handling

Both list endpoints accept either:

- A raw JSON array: `[ {...}, {...} ]`
- A wrapped envelope: `{ "listings": [...] }` or `{ "data": [...] }` (for `/listings`), `{ "reservations": [...] }` or `{ "data": [...] }` (for `/reservations`)

The provider unwraps both shapes transparently.

## Field mapping

Host Tools' JSON keys → our `Guest` dataclass fields, with fallback aliases for resilience to API changes:

| Field | Candidate JSON keys (in order) |
|---|---|
| `booking_id` | `_id`, `id`, `reservationId` |
| `name` | `guestName`, `guest_name`, `name` |
| `checkin` | `startDate`, `checkIn`, `check_in`, `start_date` |
| `checkout` | `endDate`, `checkOut`, `check_out`, `end_date` |
| `door_code` | `doorCode`, `door_code`, `accessCode`, `access_code` |

And for `Property` (listing):

| Field | Candidate JSON keys (in order) |
|---|---|
| `id` | `_id`, `id`, `listingId` |
| `name` | `nickname`, `name`, `title` |

If Host Tools changes a field name, the fix is to add the new name to the corresponding list in `_RESERVATION_FIELD_MAP` / `_LISTING_FIELD_MAP` — no other code changes required.

## Status updates back to Host Tools

`mark_arrived(booking_id)` → `PATCH /reservations/{booking_id}` with body `{"status": "arrived"}`
`mark_checked_out(booking_id)` → `PATCH /reservations/{booking_id}` with body `{"status": "checked_out"}`

Both return `True` on success and raise on HTTP error. The integration calls these best-effort when the user manually presses the "Mark Guest Arrived" / "Mark Guest Departed" buttons — failures are logged but don't roll back the local lifecycle state.

## Datetime parsing

The provider tries these formats in order:

1. `%Y-%m-%dT%H:%M:%S.%fZ` — ISO-8601 with milliseconds, UTC Z
2. `%Y-%m-%dT%H:%M:%SZ` — ISO-8601, UTC Z
3. `%Y-%m-%dT%H:%M:%S%z` — ISO-8601 with offset
4. `%Y-%m-%d` — date only (treated as midnight UTC)

Naive datetimes (no tzinfo) are stamped UTC.

## Known quirks

- The `/reservations` endpoint requires the `listingId` query param. Without it you get every reservation across every listing.
- `property_name` in the returned `PropertyData` is currently set to `property_id` (Host Tools doesn't include the listing name in the reservation payload, and we'd need a second HTTP call to look it up). HA's device registry lets the user rename the device, so this is rarely user-visible.
- Bookings with missing `checkin`, `checkout`, or `booking_id` are silently skipped (logged at DEBUG). This guards against partial blocks / drafts in the calendar.

## Testing

See [`tests/providers/test_host_tools.py`](../../tests/providers/test_host_tools.py). Tests use `aioresponses` to mock the HTTP layer — no live token needed.

```bash
pytest tests/providers/test_host_tools.py -v
```
