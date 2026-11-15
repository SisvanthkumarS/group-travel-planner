# Architecture

The React SPA uses React Router for navigation, a typed fetch wrapper for API
requests, and an in-memory authentication context. The context is a placeholder
for a future login flow; it does not authenticate users. No token persists across
reloads. The frontend authentication context has not yet been wired to the backend's JWT cookie flow.

FastAPI hosts the app and documentation under `/api/v1`. `AuthController.py`
delegates registration and login to `AuthService`. Login accepts email or username,
preferring email when both are supplied. Usernames are case-sensitive, unique,
and limited to 1–30 trimmed characters. Registration checks availability; database
unique indexes also prevent concurrent duplicates. Passwords are hashed on the
server. Invalid credentials return 401; invalid input returns 422.

Login returns the user DTO and sets two HttpOnly, SameSite=Lax, Path=/ cookies:
an access JWT with `sub`, `iat`, `exp`, and `token_type=access`, and an opaque random
refresh credential. Redis stores a SHA-256 hash as the key, plus the user ID and
absolute session deadline. Defaults are 30-minute access, 7-day refresh idle
timeout, and 30-day absolute session lifetime. Renewal slides the idle TTL without
extending the absolute deadline. Cookies are Secure when JWT_COOKIE_SECURE=true.

`require_authentication` validates access and loads its user. Missing, invalid,
or expired access can be replaced using the refresh session. Near-expiry access
is renewed proactively. Redis WATCH/MULTI prevents a renewal from recreating a
concurrently deleted session. The refresh credential stays stable within a browser
session so parallel requests cannot invalidate each other. The cookie middleware
attaches renewals even to explicit 204 and business-error responses. Public auth
routes skip automatic renewal; POST `/auth/refresh` validates its own refresh cookie.

Logout deletes the current Redis session and clears both cookies. A copied access
JWT remains valid until expiry; it is not blacklisted. Redis failures return 503
for login or required refresh, but do not reject a still-valid access JWT. Logout
clears cookies on Redis failure and returns 503 to report unconfirmed revocation.
Users must log in once after upgrading to obtain both new credentials. Tokens are
never returned in JSON. Cookie responses include Cache-Control: no-store.

Trip Management exposes authenticated create, list, detail, and delete routes at
`/api/v1/trips`. Creation inserts the trip and Organizer membership, then commits
both together; failures roll back both writes. Details return the trip fields and
all members after verifying membership: absent trips return 404 and non-members
receive 403. Member responses include names, roles, and join times, without
passwords or email addresses. Listing returns only trips the user belongs to,
ordered by start date and trip ID, or an empty list when there are no memberships.
Deletion requires the Organizer, returns 404 for absent trips and 403 for other
users, and commits the trip deletion and cascaded member/invitation deletion
atomically. A successful deletion returns 204 with no body. Controllers delegate with the authenticated user ID; the
client cannot choose its own Organizer identity. Request DTOs validate nonblank
names/destinations and date order. Detail queries do not flush or commit the Session.
The authentication lookup already starts the shared Session transaction, so write
services should finish it with commit/rollback rather than calling begin again.

`InvitationController` exposes POST `/trips/{trip_id}/invitations`, GET
`/invitations`, and PATCH `/invitations` under `/api/v1`. Creation, listing, and responses are implemented and require authentication. Creation accepts the registered recipient's `email` or
`user_name` (1–30 characters, case-sensitive); blank identifiers become absent and
at least one is required. Lookup prefers email if both are provided and never
falls back to username after a failed email lookup. Responses
accept an `invitation_id` and `decision` (`ACCEPT` / `DECLINE`). Stored states remain
`PENDING`, `ACCEPTED`, and `DECLINED`. Creation locks the trip, requires the Organizer,
rejects self-invites, existing members and pending duplicates, and commits once.
The pending unique index also maps concurrent duplicate conflicts to HTTP 409.
Failures roll back the transaction. Only the recipient can respond to a pending
invitation; already answered invitations return HTTP 409.
`InvitationRepository` owns invitation queries; `TripInvitationRepository` implements
trip locking and member counts. Responses lock the trip first, then lock and
refresh the invitation. Acceptance checks membership and the eight-person limit
(including the Organizer), then commits the MEMBER row and ACCEPTED status in one
transaction. Declining records DECLINED without adding membership, even if the trip
is full. Both decisions record a UTC responded_at; failures roll back all changes. Listing filters by the
authenticated recipient's `invited_user_id`, includes all invitation states, and
orders by `created_at DESC, invitation_id DESC`. It returns an empty list when
there are no invitations and does not flush or commit.

| Layer        | Responsibility                                             |
| ------------ | ---------------------------------------------------------- |
| Controllers  | HTTP input validation, dependencies, response mapping      |
| Services     | Business rules and transaction boundaries                  |
| Repositories | Queries and persistence through injected database sessions |
| Models       | SQLAlchemy entities and shared metadata                    |

Dependencies point from controllers to services to repositories to models.
Database sessions are scoped with `get_session`; future services explicitly own
commits and rollbacks. Connections are opened lazily, so importing the app and
generating OpenAPI requires no database.

PostgreSQL is the database. Alembic owns schema evolution; revision `0002` creates
users, trips, trip memberships, and invitations. The database enforces uniqueness,
valid dates and invitation states, foreign keys, and cascade deletion. Services
must still enforce authorization, the eight-member limit under concurrency, and
atomic creation of a trip and its organizer membership. Compose waits for the database health check, applies migrations in a
one-shot service, and starts the API after successful migration. Backend health
checks read the generated schema; they confirm HTTP availability, not database
readiness. Frontend health checks read its index page.

`ActivityController` exposes proposal submission/listing/withdrawal, poll opening,
voting/tie resolution, and itinerary retrieval/cancellation. `ActivityService`
enforces the requirements in US-07 through US-10 and US-13 through US-16;
`ActivityRepository` owns persistence. Revision `0006` adds proposals, polls,
eligible voter snapshots, current votes, vote history, and itinerary items.
Proposal submission requires a description and non-negative estimated cost.
The activity start must be in the future, its end must follow its start, and both
must fall within the trip dates in the trip's IANA timezone (for example,
`America/New_York`). Trip creation requires a valid `timezone`; trip create, list,
and detail responses include it. Activity timestamps must include an offset, and
the backend converts them to the trip timezone to validate local calendar dates.
Timestamps are still stored as UTC instants; future-time checks, poll deadlines,
and itinerary ordering compare instants, including across daylight-saving changes.
Migration `0007` adds the timezone column and assigns `America/New_York` to existing
trips, as agreed for the legacy data. Existing trips in other zones must have their
intended timezone assigned explicitly; it cannot be inferred reliably from destinations. Clients
must send the trip's timezone when creating trips and use it when displaying times.
The 100-proposal limit includes withdrawn, rejected, and canceled proposals.

Opening a poll snapshots all current trip participants, including the organizer
and author. Its deadline must be after now and before the activity starts. There
is one current vote per eligible participant; changed choices append history,
while an identical PUT retry has no additional effect. New members cannot vote in
polls already open. Voting and withdrawal stop at the deadline even before the
scheduler processes it. Only the author can withdraw PENDING/OPEN proposals;
withdrawal cancels an open poll without producing an outcome.

The FastAPI lifespan runs an internal poll scheduler every five seconds by default.
`POLL_SCHEDULER_ENABLED` and `POLL_SCHEDULER_INTERVAL_SECONDS` configure it. Overdue
polls are discovered from the database, so a restart recovers missed deadlines.
The scheduler retries failures on the next scan. No public closing endpoint exists.
More YES than NO approves; more NO or zero votes rejects; equal nonzero counts
produces TIED. Only the organizer may resolve a tie. Approval and creation of a
unique itinerary item commit together. Cancellation sets the item and proposal to
CANCELLED but retains the poll outcome, organizer resolution, votes, and history.
Active itinerary results sort by start time, then item ID. Proposal lists batch
their poll/voter/vote/history queries rather than querying each proposal separately.

All activity transactions acquire the trip row lock first, including poll opening
and its membership snapshot, to coordinate with invitation acceptance and enforce
capacity limits. Existing proposal/poll objects refresh after the lock is acquired.
Scheduler workers skip locked trips and retry on a later scan, so multiple API
workers cannot resolve the same poll twice. All failures roll back the complete
operation. Reads also use the trip lock to return consistent proposal/poll histories.

`docs/openapi.yaml` is generated from FastAPI and compared semantically in CI.
Apply Alembic migrations before starting the API. The current Docker setup uses
reload servers and is for development.

Notification migration `0008` adds channel preferences to users and creates
`notifications` and `notification_emails`. `NotificationPublisher` records events
in the business transaction, suppresses self-notifications, applies current
preferences, and deduplicates by recipient/event key. Email-only records are
excluded from inbox APIs. Trip/resource deletion clears foreign keys while
preserving notification text. `NotificationInboxService` owns inbox reads, read
state, and preference updates; all queries are scoped to the current user.

The email worker uses short database locks to claim jobs, then releases them
before SMTP I/O. Lease expiration recovers interrupted workers; completion checks
an ownership token. Opt-out cancels pending/claimed jobs, with a final cancellation
check before sending. Failed SMTP attempts back off and eventually become FAILED.
Global SMTP disable pauses delivery without affecting in-app notifications.
SMTP acceptance and database commit cannot be atomic, so retry after a crash or
ambiguous provider response may duplicate an email. See [notification contracts
and operational details](notifications.md).
