# Custom Endpoint provider — implementation notes

Source: [`custom_components/str_concierge/providers/custom_endpoint.py`](../../custom_components/str_concierge/providers/custom_endpoint.py)

This is the "I run my own booking backend" provider. It points STR Concierge at a REST API you control. The full wire-level contract — what to build on the backend so this provider talks to it — lives in [`backend-api-spec.md`](backend-api-spec.md). Read that doc if you're implementing the backend; this one only covers how the integration uses it.

## Auth

Bearer token on every request:

```
Authorization: Bearer <token>
```

The token and base URL are entered during the integration's setup flow.

## Endpoints used

| Method | Path | When the integration calls it |
|---|---|---|
| `GET` | `/properties` | Config flow, to populate the property dropdown |
| `GET` | `/properties/{propertyId}/reservations` | Every poll (default 5 minutes) |
| `POST` | `/properties/{propertyId}/reservations/{reservationId}/arrive` | When the user presses **Mark Guest Arrived** (best-effort, failures are logged but don't roll back local state) |
| `POST` | `/properties/{propertyId}/reservations/{reservationId}/checkout` | When the user presses **Mark Guest Departed** (best-effort) |

The integration uses one property per config entry — when a user picks "My Villa" during setup, the provider scopes all subsequent calls to that property's ID.

## Field aliases

The provider accepts multiple key names per field so adapter writers can match whatever shape their PMS already gives them:

| Field | Accepted keys (first match wins) |
|---|---|
| Property ID | `id` |
| Property name | `name` |
| Booking ID | `id` |
| Guest name | `guestName`, `guest_name`, `name` |
| Check-in | `checkIn`, `check_in`, `startDate`, `start_date` |
| Check-out | `checkOut`, `check_out`, `endDate`, `end_date` |
| Door code | `doorCode`, `door_code`, `accessCode`, `pin` |

The integration ignores any other fields in the payload — feel free to include them for your own use.

## See also

- [backend-api-spec.md](backend-api-spec.md) — the standalone API specification, written so it can be handed to another agent (or another developer) and implemented end-to-end without reading any other doc.
