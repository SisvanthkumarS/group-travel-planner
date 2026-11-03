# group-travel-planner

Collaborative group trip planner: participants propose activities, vote in organizer-run polls, and approved plans land on a shared itinerary automatically. NYU CS-GY 6063, Team 10.

The React frontend includes registration and sign-in, trip lists and creation,
invitations, activity proposals, voting, and the shared itinerary. It uses the
backend's HttpOnly JWT cookie, sends credentials and the required CSRF header,
and synchronizes sign-out across tabs. See the integration gaps below before
testing the complete flow.

The FastAPI backend supports:

- Registration, email/username login, and logout.
- Trip creation with an organizer membership, member-only trip details, listing,
  and organizer-only deletion.
- Invitations to registered users, acceptance/decline, and an eight-participant
  limit including the organizer.
- Activity proposals with description, estimated cost, and timezone-aware times;
  a maximum of 100 proposals per trip; and author-only withdrawal while pending
  or open before the poll deadline.
- Organizer-opened polls that snapshot eligible voters, including the organizer
  and proposal author. Each eligible participant can cast or update one YES/NO vote.
- Automatic deadline processing: more YES than NO approves, more NO or zero votes
  rejects, and equal nonzero counts require an organizer tie decision. There is
  no public poll-closing endpoint.
- Automatic addition of approved activities to the itinerary exactly once,
  chronological retrieval, and organizer-only cancellation. Canceled proposals
  retain their poll outcome, vote history, and any tie decision.

Request and response contracts are in [docs/openapi.yaml](docs/openapi.yaml);
implementation details are in [docs/architecture.md](docs/architecture.md).

## Current integration gaps

- The frontend trip form and generated frontend types still need the required
  `timezone` field. Until updated, submitting that form returns HTTP 422.
- Frontend activity inputs and display currently use the browser's timezone;
  backend date validation uses the trip's timezone. These can differ.
- `GET /auth/me` is not implemented. Session restoration tries it, then falls
  back to cached user display data after verifying the cookie with `GET /trips`.
- Invitation responses contain IDs, without the trip name or organizer name.
- The frontend requires eight-character registration passwords, but backend
  registration currently accepts passwords of one or more characters.

## Setup

Install Node.js 26+, [pnpm](https://pnpm.io/installation), and
[uv](https://docs.astral.sh/uv/getting-started/installation/) 0.13.5 or later.
The repository pins pnpm 12.15.0 in `package.json`; Corepack can select this version.
uv installs Python 3.15 when needed. Docker Compose v2 with support for `include`
is needed for the container setup.

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
| `CORS_ORIGINS`                                                       | JSON array of explicit trusted browser origins for CORS and CSRF      |
| `POLL_SCHEDULER_ENABLED`                                             | Enable automatic poll closure; defaults to `true`                     |
| `POLL_SCHEDULER_INTERVAL_SECONDS`                                    | Deadline scan interval; defaults to `5` seconds                       |
| `VITE_API_URL`                                                       | Public frontend API base URL, normally `http://localhost:8000/api/v1` |

Host processes read the root `.env`; Docker Compose uses `docker/.env`, copied
from `docker/.env.example`. Docker's database service is named `postgres`;
host processes normally connect through `localhost` and the published port.
If you change database credentials or the published port, update the host
`DATABASE_URL` too. URL-encode special
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

For local application development, start PostgreSQL separately, configure the
root `.env`, and apply migrations before starting FastAPI. Then run the backend
and frontend in separate terminals:

```sh
pnpm run db:migrate
pnpm run dev:backend
pnpm run dev:frontend
```

Open <http://localhost:5173> for the frontend and <http://localhost:8000/docs>
for Swagger UI. Use `localhost` consistently for both to keep cookie behavior
predictable. Source changes reload automatically.

To start only the Docker database services:

```sh
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/compose.base.yml up -d
```

On PowerShell, use `Copy-Item docker/.env.example docker/.env`. Preserve existing
values if the file already exists. The base configuration starts PostgreSQL and
Redis; the current FastAPI activity workflow does not require Redis.

`pnpm run dev` uses `docker/compose.dev.yml` and `docker/.env` to start the
development containers in the background. **Its backend command is currently
`sleep infinity`: it does not start FastAPI or run migrations.** Use the host
commands above for the API. The Docker frontend already occupies port 5173, so
do not also start a host frontend on that port. Stop the development containers
with `docker compose --env-file docker/.env -f docker/compose.dev.yml down`;
volumes persist unless explicitly removed.

The API imports and serves documentation without a database connection, but
authenticated features and the enabled deadline scheduler require a migrated
PostgreSQL database. An error such as `relation "proposals" does not exist`
means migrations must be applied to the database in `DATABASE_URL`.

## Trip timezones and poll deadlines

`POST /api/v1/trips` requires an IANA timezone alongside its calendar dates:

```json
{
  "name": "New York weekend",
  "destination": "New York",
  "start_date": "2027-07-01",
  "end_date": "2027-07-03",
  "timezone": "America/New_York"
}
```

Trip create, list, and detail responses include `timezone`. Proposal `starts_at`
and `ends_at` require explicit offsets, such as `2027-07-03T21:00:00-04:00`.
The backend checks both dates in the trip's timezone, so a late evening on the
final day is valid even when its UTC date is the following day. The start must
be in the future, and the end must follow the start. Stored timestamps, deadline
checks, and itinerary ordering compare instants rather than local clock readings.

A poll deadline must be after now and before the proposed activity starts.
Votes stop at the deadline even if the scheduler has not processed the poll yet.
The scheduler scans every five seconds by default, recovers overdue polls after
restart, and retries failed scans. Trip row locks and unique itinerary records
prevent duplicate approvals across workers.

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
Revision `0006` adds proposals, polls, eligible voter snapshots, current votes,
vote history, and itinerary items.
Revision `0007` adds trip timezones and assigns `America/New_York` to existing
trips, as agreed for legacy data. New API requests must provide a valid timezone;
legacy direct database inserts default to UTC. Review existing trips in other
timezones before relying on their local-date validation.
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

Review generated migrations before applying them. Run `pnpm run db:migrate`
against the intended `DATABASE_URL`; the current development Compose configuration
does not provide a migration service.

## API documentation

- Swagger UI: <http://localhost:8000/docs>
- Generated schema: <http://localhost:8000/api/v1/openapi.json>
- Checked-in schema: [docs/openapi.yaml](docs/openapi.yaml)

The router is mounted under `/api/v1` and exposes 18 operations:

| Area             | Operations (paths relative to `/api/v1`)                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------------------------- |
| Authentication   | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`                                                |
| Trips            | `POST /trips`, `GET /trips`, `GET /trips/{trip_id}`, `DELETE /trips/{trip_id}`                                |
| Invitations      | `POST /trips/{trip_id}/invitations`, `GET /invitations`, `PATCH /invitations`                                 |
| Proposals        | `POST /trips/{trip_id}/proposals`, `GET /trips/{trip_id}/proposals`, `POST /proposals/{proposal_id}/withdraw` |
| Polls and voting | `POST /proposals/{proposal_id}/poll`, `PUT /polls/{poll_id}/vote`, `POST /polls/{poll_id}/resolve`            |
| Itinerary        | `GET /trips/{trip_id}/itinerary`, `DELETE /trips/{trip_id}/itinerary/{item_id}`                               |

Run
`pnpm run openapi` after changing API contracts, using the default `APP_NAME` when
exporting the shared schema. `pnpm run openapi:check` detects schema drift and runs
in CI. Run `pnpm run openapi:types` to regenerate frontend API types, then update
affected callers and run the frontend build. Swagger mutation requests must also
include `X-CSRF-Protection: 1`.

## Quality checks

```sh
pnpm run lint
pnpm run format
pnpm test
pnpm run build
```

Linting runs ESLint, Prettier, and Ruff lint/format checks. Tests use Vitest for the
API client, authentication, and frontend workflow helpers, plus pytest for backend
authentication, CSRF, authorization, validation, and workflow behavior. Tests live under
`tests/frontend` and `tests/backend`. Database integration tests are skipped unless
`TEST_DATABASE_URL` points to a migrated PostgreSQL test database. They check actual
constraints, transaction rollback, concurrent limits, poll outcomes, history,
and local-date validation. Fixtures roll back or remove their test records. For example, after
running migrations with the host `DATABASE_URL` exported:

```sh
TEST_DATABASE_URL="$DATABASE_URL" uv run --project backend pytest -c backend/pyproject.toml tests/backend
```

PowerShell equivalent:

```powershell
$env:TEST_DATABASE_URL = $env:DATABASE_URL
uv run --project backend pytest -c backend/pyproject.toml tests/backend
```

These examples assume `DATABASE_URL` has been exported in the shell and points to
a migrated test database. A value present only in `.env` is not a shell variable.

The [Husky](https://typicode.github.io/husky/get-started.html) pre-commit hook runs
lint-staged: ESLint and Prettier for staged frontend code, Prettier for frontend
assets, and Ruff lint/format checks for staged Python. It then runs the full
frontend build, including TypeScript checks, followed by `pnpm test` for frontend
tests, backend tests, and OpenAPI consistency before allowing the commit.
Python formatting failures can be fixed with `pnpm run format`, then restaged.
CI checks lint, tests, OpenAPI
consistency, the frontend build, PostgreSQL constraints, model/migration consistency,
and migration upgrade/downgrade on PostgreSQL.
The current CI database step names schema, authentication, trip, and invitation
integration modules explicitly; run the full backend suite with `TEST_DATABASE_URL`
to include the activity integration tests too.

## Layout

```text
frontend/           React + TypeScript + Vite, routing, API client, auth context
backend/app/        Controllers -> Services -> Repositories -> Models
backend/migrations/ Alembic revision chain
docker/             Compose configurations, Dockerfiles, container startup
docs/               OpenAPI contract and architecture notes
tests/              Frontend and backend tests
.github/workflows/  CI
```

See [docs/architecture.md](docs/architecture.md) for layer responsibilities.
