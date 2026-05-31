# STR Concierge — Custom Backend API Specification

**Status:** stable
**Audience:** anyone (human or AI agent) implementing a backend that STR Concierge's "Custom Endpoint" provider can talk to.
**Goal:** a single, complete document. You should be able to read only this file and ship a working backend.

---

## 1. Overview

You are building a REST API. STR Concierge (a Home Assistant integration that surfaces short-term-rental bookings as HA entities) will poll this API every few minutes to learn:

- which properties (listings) the connected account owns
- which guest is currently in each property and who's coming next
- whether a guest has been manually marked as arrived or checked out

You expose four endpoints. JSON in, JSON out. Bearer token auth. No state of your own beyond what your booking system already tracks.

---

## 2. Conventions

### Base URL

The integration concatenates each endpoint path to a base URL the user configures, e.g. `https://my-bookings.example.com/api`. All paths in this spec are relative to that base.

### Authentication

Every request — including `GET`s — carries:

```
Authorization: Bearer <token>
```

The token is opaque to the integration. You issue it however you like (one-time generation in your dashboard, periodic rotation, etc.). The integration sends the same token verbatim on every request.

Recommended behaviour:

- `200` when the token is valid and the request succeeds
- `401 Unauthorized` for missing or invalid token. The integration treats this as a credential error and shows the user "cannot connect" in the UI.
- `403 Forbidden` if the token is valid but the property/reservation doesn't belong to this account.

### Content types

- Requests with bodies: `Content-Type: application/json`
- All responses: `Content-Type: application/json` with a UTF-8 body
- The integration always sends `Accept: application/json`

### Dates and times

All timestamp fields are **ISO-8601 strings**. The integration accepts any of:

- `2026-06-01T15:00:00.000Z` (with milliseconds, UTC)
- `2026-06-01T15:00:00Z` (UTC)
- `2026-06-01T15:00:00+02:00` (with offset)
- `2026-06-01` (date only — interpreted as midnight UTC)

Pick one shape and be consistent. The integration normalises everything to UTC internally.

### Identifiers

`propertyId` and `reservationId` are opaque strings — they can be anything URL-safe (UUIDs, slugs, integer-stringified, your booking ID, your PMS confirmation code). They MUST be stable: once the integration sees a `reservationId`, that ID must continue to refer to the same booking for its lifetime. The integration uses the IDs to detect when bookings rotate.

### Errors

For any error response, prefer this shape:

```json
{
  "error": "Descriptive message, safe to log"
}
```

Use sensible HTTP status codes (`401`, `403`, `404`, `429`, `5xx`). The integration logs the status and body at DEBUG level; users only see "cannot connect" in the config flow.

---

## 3. Endpoints

There are four. Order in this section matches the order in which the integration calls them.

### 3.1 `GET /properties`

**Called by:** the config flow, exactly once per setup, to populate the "which property?" dropdown the user sees during integration setup.

**Request**

```
GET /properties HTTP/1.1
Authorization: Bearer <token>
Accept: application/json
```

No query parameters, no body.

**Response — 200 OK**

A JSON array of property objects. The integration also accepts a wrapped envelope (`{ "properties": [...] }` or `{ "data": [...] }`) but a raw array is simplest.

```json
[
  {
    "id": "villa-amalfi",
    "name": "Villa Amalfi"
  },
  {
    "id": "loft-soho",
    "name": "Soho Loft"
  }
]
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Opaque, stable property identifier. Used in every subsequent URL path. |
| `name` | string | yes | Human-readable property name. Shown to the user in the dropdown and as the HA device name. |

You may include other fields; the integration ignores them.

**Errors**

- `401` — token invalid → config flow shows "Cannot connect"
- `403` — token valid but no properties visible → effectively an empty array; the config flow shows "No properties were found for this account"
- `200` with `[]` → same result as `403`

---

### 3.2 `GET /properties/{propertyId}/reservations`

**Called by:** the integration's coordinator, every poll interval (default: 5 minutes; user-configurable 60–3600 seconds).

This is the main loop. Return reservations for the property so the integration can decide who's `current` and who's `next`.

**Request**

```
GET /properties/villa-amalfi/reservations HTTP/1.1
Authorization: Bearer <token>
Accept: application/json
```

No query parameters required. The integration filters the response itself — return what you have.

**Recommended scope**

Return reservations whose `[checkIn, checkOut]` window overlaps **today + the next ~30 days at minimum**. Returning the entire historical list works but is wasteful. The integration's "vacancy threshold" defaults to 30 days, so anything further out is ignored anyway.

**Response — 200 OK**

```json
[
  {
    "id": "res-001",
    "guestName": "Alice Smith",
    "checkIn": "2026-06-01T15:00:00Z",
    "checkOut": "2026-06-07T11:00:00Z",
    "doorCode": "1234",
    "status": "confirmed"
  },
  {
    "id": "res-002",
    "guestName": "Bob Jones",
    "checkIn": "2026-06-08T15:00:00Z",
    "checkOut": "2026-06-10T11:00:00Z",
    "doorCode": "5678",
    "status": "confirmed"
  }
]
```

Wrapped envelopes are also accepted (`{ "reservations": [...] }`, `{ "data": [...] }`).

**Fields**

The integration accepts several aliases per field so you can match whatever shape your PMS already uses. The **first listed alias is the canonical form** — please use it unless you have a strong reason not to.

| Logical field | Canonical key | Other accepted keys | Type | Required | Notes |
|---|---|---|---|---|---|
| Booking ID | `id` | — | string | **yes** | Stable opaque identifier. The integration uses it to detect when a booking rotates. |
| Guest name | `guestName` | `guest_name`, `name` | string | **yes** | Display name. Use a single combined string ("Firstname Lastname"). |
| Check-in | `checkIn` | `check_in`, `startDate`, `start_date` | ISO-8601 string | **yes** | When the reservation starts. |
| Check-out | `checkOut` | `check_out`, `endDate`, `end_date` | ISO-8601 string | **yes** | When the reservation ends. |
| Door code | `doorCode` | `door_code`, `accessCode`, `pin` | string | no | If present, the integration writes it to the door-lock automations. Omit or send `null` if you don't issue codes. |
| Status | `status` | — | string | no | One of `confirmed`, `pending`, `arrived`, `checked_out`, `cancelled`. See below. Defaults to `confirmed` if absent. |

#### Status values

| Value | Meaning | What STR Concierge does with it |
|---|---|---|
| `confirmed` | Booking is firm | Treat as a real reservation (default if status field is omitted) |
| `pending` | Booking is provisional | Treat as a real reservation — host probably wants visibility |
| `arrived` | Guest has been marked arrived in the PMS | Treat as a real reservation. The integration manages its own `in_house` state via the local lock event, so this is informational only. |
| `checked_out` | Guest has been marked checked-out in the PMS | Treat as a real reservation while the dates still cover "now" — the integration's local courtesy window decides when to flip to `departed`. |
| `cancelled` | Booking is voided | **Omit from the response.** The integration has no concept of cancelled bookings; just don't return them. |

Anything not listed here is treated as "confirmed".

#### What if I have no reservations?

Return `200 OK` with `[]`. Don't 404. The integration logs "no current/next guest" and waits for the next poll.

**Errors**

- `401` — token invalid → coordinator logs error, sensors go `unavailable`
- `404` — property ID unknown → same effect as `401`
- `429` — rate-limited → coordinator backs off and retries on the next poll
- `5xx` — transient → coordinator backs off and retries

---

### 3.3 `POST /properties/{propertyId}/reservations/{reservationId}/arrive`

**Called by:** the integration, when the user presses the **Mark Guest Arrived** button in HA, OR when a configured door-lock event fires inside the booking's lock-access window.

This is best-effort. The integration's own state (`entered_at`) is the source of truth for `in_house` status — this POST is just so your PMS stays in sync if it supports the concept. If you don't, return 200 anyway and ignore.

**Request**

```
POST /properties/villa-amalfi/reservations/res-001/arrive HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

(no body)
```

**Response — 200 OK**

```json
{ "ok": true }
```

The integration doesn't read the body. Any 2xx response is treated as success.

**Errors**

The integration logs failures at DEBUG and continues. Returning `404 Not Found` if the reservation ID doesn't exist is fine. Returning `409 Conflict` if the reservation is already marked arrived is also fine.

---

### 3.4 `POST /properties/{propertyId}/reservations/{reservationId}/checkout`

**Called by:** the integration, when the user presses the **Mark Guest Departed** button.

Same shape and semantics as the `/arrive` endpoint above.

**Request**

```
POST /properties/villa-amalfi/reservations/res-001/checkout HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

(no body)
```

**Response — 200 OK**

```json
{ "ok": true }
```

---

## 4. Worked example

A user with one property and two upcoming bookings:

```
GET /properties
→ 200
[ { "id": "villa-amalfi", "name": "Villa Amalfi" } ]

GET /properties/villa-amalfi/reservations
→ 200
[
  {
    "id": "res-001",
    "guestName": "Alice Smith",
    "checkIn": "2026-06-01T15:00:00Z",
    "checkOut": "2026-06-07T11:00:00Z",
    "doorCode": "1234",
    "status": "confirmed"
  },
  {
    "id": "res-002",
    "guestName": "Bob Jones",
    "checkIn": "2026-06-08T15:00:00Z",
    "checkOut": "2026-06-10T11:00:00Z",
    "doorCode": "5678",
    "status": "confirmed"
  }
]

POST /properties/villa-amalfi/reservations/res-001/arrive
→ 200
{ "ok": true }

POST /properties/villa-amalfi/reservations/res-001/checkout
→ 200
{ "ok": true }
```

That's the entire wire conversation. The integration handles everything else (vacancy threshold, arrival window, lock latching, `departed` dwell, house-cleaning state) locally.

---

## 5. Implementation tips

These aren't required, but they make the integration behave well:

- **Be fast.** The poll runs in the user's HA event loop. Keep `GET /properties/{id}/reservations` under 1 second if you can.
- **Cache aggressively.** Most polls return identical data. ETags / `If-None-Match` are fine; the integration ignores them today but won't break if you send them, and they reduce your own load.
- **Don't return cancelled reservations.** The integration has no `cancelled` state — surfacing one will just look like a "real" booking until you remove it.
- **Stable IDs matter.** Don't regenerate `id` on every export. The integration uses the ID transition to detect "the booking rotated" and to fire events that user automations may depend on.
- **One property per booking entry.** If a single reservation spans multiple properties (rare), split it into N reservations, one per property.
- **Door codes are sensitive.** Treat the token like a secret; consider scoping it to a single property if your auth model supports it.

---

## 6. Quick conformance checklist

Before shipping your backend, verify:

- [ ] `GET /properties` returns 200 with a JSON array, each item having a string `id` and `name`
- [ ] `GET /properties/{id}/reservations` returns 200 with a JSON array, each item having string `id`, `guestName`, and ISO-8601 `checkIn` / `checkOut`
- [ ] `POST /properties/{id}/reservations/{rid}/arrive` returns any 2xx (`{ "ok": true }` is conventional)
- [ ] `POST /properties/{id}/reservations/{rid}/checkout` returns any 2xx
- [ ] Missing/invalid token → 401
- [ ] Property ID unknown → 404
- [ ] Cancelled bookings are NOT in the response
- [ ] Same booking always returns the same `id` across polls
- [ ] All datetime fields are ISO-8601
- [ ] Empty calendar → `200 OK` with `[]`, never `404`

If everything in that list is true, the integration will work.

---

## 7. Changelog

- **2026-05-31** — Initial published spec. Reservations endpoint moved from `/reservations?propertyId={id}` (legacy) to `/properties/{propertyId}/reservations` (current). The arrive/checkout endpoints moved from `/reservations/{id}/arrive` to `/properties/{propertyId}/reservations/{reservationId}/arrive` for symmetry.
