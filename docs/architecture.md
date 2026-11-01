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

`docs/openapi.yaml` is generated from FastAPI and compared semantically in CI.
Add domain models, endpoints, authentication, and their tests when their designs
are ready. The current Docker setup uses reload servers and is for development.
