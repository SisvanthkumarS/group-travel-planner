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
`/api/v1/trips`. These are scaffolds: `TripService` returns HTTP 501 until business
logic is implemented. Controllers delegate with the authenticated user ID; the
client cannot choose its own Organizer identity. Request DTOs validate nonblank
names/destinations and date order. `TripRepository` provides unimplemented database
method signatures. Creation must insert the trip and Organizer membership in one
transaction; detail access requires membership, and deletion requires the Organizer.
The authentication lookup already starts the shared Session transaction, so write
services should finish it with commit/rollback rather than calling begin again.

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
