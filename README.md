# group-travel-planner

Collaborative group trip planner: participants propose activities, vote in organizer-run polls, and approved plans land on a shared itinerary automatically. NYU CS-GY 6063, Team 10.

The backend includes the initial database schema, registration, login using email
or a unique username, JWT signing/verification, and logout. The frontend login
context is still a placeholder and is not wired to these endpoints yet.
Trip Management routes are available as authenticated scaffolds and return HTTP
501 until their Service and Repository business logic is implemented.

## Setup

Install Node.js 22.12+, [pnpm](https://pnpm.io/installation), and
[uv](https://docs.astral.sh/uv/getting-started/installation/) 0.13.5 or later.
The repository pins pnpm 12.15.0 in `package.json`; Corepack can select this version.
uv installs Python 3.15 when needed. Docker Compose v2 is needed for the full stack.

```sh
pnpm install --frozen-lockfile
uv sync --project backend --python 3.15 --frozen
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env` for the last command. Keep existing
local environment values if you already have `.env`. `pnpm install --frozen-lockfile` installs Husky hooks.
Ensure `uv` and Node are on PATH in the terminal or Git client used for commits.

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

Compose sets the backend database hostname to `db`. If you change the database
credentials or port, update the host `DATABASE_URL` too. URL-encode special
characters in connection URL credentials. Never put secrets in `VITE_*` values.
Use independently generated secrets and a deployment-specific configuration for
any deployed environment; the Compose setup is for development.

## Development

```sh
pnpm run dev
```

This builds and starts PostgreSQL, runs Alembic migrations once the database is
healthy, then starts FastAPI and Vite with hot reload. Open the frontend at
<http://localhost:5173>. Source edits under `frontend/src` and `backend/app` reload
automatically. Rebuild after dependency changes. Stop with `docker compose down`;
the database volume persists. `docker compose down -v` also deletes local data.

To run application processes directly, start PostgreSQL separately (or run
`docker compose up -d db`), then use separate terminals:

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
`docker compose run --rm migrate` to apply additional migrations.

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
