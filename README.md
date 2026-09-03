# Next Task

Next Task is a small, self-hosted task manager that ranks unfinished work with a
workspace-configurable score. It supports multiple workspaces, owner/editor/viewer
roles, Markdown task descriptions, subtasks, assignees, blocking history, and a
Tag Studio-style inheritance DAG.

The application is deliberately one deployable unit: FastAPI serves the REST API
and built Svelte PWA, while SQLite stores application data in a mounted `/data`
directory. There is no offline synchronization; the service worker caches only the
application shell and an offline explanation page.

## Docker deployment

Prepare the persistent directory once. The image runs as UID/GID `10001`:

```bash
sudo mkdir -p /mnt/hdd/next-task/data
sudo chown 10001:10001 /mnt/hdd/next-task/data
```

Build and start the single application container:

```bash
cd ~/services/next-task
docker compose up --build
```

Add `-d` to run it in the background.

The application is available on port `8000`. `docker-compose.yml` deliberately
does not alter a reverse proxy, DNS, or an external Docker network. Once HTTPS is
in front of the application, enable the cookie `Secure` attribute when starting
or recreating it:

```bash
NEXT_TASK_COOKIE_SECURE=true docker compose up -d --build
```

The production-shaped reference is also available as
`docker-compose.example.yml`. Both mount persistent SQLite state from
`/mnt/hdd/next-task/data` and never expose SQLite itself.

Database migrations run automatically before the web server starts. To create the
first account after startup:

```bash
docker compose exec next-task uv run python -m app.cli create-user
```

The command prompts for email, display name, password, and confirmation. Sign in,
then create the first workspace in the UI; its creator becomes owner and the
`todo` and `doing` statuses plus a default scoring formula are created together.

Reset a password with direct server access:

```bash
docker compose exec next-task uv run python -m app.cli reset-password user@example.com
```

Existing sessions for that user are revoked. For controlled automation, both CLI
commands also accept `--password-stdin`, avoiding a password in process arguments.

## Local development

Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Node.js 22+ are expected.
From the repository root:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

The default development database is `./data/next-task.sqlite3` and is ignored by
Git. In another terminal, start Vite; it proxies `/api` to FastAPI:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. To create a local user from the repository root:

```bash
uv run python -m app.cli create-user
```

### Checks and builds

```bash
uv run ruff check backend
uv run pytest backend/tests

cd frontend
npm run check
npm run build
```

The complete production artifact can be verified with:

```bash
docker compose build
```

### Migrations

After changing SQLAlchemy models, create and inspect a migration:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic check
```

Rollback one revision during development with `uv run alembic downgrade -1`.
Never replace migrations with `Base.metadata.create_all()` in production.

## Scoring formulas

Scores are calculated when tasks are read and are not persisted. Available
variables are `priority`, `ageDays`, `idleDays`, `dueOffsetDays`, and
`statusValue`. Formulas accept numbers, arithmetic, comparisons, boolean
operations, and Python-style conditional expressions, for example:

```text
priority * 20 + idleDays * 1.5 + (dueOffsetDays * 50 if dueOffsetDays > 0 else 0)
```

Function calls, attribute access, imports, and other arbitrary Python are rejected
by the limited expression evaluator. Finished tasks score zero and are excluded
from the normal Next queue.

## API

REST routes live under `/api`. With the backend running, interactive OpenAPI docs
are at `http://localhost:8000/api/docs`; the health check is `/api/health`.
