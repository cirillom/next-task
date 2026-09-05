# Next Task

Next Task is a small, self-hosted task manager that ranks unfinished work with a
workspace-configurable score. It supports multiple workspaces, owner/editor/viewer
roles, Markdown task descriptions, subtasks, assignees, blocking history, and a
Tag Studio-style inheritance DAG.

One production image contains both entrypoints: FastAPI serves the REST API and
built Svelte PWA, and a separate isolated process serves the authenticated MCP
gateway. Both use SQLite in a mounted `/data` directory. There is no offline
synchronization; the service worker caches only the application shell.

## Docker development

The repository's `docker-compose.yml` builds the current checkout, publishes port
`8000`, and stores disposable development data in `./data-dev`:

```bash
docker compose up --build
```

Database migrations run automatically before the web server starts. Create a
development user from another terminal with:

```bash
docker compose exec next-task uv run python -m app.cli create-user
```

## Releases and homeserver deployment

CI runs backend lint/tests, release tooling tests, Svelte checks/build, and a
production image build on pushes to `main` and pull requests. It also checks that
Python and npm release versions agree, including both lockfiles.

To release, open **Actions → Release → Run workflow**, select **main**, and choose
`patch` (default), `minor`, or `major`. For example, from `0.4.2` these produce
`0.4.3`, `0.5.0`, and `1.0.0`, respectively. The equivalent CLI command is:

```bash
gh workflow run release.yml --ref main -f bump=patch
```

The workflow updates `pyproject.toml`, `uv.lock`, `frontend/package.json`, and
`frontend/package-lock.json` using uv and npm. After backend and frontend checks
pass, it commits the version change and atomically pushes `main` and the matching
`vMAJOR.MINOR.PATCH` tag. It then publishes the versioned image and `latest` to
`ghcr.io/cirillom/next-task`, and creates a GitHub Release with
`docker-compose.example.yml` attached. The frontend remains a private npm package;
this workflow publishes the Docker image, not packages to npm or PyPI.

The workflow uses the built-in `GITHUB_TOKEN`; repository rules must allow it to
push the release commit to `main` and create version tags. Publication runs in the
same workflow because tags pushed by that token do not trigger another workflow.
Release runs are serialized. If publication fails, use **Re-run failed jobs**;
rerunning the entire run also reuses its existing release commit and version.
If `main` changes during validation, the atomic push fails without creating a
remote tag; rerun to release the updated `main`.

Manually pushed version tags still work when all four files already match the
tag. To check versions or prepare a bump locally with Python 3.12+, uv, and npm:

```bash
python3 scripts/release.py check
python3 scripts/release.py bump patch
```

The local bump command only updates the four version files. It does not commit,
tag, or publish anything, and restores those files if a package manager fails.

The homeserver keeps only deployment configuration in `~/services/next-task`.
Its Compose file pulls the published image, mounts persistent state from
`/mnt/hdd/next-task/data`, and runs the private web app plus a loopback-only MCP
gateway. Tailscale Funnel provides public HTTPS only for the gateway.

```bash
cd ~/services/next-task
docker compose --env-file ../.env pull
docker compose --env-file ../.env up -d
docker compose --env-file ../.env exec next-task uv run python -m app.cli create-user
```

The image runs as UID/GID `10001`, so prepare the persistent directory first as
documented in the deployment README. Secure cookies are enabled in the homeserver
Compose file.

Reset a password with direct server access:

```bash
docker compose --env-file ../.env exec next-task uv run python -m app.cli reset-password user@example.com
```

Existing sessions for that user are revoked. Both CLI commands accept
`--password-stdin` for controlled automation without putting a password in process
arguments. After signing in, create the first workspace in the UI; its creator
becomes owner and the `todo` and `doing` statuses plus a default scoring formula
are created together.

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
uv run ruff check backend scripts tests
uv run pytest backend/tests tests

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

## ChatGPT MCP connector

The connector lets ChatGPT use Next Task tools directly. Your ChatGPT subscription
handles the conversation and natural-language interpretation; this server never calls
an OpenAI model API and does not need an OpenAI API key.

The production Compose file binds the isolated MCP process to host loopback. Give it a
public HTTPS URL with Tailscale Funnel and set that exact origin in
`NEXT_TASK_MCP_PUBLIC_URL` before starting either container:

```bash
sudo tailscale funnel --bg --https=8443 8765
tailscale funnel status
```

The connector URL is the public origin plus `/mcp`, for example:

```text
https://homeserver.tail195af8.ts.net:8443/mcp
```

To connect:

1. In Next Task, open **Settings → ChatGPT task connector** and copy the URL.
2. In ChatGPT, enable **Developer mode** in **Settings → Security and login**.
3. Open **Settings → Plugins**, add a custom connector, and paste the URL.
4. Sign in on the Next Task authorization page and approve the connection.

Then ask naturally, for example:

```text
In my Home workspace, create a high-priority task to buy detergent tomorrow and tag it shopping.
```

ChatGPT first inspects the selected workspace's statuses, tags, and members, proposes the
task fields, and asks for confirmation before calling a write tool. It can list and inspect
tasks, create and update them, mark them finished or reopened, and block or unblock them.

OAuth uses authorization code with PKCE. Access and refresh tokens are stored only as
hashes, registered client secrets are encrypted with `NEXT_TASK_CREDENTIAL_SECRET`, and
each user can revoke all ChatGPT connections from Next Task Settings.

## Gemini text to task

Each user can add a personal Gemini API key in **Settings -> Gemini text to task**.
After selecting a workspace, editors and owners can use **Text to task** in the top
bar, describe one task naturally, and review an editable draft before anything is
created. The review includes title, Markdown description, status, priority, due date,
assignees, existing tags, and suggested new tags.

Drafting sends the entered text plus the selected workspace statuses, members, and tag
names to Gemini. The personal API key is encrypted in SQLite and is never returned to
the browser after it is saved. Server-side encryption requires a stable value of at
least 32 characters:

```dotenv
NEXT_TASK_CREDENTIAL_SECRET=<random value kept outside Git>
```

Set it before the first API key is saved and keep it unchanged across deployments. If
it is lost or replaced, users must save their Gemini keys again.
`NEXT_TASK_GEMINI_MODEL` optionally overrides the default Flash model.

## Scoring formulas

Scores are calculated when tasks are read and are not persisted. Available
variables are `priority`, `ageDays`, `idleDays`, `dueOffsetDays`, `hasDueDate`, and
`statusValue`. `hasDueDate` is `1` when a due date exists and `0` otherwise. The
`dueOffsetDays` value is negative before the due date, zero on the due date, and
positive after it. Formulas accept numbers, arithmetic, comparisons, boolean
operations, the `exp()` function, and Python-style conditional expressions.

The default formula is:

```text
priority * 25
+ ageDays * 0.25
+ idleDays * 1.00
+ statusValue * 20
+ (
    (
        50 * exp(dueOffsetDays / 7)
        if dueOffsetDays < 0
        else 50 + dueOffsetDays * 20
    )
    if hasDueDate > 0
    else 0
)
```

Only the explicitly supported `exp()` function can be called. Other function calls,
attribute access, imports, and arbitrary Python are rejected by the limited expression
evaluator. Finished tasks score zero and are excluded from the normal Next queue.

## API

REST routes live under `/api`. With the backend running, interactive OpenAPI docs
are at `http://localhost:8000/api/docs`; the health check is `/api/health`.
