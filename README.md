# Next Task

Next Task is a small self-hosted task manager built around one core question: **what deserves attention next?**

It combines ranked task selection with workspaces, statuses, tags, subtasks, assignees, blocking, Pomodoro focus sessions, Gemini-assisted task creation, MCP access, and configurable scoring formulas.

## Quick start

```bash
cp .env.example .env
# Set NEXT_TASK_CREDENTIAL_SECRET to a stable random secret.
docker compose up --build
```

The production container runs database migrations automatically before starting the API.

For local Python development:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

The default development database is `./data/next-task.sqlite3` and is ignored by Git.

## Task flow

- **Next** presents the current recommendation and actionable queue.
- **Tasks** is the full browse/search/organization view.
- **Focus** runs Pomodoro sessions around the current recommended task.
- **Drafts** holds quick captures that still need user review before entering the normal workflow.

### Quick capture

`+ New task` opens one compact capture surface with three paths:

- **Draft task** saves immediately with priority `0`, using the first non-empty line as the title and the remaining text as the description.
- **Text to task** sends the whole capture to Gemini and opens the full editor with the suggested fields filled in.
- **Expand** opens the full editor using the first non-empty line as title and the remaining text as description.

Priority `0` is reserved for drafts. Drafts are excluded from normal task lists, Next recommendations, and Pomodoro selection. Finalizing a draft opens the full editor with priority `1` as the starting value; saving it with any priority of `1` or higher moves it into the normal task workflow.

## Ranking

Tasks have a numeric score calculated from the workspace scoring formula. The default formula considers priority, age, idle time, status value, and due-date urgency.

Normal task browsing is hierarchy-aware: an unfinished parent's ranking level can pull unfinished descendants upward so required child work appears before that parent, while siblings at the same inherited level remain ordered by their own score. The displayed task score remains the task's real score.

Next and Pomodoro only consider actionable tasks: unfinished leaf work assigned to the current user or left unassigned, excluding blocked work and drafts.

## Task hierarchy

Tasks can have a parent and subtasks. A task with unfinished descendants is not actionable for Next/Pomodoro. Finishing a parent cascades completion through its descendants; reopening a child reopens finished ancestors so unfinished work cannot remain under a completed parent.

## Blocking

Tasks can be blocked with a reason and optionally scheduled to auto-unblock. The UI provides quick auto-unblock choices for tomorrow, in three days, next week, a custom date/time, or no automatic unblock.

## Pomodoro

A Focus session pins one task until it is finished, blocked, or manually replaced. Starting a focus period records work on the current task. The task description is available as autosaving working notes, using the shared line-aware Markdown editor.

## Markdown

Task descriptions support Markdown. The editor keeps the current caret line as raw Markdown while rendering the other lines, so formatting remains directly editable without a separate preview pane. Rendered task-list checkboxes can be toggled directly.

## Gemini text to task

Users can store a Gemini API key from Settings. The key is encrypted at rest with `NEXT_TASK_CREDENTIAL_SECRET`.

Quick Capture's **Text to task** action sends natural-language task text to Gemini and opens the normal task editor with proposed title, description, status, priority, due date, assignees, and tags for review before creation.

## MCP

Next Task includes an MCP server for connected clients. Configure `NEXT_TASK_MCP_PUBLIC_URL` to the externally reachable MCP URL.

The default Docker Compose setup exposes:

- Web/API: `http://localhost:8000`
- MCP: `http://localhost:8001`

## Authentication

Accounts use Argon2 password hashes. Sessions are stored server-side using hashed tokens.

`NEXT_TASK_CREDENTIAL_SECRET` protects encrypted integration credentials such as Gemini API keys and MCP OAuth client secrets. Use a stable value at least 32 characters long and back it up securely.

Example:

```bash
openssl rand -base64 48
```

Changing or losing that secret makes previously encrypted credentials unreadable.

## Workspaces

Each workspace contains its own:

- tasks
- statuses
- tags and tag hierarchy
- members and roles
- scoring formula

Roles are owner, editor, and viewer. Owners can delete a workspace permanently; user accounts themselves are not deleted with the workspace.

## Database

Next Task uses SQLite with SQLAlchemy and Alembic. Production starts with:

```bash
uv run alembic upgrade head
```

before Uvicorn, so migrations are applied automatically when the production container starts.

## Development checks

```bash
uv run ruff check backend
uv run pytest
cd frontend
npm ci
npm run check
npm run build
```

CI also builds the production Docker image.
