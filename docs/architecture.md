# Architecture

The React SPA uses React Router for navigation, a typed fetch wrapper for API
requests, and an in-memory authentication context. The context is a placeholder
for a future login flow; it does not authenticate users. No token persists across
reloads. The frontend authentication context has not yet been wired to the backend's JWT cookie flow.

FastAPI hosts the app and documentation. All future feature controllers join the
router with the `/api/v1` prefix. `AuthController.py` delegates registration and
login to `AuthService`; logout clears the configured JWT cookie. Login accepts
email or username, treating blank identifiers as absent and preferring email
when both are supplied. Usernames are case-sensitive, unique, and limited to
1–30 characters after trimming outer whitespace. Registration checks email and
username availability; database unique indexes also prevent concurrent duplicates.
Login first looks up the user, then verifies the password hash. Invalid credentials
return 401; missing identifiers or passwords return 422.
The controller sets an HttpOnly, SameSite=Lax cookie after authentication.
`create_access_token` signs a token with `sub`, `iat`, and `exp`;
`parse_access_token` verifies the signature, timestamps, and positive user ID.
Tokens contain no password data. Set `JWT_COOKIE_SECURE=true` for HTTPS deployment.
Clearing a cookie does not revoke a previously issued token on the server.

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
must fall within the trip dates. Since trips have no timezone field, travel dates
are interpreted as UTC calendar dates; activity timestamps must include an offset.
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
