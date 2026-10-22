# Architecture

The React SPA uses React Router for navigation, a typed fetch wrapper for API
requests, and an in-memory authentication context. The context is a placeholder
for a future login flow; it does not authenticate users. No token persists across
reloads. JWT configuration is reserved for future backend authentication work.

FastAPI hosts the app and documentation. All future feature controllers join the
router with the `/api/v1` prefix. The scaffold deliberately has no product routes.

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

PostgreSQL is the database. Alembic owns schema evolution; the initial revision
is empty. Compose waits for the database health check, applies migrations in a
one-shot service, and starts the API after successful migration. Backend health
checks read the generated schema; they confirm HTTP availability, not database
readiness. Frontend health checks read its index page.

`docs/openapi.yaml` is generated from FastAPI and compared semantically in CI.
Add domain models, endpoints, authentication, and their tests when their designs
are ready. The current Docker setup uses reload servers and is for development.
