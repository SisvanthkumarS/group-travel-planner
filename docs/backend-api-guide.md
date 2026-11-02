# Backend API Integration Guide

Authentication, Trip Management, and Invitations · API version `0.1.0`

Last reviewed: November 2, 2026. This guide describes the implementation on branch
`KC`, including Redis-backed refresh sessions. Examples use fictional accounts and illustrative IDs and
timestamps; replace IDs with values returned by your own requests.

## 1. Connection and request conventions

| Item                              | Value                                                         |
| --------------------------------- | ------------------------------------------------------------- |
| Local API base URL                | `http://localhost:8000/api/v1`                                |
| Interactive Swagger documentation | `http://localhost:8000/docs`                                  |
| Live OpenAPI JSON                 | `http://localhost:8000/api/v1/openapi.json`                   |
| Repository OpenAPI specification  | [openapi.yaml](./openapi.yaml)                                |
| Request body                      | JSON with `Content-Type: application/json`                    |
| Response body                     | JSON, except successful `204` responses, which have no body   |
| Authentication                    | JWT in an HttpOnly cookie; default name: `access_token`       |
| Date format                       | Use `YYYY-MM-DD`, for example `2026-11-15`                    |
| Timestamp format                  | ISO 8601 with a timezone, for example `2026-10-29T14:00:00Z`  |
| IDs                               | Positive integer IDs returned by the API; send them unchanged |

All endpoint paths below are relative to the API base URL. Use the exact field
name `user_name`, not `username`. Enum values are case-sensitive uppercase strings.
List responses are plain arrays, without a `data`, `items`, or pagination wrapper.
The list endpoints currently do not support pagination or filtering parameters.

Do not send `current_user_id`, `organizer_id`, or `invited_by_user_id` to select
which user performs an action. The backend derives the acting user from the JWT
cookie. Unrecognized fields are currently ignored by the request models; do not
rely on them changing server behavior.

## 2. Browser authentication

Registration creates an account but does **not** log the user in. Call login
separately. Successful login returns the user object and sets an HttpOnly cookie;
it does **not** return an access token in the JSON body. Browser JavaScript cannot
read this cookie. Protected endpoints read the cookie, not an `Authorization:
Bearer ...` header.

Use `credentials: "include"` for login, logout, and protected requests when the
frontend and API use different origins. The default permitted frontend origin is
`http://localhost:5173`. Use `localhost` consistently for local development; an
origin such as `http://127.0.0.1:5173` needs its own CORS configuration.

Both credentials use HttpOnly cookies with `SameSite=Lax` and `Path=/` (so the
backend can renew sessions on business requests). `Secure=false` is the local
default; enable it for HTTPS deployment. Default cookie names and lifetimes:

| Cookie          | Format                               | Lifetime                                                  |
| --------------- | ------------------------------------ | --------------------------------------------------------- |
| `access_token`  | Signed JWT, `token_type=access`      | 30 minutes                                                |
| `refresh_token` | Random opaque credential (not a JWT) | 7-day sliding idle timeout; 30-day absolute session limit |

The filter automatically renews the cookies when access is missing, invalid,
expired, or within 60 seconds of expiry, provided the refresh session is valid.
Frontend code still only needs `credentials: "include"`; no token storage or
expiry timer is required. Renewal extends the Redis session's idle timeout and
refresh-cookie lifetime, capped at the original 30-day deadline. Passive time on
a page with no API requests does not renew a session.

`POST /auth/refresh` can also renew the cookies explicitly. A refresh credential
is stable within one browser session so parallel requests do not invalidate each
other. Redis stores its SHA-256 hash, user ID, and absolute deadline, not the raw
credential. Session expiry or logout prevents further refreshes. Both cookies and
all durations are configurable. On 401 after refresh expiry/revocation, ask the
user to log in again. On 503, show a temporary failure and allow retry; do not
interpret it as invalid credentials.

Redis is required for login and renewal. Valid access JWTs continue working during
a Redis outage, including when a proactive renewal fails. Logout revokes the
refresh session but does not blacklist a copied access JWT; it remains valid until
its own expiry. Cross-site deployments may require cookie and CORS settings beyond
the local defaults. Existing users must log in once after this upgrade to obtain
the new refresh cookie and typed access JWT.

### Browser request helper

```javascript
const API_BASE = 'http://localhost:8000/api/v1';

async function apiRequest(path, { method = 'GET', body } = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    ...(body !== undefined
      ? {
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      : {}),
  });

  // Logout and trip deletion return no JSON body.
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const error = new Error(`API request failed (${response.status})`);
    error.status = response.status;
    error.detail = payload?.detail; // A string OR a validation-error array.
    throw error;
  }
  return payload;
}

// Stores the cookie through the browser automatically.
await apiRequest('/auth/login', {
  method: 'POST',
  body: { user_name: 'KC', password: 'Example-password-2026' },
});
const trips = await apiRequest('/trips');
```

The helper assumes an HTTP response from the API; fetch can also throw for network
or CORS failures. Do not call `response.json()` on a successful `204` response.

## 3. Endpoint overview

| #   | Method | Path                           | Authentication / permission               | Success                          |
| --- | ------ | ------------------------------ | ----------------------------------------- | -------------------------------- |
| 1   | POST   | `/auth/register`               | Public                                    | `201`, user object               |
| 2   | POST   | `/auth/login`                  | Public                                    | `200`, user object + two cookies |
| 3   | POST   | `/auth/logout`                 | Public; cookie optional                   | `204`, no body                   |
| 4   | POST   | `/trips`                       | Logged-in user                            | `201`, trip object               |
| 5   | GET    | `/trips`                       | Logged-in user; own memberships only      | `200`, trip array                |
| 6   | GET    | `/trips/{trip_id}`             | Member of this trip                       | `200`, trip + members            |
| 7   | DELETE | `/trips/{trip_id}`             | Organizer of this trip                    | `204`, no body                   |
| 8   | POST   | `/trips/{trip_id}/invitations` | Organizer of this trip                    | `201`, invitation object         |
| 9   | GET    | `/invitations`                 | Logged-in user; received invitations only | `200`, invitation array          |
| 10  | PATCH  | `/invitations`                 | Recipient of the invitation               | `200`, updated invitation        |

Additional endpoint: **POST `/auth/refresh`**, authenticated by the refresh cookie;
returns `200` with the user object and renewed cookies, or `401` / `503`.

## 4. Authentication

### 4.1 Register an account

**`POST /auth/register`** · Public · Success: **201 Created**

#### Request fields

| Field       | JSON type | Required | Rules                                                                                    |
| ----------- | --------- | -------- | ---------------------------------------------------------------------------------------- |
| `user_name` | string    | Yes      | 1–30 characters after trimming surrounding whitespace; unique and case-sensitive         |
| `email`     | string    | Yes      | Valid email address; normalized to lowercase for storage; uniqueness is case-insensitive |
| `password`  | string    | Yes      | At least 1 character; submit the plaintext password, not a client-generated hash         |

Password hashing is performed by the backend. Passwords are not trimmed by the
backend; do not silently trim them in the client. The current API does not enforce
a stronger password-complexity rule. Email verification is not part of this sprint.

#### Request example

```json
{
  "user_name": "KC",
  "email": "kc@example.com",
  "password": "Example-password-2026"
}
```

#### Success response example

```json
{
  "user_name": "KC",
  "user_id": 7,
  "email": "kc@example.com",
  "created_at": "2026-10-29T14:00:00Z"
}
```

No password or password hash is returned. No login cookie is issued by registration.

#### Errors

| Status | `detail` / cause                                                                                    |
| ------ | --------------------------------------------------------------------------------------------------- |
| 409    | `Email is already registered.`                                                                      |
| 409    | `Username is already registered.`                                                                   |
| 422    | Missing/null required fields, invalid email, empty password, or username outside the allowed length |

### 4.2 Log in

**`POST /auth/login`** · Public · Success: **200 OK**

#### Request fields

| Field       | JSON type      | Required    | Rules                                                                        |
| ----------- | -------------- | ----------- | ---------------------------------------------------------------------------- |
| `email`     | string or null | Conditional | Valid email if supplied; omitted/null/blank means absent                     |
| `user_name` | string or null | Conditional | 1–30 characters when present; surrounding whitespace trimmed; case-sensitive |
| `password`  | string         | Yes         | At least 1 character; not trimmed                                            |

At least one of `email` and `user_name` must be present after normalization. If
both are present, **email takes precedence**. An unsuccessful email lookup does
not fall back to username. Each supplied nonblank identifier must still pass
validation, even if it will not be used for lookup.

#### Request example: email login

```json
{
  "email": "kc@example.com",
  "password": "Example-password-2026"
}
```

#### Request example: username login

```json
{
  "user_name": "KC",
  "email": null,
  "password": "Example-password-2026"
}
```

#### Success response example

```json
{
  "user_name": "KC",
  "user_id": 7,
  "email": "kc@example.com",
  "created_at": "2026-10-29T14:00:00Z"
}
```

The HTTP response also sets both the access and refresh cookies. The JSON body contains no
`access_token` field. Keep the returned user object as UI state if needed; cookie
handling is automatic when browser credentials are enabled.

#### Errors

| Status | `detail` / cause                                                                         |
| ------ | ---------------------------------------------------------------------------------------- |
| 401    | `Invalid login credentials.` — account not found or password incorrect                   |
| 422    | Neither identifier supplied, invalid supplied identifier, or missing/null/empty password |

### 4.3 Log out

**`POST /auth/logout`** · Public · Success: **204 No Content**

**Request:** No path parameters, query parameters, or body. Include browser
credentials so the matching cookie can be cleared.

**Success response:** Empty body. The response expires both authentication cookies and revokes this browser's Redis refresh session.
Calling logout without a refresh cookie or after revocation also returns 204. Clear the frontend's
cached user/session state after success. Logout removes the browser cookie; it
does not revoke an already issued access JWT server-side before its expiry.
If Redis revocation fails, logout still clears both cookies but returns 503; the
server-side refresh session may remain valid until its TTL. A retry with the
original refresh cookie is needed to confirm server-side revocation.

### 4.4 Refresh the session explicitly

**`POST /auth/refresh`** · Valid refresh cookie required · Success: **200 OK**

**Request:** No body or parameters. Send cookies with `credentials: "include"`.
The access token may be absent or expired.

```javascript
const user = await apiRequest('/auth/refresh', { method: 'POST' });
```

The response has the same user-object shape as login and registration:

```json
{
  "user_name": "KC",
  "user_id": 7,
  "email": "kc@example.com",
  "created_at": "2026-10-29T14:00:00Z"
}
```

Both cookies are set again; neither credential appears in the JSON body. Responses
that issue or clear authentication cookies include `Cache-Control: no-store`.
This endpoint is optional for ordinary API use because protected routes perform
renewal automatically, even on explicit 204 or business-error responses.

| Status | `detail` / cause                                                                                |
| ------ | ----------------------------------------------------------------------------------------------- |
| 401    | `Invalid or expired refresh token.` — missing, invalid, expired, or revoked session             |
| 401    | `Authentication required.` — account no longer exists                                           |
| 503    | `Authentication service temporarily unavailable. Please retry.` — Redis error; `Retry-After: 5` |

Login can also return this 503 error; a failed login does not issue new cookies.
Protected endpoints can return 503 if access has expired and Redis renewal is
unavailable. Do not redirect to login solely because of a 503 response.

## 5. Trip Management

### 5.1 Create a trip

**`POST /trips`** · Authentication required · Success: **201 Created**

#### Request fields

| Field         | JSON type | Required | Rules                                                           |
| ------------- | --------- | -------- | --------------------------------------------------------------- |
| `name`        | string    | Yes      | Surrounding whitespace trimmed; must not be blank               |
| `destination` | string    | Yes      | Surrounding whitespace trimmed; must not be blank               |
| `start_date`  | string    | Yes      | Valid date; send `YYYY-MM-DD`                                   |
| `end_date`    | string    | Yes      | Valid date; send `YYYY-MM-DD`; must be on or after `start_date` |

Same-day trips are allowed. No future-date restriction is currently implemented.
Do not submit `organizer_id` or an initial member list. The logged-in user becomes
the Organizer and is added to `trip_members` automatically.

#### Request example

```json
{
  "name": "NYC Weekend",
  "destination": "New York City",
  "start_date": "2026-11-15",
  "end_date": "2026-11-17"
}
```

#### Success response example

```json
{
  "trip_id": 12,
  "name": "NYC Weekend",
  "destination": "New York City",
  "start_date": "2026-11-15",
  "end_date": "2026-11-17",
  "organizer_id": 7
}
```

**Errors:** 401 for missing/invalid authentication; 422 for missing/invalid input
or `start_date` later than `end_date`. Trip creation and Organizer membership are
saved together; this response does not include a `members` field.

### 5.2 List my trips

**`GET /trips`** · Authentication required · Success: **200 OK**

**Request:** No path parameters, supported query parameters, or body. Do not pass
a user ID. The backend returns trips where the logged-in user has a membership,
as either Organizer or Member. A pending invitation does not grant membership.

Results are ordered by `start_date` ascending, then `trip_id` ascending.

#### Success response example

```json
[
  {
    "trip_id": 12,
    "name": "NYC Weekend",
    "destination": "New York City",
    "start_date": "2026-11-15",
    "end_date": "2026-11-17",
    "organizer_id": 7
  }
]
```

With no accessible trips, the response is `200` with `[]`. Each item has the same
fields as the create-trip response; the list does not contain member details.

**Errors:** 401 for missing/invalid authentication.

### 5.3 Get trip details and members

**`GET /trips/{trip_id}`** · Trip membership required · Success: **200 OK**

| Input     | Location | Type    | Rules                                       |
| --------- | -------- | ------- | ------------------------------------------- |
| `trip_id` | URL path | integer | Positive existing trip ID, e.g. `/trips/12` |

**Request:** No body or supported query parameters. The user must already be an
Organizer or Member; simply receiving an invitation is insufficient.

#### Success response example

```json
{
  "trip_id": 12,
  "name": "NYC Weekend",
  "destination": "New York City",
  "start_date": "2026-11-15",
  "end_date": "2026-11-17",
  "organizer_id": 7,
  "members": [
    {
      "user_id": 7,
      "user_name": "KC",
      "role": "ORGANIZER",
      "joined_at": "2026-10-29T14:05:00Z"
    },
    {
      "user_id": 8,
      "user_name": "Alex",
      "role": "MEMBER",
      "joined_at": "2026-10-29T14:20:00Z"
    }
  ]
}
```

Trip fields are at the top level, not inside a nested `trip` object. `members`
includes the Organizer and is ordered by `joined_at` ascending, then `user_id`
ascending. Member records do not include email addresses.

#### Errors

| Status | `detail` / cause                                             |
| ------ | ------------------------------------------------------------ |
| 401    | Missing/invalid authentication                               |
| 403    | `Trip membership required.`                                  |
| 404    | `Trip not found.`                                            |
| 422    | Invalid path parameter, such as `trip_id=0` or a non-integer |

### 5.4 Delete a trip

**`DELETE /trips/{trip_id}`** · Organizer only · Success: **204 No Content**

**Path input:** Positive integer `trip_id`, e.g. `DELETE /trips/12`.
**Body/query input:** None.

**Success response:** Empty body. The trip and its related memberships and
invitations are deleted through database cascades. Remove the trip from frontend
state after success. Do not attempt to parse a JSON response. A second deletion
of the same trip returns 404.

#### Errors

| Status | `detail` / cause                           |
| ------ | ------------------------------------------ |
| 401    | Missing/invalid authentication             |
| 403    | `Only the Organizer can delete this trip.` |
| 404    | `Trip not found.`                          |
| 422    | Invalid path parameter                     |

## 6. Invitations

### 6.1 Invite a registered user

**`POST /trips/{trip_id}/invitations`** · Organizer only · Success: **201 Created**

**Path input:** Positive integer `trip_id`, e.g. `/trips/12/invitations`.

#### JSON request fields

| Field       | JSON type      | Required    | Rules                                                                                  |
| ----------- | -------------- | ----------- | -------------------------------------------------------------------------------------- |
| `email`     | string or null | Conditional | Valid email; case-insensitive lookup; omitted/null/blank means absent                  |
| `user_name` | string or null | Conditional | 1–30 characters after trimming; case-sensitive lookup; omitted/null/blank means absent |

At least one identifier is required. If both are supplied, email takes precedence,
with no username fallback if email lookup fails. Any supplied nonblank identifier
must pass validation. The recipient must already have an account. This endpoint
creates an in-app invitation; it does not send an email or create a new account.

#### Request example: by email

```json
{
  "email": "alex@example.com"
}
```

#### Request example: by username

```json
{
  "user_name": "Alex"
}
```

#### Success response example

```json
{
  "invitation_id": 25,
  "trip_id": 12,
  "invited_user_id": 8,
  "invited_by_user_id": 7,
  "status": "PENDING",
  "created_at": "2026-10-29T14:10:00Z",
  "responded_at": null
}
```

Creation does not add the recipient as a trip member. Only one `PENDING`
invitation can exist for the same trip and recipient. A previous `DECLINED`
invitation does not prevent another invitation. Capacity is checked on acceptance,
not on creation; an invitation may be created even when the trip is full.

#### Errors

| Status | `detail` / cause                                                              |
| ------ | ----------------------------------------------------------------------------- |
| 401    | Missing/invalid authentication                                                |
| 403    | `Only the Organizer can invite users to this trip.`                           |
| 404    | `Trip not found.`                                                             |
| 404    | `Registered recipient not found.`                                             |
| 409    | `You cannot invite yourself.`                                                 |
| 409    | `User is already a member of this trip.`                                      |
| 409    | `An invitation is already pending for this user and trip.`                    |
| 422    | Invalid trip ID, missing both identifiers, invalid email, or invalid username |

### 6.2 List received invitations

**`GET /invitations`** · Authentication required · Success: **200 OK**

**Request:** No body, path input, or supported query parameters. The JWT determines
whose inbox is returned. Passing a `user_id` query parameter does not select
another user's inbox.

Returns invitations **received** by the current user (`invited_user_id`), not all
invitations they sent. Includes `PENDING`, `ACCEPTED`, and `DECLINED` history.
Results are ordered by `created_at` descending, then `invitation_id` descending.

#### Success response example

```json
[
  {
    "invitation_id": 25,
    "trip_id": 12,
    "invited_user_id": 8,
    "invited_by_user_id": 7,
    "status": "PENDING",
    "created_at": "2026-10-29T14:10:00Z",
    "responded_at": null
  },
  {
    "invitation_id": 24,
    "trip_id": 13,
    "invited_user_id": 8,
    "invited_by_user_id": 9,
    "status": "ACCEPTED",
    "created_at": "2026-10-28T14:10:00Z",
    "responded_at": "2026-10-28T14:20:00Z"
  },
  {
    "invitation_id": 23,
    "trip_id": 14,
    "invited_user_id": 8,
    "invited_by_user_id": 10,
    "status": "DECLINED",
    "created_at": "2026-10-27T14:10:00Z",
    "responded_at": "2026-10-27T14:20:00Z"
  }
]
```

An empty inbox returns `200` with `[]`. Invitation objects contain IDs, not trip
names, destinations, inviter names, or email addresses. A pending recipient cannot
use the member-only trip-details endpoint to enrich a pending invitation. The
current API does not provide a public trip preview or user-profile lookup; plan
inbox UI around these fields or coordinate an API extension with the backend.

**Errors:** 401 for missing/invalid authentication.

### 6.3 Accept or decline an invitation

**`PATCH /invitations`** · Recipient only · Success: **200 OK**

The invitation ID goes in the JSON body, not in the URL. The route is
`/invitations`, not `/invitations/{invitation_id}`.

| Field           | JSON type | Required | Rules                             |
| --------------- | --------- | -------- | --------------------------------- |
| `invitation_id` | integer   | Yes      | Positive existing invitation ID   |
| `decision`      | string    | Yes      | Exactly `"ACCEPT"` or `"DECLINE"` |

#### Request example: accept

```json
{
  "invitation_id": 25,
  "decision": "ACCEPT"
}
```

#### Success response example: accepted

```json
{
  "invitation_id": 25,
  "trip_id": 12,
  "invited_user_id": 8,
  "invited_by_user_id": 7,
  "status": "ACCEPTED",
  "created_at": "2026-10-29T14:10:00Z",
  "responded_at": "2026-10-29T14:20:00Z"
}
```

Acceptance adds the current user as a `MEMBER` and updates the invitation in one
transaction. The trip may have at most **8 members including the Organizer**.
Concurrent acceptances cannot claim the same last place. After success, refresh
`GET /invitations` and `GET /trips`; the user can now access `GET /trips/{trip_id}`.

#### Request example: decline

```json
{
  "invitation_id": 25,
  "decision": "DECLINE"
}
```

#### Success response example: declined

```json
{
  "invitation_id": 25,
  "trip_id": 12,
  "invited_user_id": 8,
  "invited_by_user_id": 7,
  "status": "DECLINED",
  "created_at": "2026-10-29T14:10:00Z",
  "responded_at": "2026-10-29T14:20:00Z"
}
```

Accept and decline examples are alternative outcomes of the same pending
invitation, not sequential calls. Declining does not add a membership and is
allowed even if the trip is full. An invitation can be answered only once;
repeating a response, even the same decision, returns 409. A failed acceptance
does not consume the invitation: its status stays `PENDING`.

#### Errors

| Status | `detail` / cause                                                                                             |
| ------ | ------------------------------------------------------------------------------------------------------------ |
| 401    | Missing/invalid authentication                                                                               |
| 403    | `Only the recipient can respond.`                                                                            |
| 404    | `Invitation not found.`                                                                                      |
| 404    | `Trip not found.`                                                                                            |
| 409    | `Invitation has already been answered.`                                                                      |
| 409    | `User is already a member of this trip.` — acceptance only                                                   |
| 409    | `Trip is full (maximum 8 members).` — acceptance only                                                        |
| 422    | Missing/invalid ID or decision; `"ACCEPTED"`, `"DECLINED"`, and lowercase actions are invalid request values |

## 7. Response field reference

### User object

| Field        | JSON type | Meaning                         |
| ------------ | --------- | ------------------------------- |
| `user_name`  | string    | Unique, case-sensitive username |
| `user_id`    | integer   | Account ID                      |
| `email`      | string    | Stored account email            |
| `created_at` | string    | Account creation timestamp      |

### Trip object

| Field          | JSON type | Meaning                                                                                   |
| -------------- | --------- | ----------------------------------------------------------------------------------------- |
| `trip_id`      | integer   | Trip ID                                                                                   |
| `name`         | string    | Trip name                                                                                 |
| `destination`  | string    | Destination text                                                                          |
| `start_date`   | string    | Start date (`YYYY-MM-DD`)                                                                 |
| `end_date`     | string    | End date (`YYYY-MM-DD`)                                                                   |
| `organizer_id` | integer   | Organizer's user ID                                                                       |
| `members`      | array     | Only on trip-details responses; each item has `user_id`, `user_name`, `role`, `joined_at` |

Membership `role` is `"ORGANIZER"` or `"MEMBER"`. The create/list trip responses do
not contain a separate current-user role; compare `organizer_id` with the logged-in
user's `user_id` to decide whether to display Organizer controls. The backend
still enforces permissions independently of the UI.

### Invitation object

| Field                | JSON type      | Meaning                                     |
| -------------------- | -------------- | ------------------------------------------- |
| `invitation_id`      | integer        | Invitation ID used when responding          |
| `trip_id`            | integer        | Target trip ID                              |
| `invited_user_id`    | integer        | Recipient's user ID                         |
| `invited_by_user_id` | integer        | Sender's user ID                            |
| `status`             | string         | `"PENDING"`, `"ACCEPTED"`, or `"DECLINED"`  |
| `created_at`         | string         | Invitation creation timestamp               |
| `responded_at`       | string or null | Response timestamp; null only while pending |

## 8. Error format and frontend handling

### Business and authentication errors

Expected business errors use an HTTP error status and a JSON body like:

```json
{
  "detail": "An invitation is already pending for this user and trip."
}
```

Protected endpoints may return these authentication messages:

| Status | `detail`                           | Meaning                                                        |
| ------ | ---------------------------------- | -------------------------------------------------------------- |
| 401    | `Authentication required.`         | Cookie absent, or token refers to a user that no longer exists |
| 401    | `Invalid or expired access token.` | Token invalid or expired                                       |

Use HTTP status codes for control flow. Display or map the detail message as
needed; there are currently no separate machine-readable application error codes.
There is no success/error envelope such as `{ "code": 200, "data": ... }`.

### Validation errors: 422

FastAPI validation errors have a `detail` **array**, rather than a string. For
example, requesting `GET /trips/0` with a valid login produces:

```json
{
  "detail": [
    {
      "type": "greater_than",
      "loc": ["path", "trip_id"],
      "msg": "Input should be greater than 0",
      "input": 0,
      "ctx": { "gt": 0 }
    }
  ]
}
```

`loc` identifies the input source and field. A body-field error uses a location
such as `["body", "email"]`; a whole-body validation rule (for example, both login
identifiers missing) may use `["body"]`. Validation messages and auxiliary fields
vary by error. Support both string and array forms of `detail` in the frontend.
Protected routes may reject an unauthenticated request with 401 before reporting
body validation errors. Unexpected server failures may return 500 without the
JSON error shape above; treat them as general failures.

## 9. Suggested integration sequence

1. Register the Organizer and invitee as separate accounts. Registration does not log either user in.
2. Log in as the Organizer and create a trip. Store the returned `trip_id`.
3. Create an invitation using the invitee's email or username. Store the returned `invitation_id`.
4. In another browser profile, log in as the invitee and load `GET /invitations`.
5. Submit `PATCH /invitations` with `decision: "ACCEPT"` and the invitation ID.
6. Reload the invitee's trips, then retrieve trip details to confirm membership.
7. As the Organizer, retrieve trip details to show the updated member list.

Separate browser profiles are useful when testing two accounts: tabs in the same
profile share the login cookie, so signing in as the invitee also changes the
session used by other tabs for the same API host.
