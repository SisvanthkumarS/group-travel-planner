# group-travel-planner

Collaborative group trip planner: participants propose activities, vote in organizer-run polls, and approved plans land on a shared itinerary automatically. NYU CS-GY 6063, Team 10.

The backend includes the initial database schema, registration, login using email
or a unique username, JWT signing/verification, and logout. The frontend login
context is still a placeholder and is not wired to these endpoints yet.
Authenticated trip creation persists the trip and Organizer membership in one
transaction. Trip details return the trip and its member list to authenticated
members. Trip listing includes only the current user's memberships, ordered by
start date and trip ID. Organizers can delete their trips; memberships and invitations
are removed by database cascades in the same transaction.
Organizers can create pending invitations for registered users by email or username;
existing members and duplicate pending invitations are rejected. Users can list all
invitations they have received, newest first, and accept or decline pending invitations.
Acceptance adds the recipient as a member atomically and enforces the eight-person trip limit.

For frontend integration, see the [Backend API Integration Guide](docs/backend-api-guide.md)
for request fields, authentication requirements, response examples, and error handling
for Authentication, Trip Management, Invitations, and session renewal.

## Setup

Install Node.js 22.12+, [pnpm](https://pnpm.io/installation), and
[uv](https://docs.astral.sh/uv/getting-started/installation/) 0.13.5 or later.
The repository pins pnpm 12.15.0 in `package.json`; Corepack can select this version.
uv installs Python 3.15 when needed. Docker Compose v2 is needed for the full stack.

```sh
pnpm install --frozen-lockfile
uv sync --project backend --python 3.15 --frozen
cp .env.example .env
cp docker/.env.example docker/.env
```

On PowerShell, use `Copy-Item .env.example .env` for the last command. Keep existing
local environment values if you already have `.env`. `pnpm install --frozen-lockfile` installs Husky hooks.
Ensure `uv` and Node are on PATH in the terminal or Git client used for commits.

## Redis and refresh sessions

Login sets an `access_token` JWT and an opaque HttpOnly `refresh_token` cookie.
Redis stores only a hash of the refresh credential. Protected endpoints renew
cookies automatically when access expires or is within 60 seconds of expiry;
`POST /api/v1/auth/refresh` also supports explicit renewal. Defaults are a 30-minute
access token, 7-day sliding idle timeout, and 30-day absolute session deadline.
Logout clears both cookies and deletes the current refresh session. A copied
access JWT remains valid until expiry; it is not blacklisted. An existing user
must log in once after upgrading to obtain both new cookies.

Set `REDIS_URL` for processes on the host and `REDIS_URL_DOCKER` for the backend
container. For a remote server, both can use the same URL. Keep credentials in
ignored `.env` files, never documentation or Git. Use `rediss://` if the server
provides TLS. Redis errors return 503 for login/renewal; valid access JWTs continue
working. Logout clears cookies even if Redis is unavailable, but returns 503
because server-side revocation could not be confirmed.

The development Compose files under `docker/` include a local Redis service.
Compose reads `docker/.env`; host processes read the root `.env`. Keep database
credentials consistent between them. For an existing local setup, preserve the
current credentials rather than overwriting either file. To start Redis only:

```sh
docker compose --env-file docker/.env -f docker/compose.dev.yml up -d redis
```

Set `REDIS_URL_DOCKER` in `docker/.env` to use a remote Redis for authentication. After dependency or
environment changes, rebuild/recreate the backend; source changes still reload.
Refresh credentials stay stable within a browser session to support parallel
requests, while Redis TTL renewals use WATCH/MULTI to avoid recreating a session
revoked concurrently. Each browser login has an independent refresh session.

## Environment

`.env.example` documents all variables; `.env` is ignored by Git. The supplied
values are disposable local defaults, not deployment credentials.

| Variable                                                             | Purpose                                                               |
| -------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `APP_NAME`, `APP_ENV`                                                | API title and application environment                                 |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Local database configuration and published port                       |
| `DATABASE_URL`                                                       | SQLAlchemy/psycopg connection URL for host processes                  |
| `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`     | JWT signing key, permitted algorithm, and access-token lifetime       |
| `JWT_COOKIE_NAME`, `JWT_COOKIE_SECURE`                               | Cookie name and HTTPS-only flag; enable Secure for HTTPS deployments  |
| `CORS_ORIGINS`                                                       | JSON array of allowed browser origins                                 |
| `VITE_API_URL`                                                       | Public frontend API base URL, normally `http://localhost:8000/api/v1` |

Additional settings: `REDIS_URL`, `REDIS_URL_DOCKER`, `REDIS_KEY_PREFIX`,
`REDIS_TIMEOUT_SECONDS`, `JWT_REFRESH_COOKIE_NAME`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`,
`JWT_SESSION_MAX_DAYS`, and `JWT_REFRESH_WINDOW_SECONDS`. See `.env.example`.

The production frontend image reads `VITE_API_URL` when the container starts,
so the same image can be reused across environments without rebuilding:

```bash
docker run --rm -p 3000:3000 \
  -e VITE_API_URL=http://3.12.166.194:8000/api/v1 \
  hubertchang/course:frontend-latest
```

With production Compose, set `VITE_API_URL` in the file passed to `--env-file`,
then recreate the frontend container. The entrypoint generates
`dist/runtime-config.js` before serving the app, and that file is served with
`Cache-Control: no-store`. Only this public API URL is exposed. If omitted,
the container defaults to `http://localhost:8000/api/v1`. Local Vite development
continues to use `import.meta.env.VITE_API_URL`. The backend's `CORS_ORIGINS`
must allow the actual frontend origin, including its scheme and port.

Compose sets the backend database hostname to `postgres` and internal port to `5432`. If you change the database
credentials or port, update the host `DATABASE_URL` too. URL-encode special
characters in connection URL credentials. Never put secrets in `VITE_*` values.
Use independently generated secrets and a deployment-specific configuration for
any deployed environment; the Compose setup is for development.

## Development

Cookie-authenticated API requests use custom-header CSRF protection. Every request
except `GET`, `HEAD`, and `OPTIONS` must send `X-CSRF-Protection: 1`, including
registration, login, and logout; missing or incorrect headers return `403` before
the handler runs. Browser requests with an `Origin` must match `CORS_ORIGINS`
exactly. List only trusted frontend origins (including a same-origin deployment's
origin); wildcard and `null` origins are rejected. The header forces cross-origin
browser requests through CORS preflight and is not a secret token.

The shared frontend `apiRequest(path, options?)` sends cookies and adds the
header automatically for mutations. For example:

```ts
await apiRequest('/auth/logout', { method: 'POST', auth: false });
```

CLI clients must also send the header. Safe requests and CORS preflights do not
need it. The HttpOnly session cookie retains its `SameSite=Lax` protection.

```sh
pnpm run dev
```

The backend image is built on first use; rebuild it after dependency changes.
This starts PostgreSQL and Redis, runs Alembic migrations once the database is
healthy, then starts FastAPI and Vite with hot reload. Open the frontend at
<http://localhost:5173>. Source edits under `frontend/src` and `backend/app` reload
automatically. Rebuild the backend after dependency changes. Stop with
`docker compose --env-file docker/.env -f docker/compose.dev.yml stop`;
the database volume persists. Use the same Compose file, environment file, and
project name for subsequent commands; removing database volumes deletes their data.

The local PyCharm `Docker - Full Stack` launcher must use
`docker/compose.dev.yml` and `docker/.env`, not the removed root `compose.yaml`.
Start with the same Compose project name on every run to reuse the database volume.
The backend now runs the image's migration/Uvicorn startup script instead of
`sleep infinity`. Frontend dependencies use container volumes so Linux binaries
do not overwrite the host's node_modules. Rebuild backend dependencies with:

```sh
docker compose --env-file docker/.env -f docker/compose.dev.yml build backend
```

To run application processes directly, start PostgreSQL separately (or run
`docker compose --env-file docker/.env -f docker/compose.dev.yml up -d postgres`), then use separate terminals:

```sh
pnpm run db:migrate
pnpm run dev:backend
pnpm run dev:frontend
```

The empty app and frontend can start without a database; migrations and future
database-backed features require PostgreSQL.

## Migrations

Revision `0002` creates `users`, `trips`, `trip_members`, and `invitations` from
the team's Database Setup document, including its constraints and indexes.
Revision `0003` adds `users.user_name`, also adopting an existing column created
manually. Existing names are preserved; missing names use the account email.
Revision `0004` requires unique usernames of 1–10 characters. Before upgrading an
existing database, correct duplicate, blank, or overlong usernames explicitly;
the migration does not rename accounts automatically. Username lookup is case-sensitive.
Revision `0005` expands the username limit to 30 characters, matching registration
and login validation. Downgrading to `0004` requires names longer than 10 characters
to be corrected first; the migration never truncates names.
Register future models in `backend/app/models/__init__.py` so Alembic sees their metadata.
Use `travel_test` for development; keep the production database separate.
When reusing an existing Docker volume, create `travel_test` before switching
`POSTGRES_DB` and `DATABASE_URL`: changing `POSTGRES_DB` only initializes a database
on a new volume.

```sh
uv run --project backend alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
pnpm run db:migrate
uv run --project backend alembic -c backend/alembic.ini downgrade -1
```

Review generated migrations before applying them. In Compose, run
`docker compose --env-file docker/.env -f docker/compose.dev.yml exec backend alembic -c /opt/app/backend/alembic.ini upgrade head` to apply additional migrations.

## API documentation

- Swagger UI: <http://localhost:8000/docs>
- Generated schema: <http://localhost:8000/api/v1/openapi.json>
- Checked-in schema: [docs/openapi.yaml](docs/openapi.yaml)

The router is mounted under `/api/v1`; its contract has no endpoints yet. Run
`pnpm run openapi` after changing API contracts, using the default `APP_NAME` when
exporting the shared schema. `pnpm run openapi:check` detects schema drift and runs
in CI. FastAPI's [documentation configuration](https://fastapi.tiangolo.com/tutorial/metadata/)
describes these built-in documentation routes.

## Quality checks

```sh
pnpm run lint
pnpm run format
pnpm test
pnpm run build
```

Linting runs ESLint, Prettier, and Ruff lint/format checks. Tests use Vitest for the
API client and pytest for app configuration, docs, and CORS. Tests live under
`tests/frontend` and `tests/backend`. Database integration tests are skipped unless
`TEST_DATABASE_URL` points to a migrated PostgreSQL test database. They check actual
constraints and cascade behavior and roll back their test rows. For example, after
running migrations with the host `DATABASE_URL` exported:

```sh
TEST_DATABASE_URL="$DATABASE_URL" uv run --project backend pytest -c backend/pyproject.toml tests/backend/test_database_schema.py
```

The [Husky](https://typicode.github.io/husky/get-started.html) pre-commit hook runs
lint-staged: ESLint and Prettier for staged frontend code, Prettier for frontend
assets, and Ruff lint/format checks for staged Python. It then runs the full
frontend build, including TypeScript checks, followed by `pnpm test` for frontend
tests, backend tests, and OpenAPI consistency before allowing the commit.
Python formatting failures can be fixed with `pnpm run format`, then restaged.
CI checks lint, tests, OpenAPI
consistency, the frontend build, PostgreSQL constraints, model/migration consistency,
and migration upgrade/downgrade on PostgreSQL.

## Layout

```text
frontend/           React + TypeScript + Vite, routing, API client, auth context
backend/app/        Controllers -> Services -> Repositories -> Models
backend/migrations/ Alembic revision chain
infra/              Development Dockerfiles
docs/               OpenAPI contract and architecture notes
tests/              Frontend and backend tests
.github/workflows/  CI
```

See [docs/architecture.md](docs/architecture.md) for layer responsibilities.
