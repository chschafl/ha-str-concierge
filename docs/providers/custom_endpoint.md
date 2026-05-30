# Custom Endpoint provider — API contract

Source: [`custom_components/str_concierge/providers/custom_endpoint.py`](../../custom_components/str_concierge/providers/custom_endpoint.py)

For hosts who run their own booking backend (or want to bridge from a PMS we don't support yet via a small adapter service). If you can expose three endpoints, STR Concierge will treat your backend as a first-class PMS.

## Auth

Bearer token on every request:

```
Authorization: Bearer <token>
```

The token and base URL are configured during the integration's setup flow.

## Endpoints

### `GET /properties`

Return all properties accessible with this token.

```json
[
  { "id": "string", "name": "string" }
]
```

### `GET /reservations?propertyId={id}`

Return current + upcoming bookings for one property. The integration filters and picks `current` / `next` itself based on check-in/out times.

```json
[
  {
    "id": "string",
    "guestName": "string",
    "checkIn": "2025-06-01T15:00:00Z",
    "checkOut": "2025-06-07T11:00:00Z",
    "doorCode": "string"
  }
]
```

### `POST /reservations/{id}/arrive`

Optional. Called when the user presses "Mark Guest Arrived" in HA.

```json
{ "ok": true }
```

### `POST /reservations/{id}/checkout`

Optional. Called when the user presses "Mark Guest Departed" in HA.

```json
{ "ok": true }
```

If you don't support these, return `404` or `405` and the integration treats them as no-ops (local state still latches correctly).

## Field aliases

The provider accepts multiple key names per field to make adapter writing easier:

| Field | Accepted keys |
|---|---|
| Property ID | `id` |
| Property name | `name` |
| Booking ID | `id` |
| Guest name | `guestName`, `guest_name`, `name` |
| Check-in | `checkIn`, `check_in`, `startDate`, `start_date` |
| Check-out | `checkOut`, `check_out`, `endDate`, `end_date` |
| Door code | `doorCode`, `door_code`, `accessCode`, `pin` |

## Minimum viable adapter

If you're bridging from an unsupported PMS, the smallest useful adapter is a single endpoint that returns whatever the PMS gave you, reshaped into the JSON above. A Flask / FastAPI app with three routes is enough.
