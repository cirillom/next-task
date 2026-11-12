# Next Task

Next Task is a small, self-hosted task manager that ranks each user's unfinished
work with a personal scoring formula. It supports Markdown task descriptions,
subtasks, blocking history, and a Tag Studio-style inheritance DAG.

There is no offline synchronization; the service worker caches only the application shell.

Dates throughout the UI use `dd/mm/yyyy`, and date/time fields use
`dd/mm/yyyy HH:mm` with a 24-hour clock in the device's timezone. API timestamps
are stored and returned in UTC; due dates remain calendar dates without timezone
conversion. Date/time fields accept this explicit format regardless of browser
language. Times skipped by a daylight-saving change are rejected; repeated times
use the device's first occurrence.

Pomodoro sessions keep one active state per account. Starting, skipping, dismissing,
or ending a period on one signed-in device is reflected on the others. The timer uses
a shared UTC deadline rather than per-second writes. In Settings, period-end audio can
be a one-time notification or a repeating alarm that must be dismissed on any device.

## Abandoning tasks

Use **Abandon task** when work is no longer worth doing. The task and its
descendants leave active lists, Next recommendations, Drafts, and focus queues
without being marked finished. In Tasks, open Filters and select
**Abandonment → Abandoned** to find them. **Restore task** brings back the
unfinished branch; descendants abandoned separately remain abandoned. A child
hidden by its parent links to that parent so you can restore the branch there.

Abandonment preserves notes, tags, dates, relationships, and blocking history.
It resolves outgoing dependency blocks for the whole abandoned branch, allowing
dependent work to proceed once its other blockers are resolved. Those resolutions
remain in history after restoration, matching Finish followed by Reopen. Abandoned
tasks cannot be selected as new blockers. Finishing a parent skips abandoned
branches. Restored tasks are ranked again using the current formula and dates.

Abandoning a pinned task or its parent clears the Pomodoro pin without changing
the timer. Focus recalculates the next eligible task in the current session scope.
Finished tasks must be reopened before they can be abandoned; drafts inherit
abandonment from their parents but cannot be abandoned separately.

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
Its Compose file pulls the published image and mounts persistent state from
`/mnt/hdd/next-task/data`.

```bash
cd ~/services/next-task
docker compose --env-file ../.env pull
docker compose --env-file ../.env up -d
docker compose --env-file ../.env exec next-task uv run python -m app.cli create-user
```

The image runs as UID/GID `10001`, so prepare the persistent directory first as
documented in the deployment README. Secure cookies are enabled in the homeserver
Compose file.

### Invite-only accounts

Public signup is disabled. To invite a beta user, have the app send a link using
the SMTP settings below:

```bash
docker compose --env-file ../.env exec next-task uv run python -m app.cli invite-user person@example.com
docker compose --env-file ../.env exec next-task uv run python -m app.cli revoke-invite person@example.com
```

Run `invite-user` again to resend. Each invocation replaces the previous link;
links expire 24 hours after issuance and work once. If delivery fails, the command
reports an error and invalidates the new link; retry the command to send another.
Configuration failures before issuance leave an existing link unchanged. SMTP
acceptance does not guarantee inbox delivery. A crash after issuance can leave a
pending link; revoke or resend it using the same commands.

Opening an invitation does not consume it. The recipient chooses a display name
and a password of at least 10 characters, then submits the form to create the
account. The invited email is verified through redemption and cannot be replaced
by the form. The user signs in normally afterward. No account is created merely
by sending an invitation. Expired, revoked, replaced, or used links cannot create
accounts. Redemption is limited to 10 attempts per IP per 15 minutes, separately
from login limits.

Existing accounts retain access, including legacy usernames. Operator
`create-user` and `reset-password` commands remain available for emergencies;
`create-user` does not automatically verify an email. Invitations cannot replace
existing accounts. This release does not add an admin UI or require 2FA.

### Account email delivery and verification

New accounts require an email address. Existing accounts keep their current
sign-in value after the migration, including older accounts created with a
username. No existing address is automatically considered verified. In Settings,
a signed-in user can verify their current email or enter a new one and confirm
the request with their password. The link expires after 24 hours and works only
once. A new address becomes the sign-in email only after verification; until
then, the current sign-in value continues to work. An invalid address cannot be
verified. Requests to resend are limited to once per minute per account.

Configure SMTP in the deployment environment file used by Compose (for the
homeserver example, `~/services/.env`). Keep the actual password out of the
repository:

```dotenv
NEXT_TASK_PUBLIC_APP_URL=https://tasks.example.com
NEXT_TASK_SMTP_HOST=smtp.example.com
NEXT_TASK_SMTP_PORT=587
NEXT_TASK_SMTP_SECURITY=starttls
NEXT_TASK_SMTP_USERNAME=your-smtp-username
NEXT_TASK_SMTP_PASSWORD=your-smtp-secret
NEXT_TASK_SMTP_FROM_EMAIL=tasks@example.com
```

`NEXT_TASK_PUBLIC_APP_URL` must be the fixed public HTTPS origin, with no path,
query, or fragment. HTTP is allowed only for `localhost`, `127.0.0.1`, and `::1`
when testing locally. It is never inferred from request headers. Use
`NEXT_TASK_SMTP_SECURITY=ssl` with the server's implicit TLS port if needed;
plaintext SMTP is not supported. Username and password can both be omitted for
an SMTP server that permits unauthenticated delivery over TLS. The same settings
work with a Google, self-hosted, or transactional SMTP server. SMTP settings are
optional until account email delivery is needed; password login continues to
work if the mail server is down.

After deployment, send an operator test message and confirm that it arrives in
the inbox (including the spam folder):

```bash
docker compose --env-file ../.env exec next-task uv run python -m app.cli test-email you@example.com
```

The command reports when the SMTP server accepts the message; inbox delivery
must be checked separately. Mail failures return an error to the user and log
the transport error type without logging credentials or verification links.
For a local trial, use `NEXT_TASK_PUBLIC_APP_URL=http://localhost:8000` in the
repository's ignored `.env`; Compose serves the app at that address.

### Password recovery

Use **Forgot password?** on the sign-in screen to request a reset link for the
account's verified email. Links expire after 30 minutes, work once, and are stored
only as hashes. A successfully sent replacement link supersedes the previous
one; a failed send leaves the previous link available until it expires.

The request always gives the same response for existing, unknown, and unverified
addresses. Address lookup and email delivery run after the HTTP response, so SMTP
timing and delivery errors do not disclose whether an account exists. Requests
are limited to 10 per IP and 3 per address in 15 minutes; exceeding the address
limit keeps the generic response. Reset attempts are limited to 10 per IP in
15 minutes. These limits persist in the database and do not lock password login.

A successful reset revokes all sessions, pending email changes, and outstanding
reset links, clears the account's password lockout, and sends a change
notification. The user must sign in with the new password. Password changes and
operator resets also invalidate outstanding recovery links; changing the verified
email invalidates links sent to the old address.

Delivery runs in the app process rather than a separate worker service. If the
process restarts before sending, request a new link. Mail failures are logged
without addresses, passwords, or links. A notification delivery failure does not
undo a successful password reset. Configure and check SMTP with the operator
`test-email` command before enabling recovery for users.

Older accounts without a verified email still need the operator reset command:

```bash
docker compose exec next-task uv run python -m app.cli reset-password existing-login
```

### Password login limits behind a proxy

Login attempts are counted in the SQLite database, so the limits survive app
restarts and are shared by app processes using the same database:

- Five failed passwords for one account within a rolling 15-minute window lock that account's
  password login for 15 minutes. The response stays the same generic 401 for a
  wrong password, an unknown account, and a temporarily locked account. A
  successful login clears that account's failure count.
- Each client IP gets 30 failed logins in a rolling 15-minute window, across all
  identifiers (including unknown ones). Successful logins do not consume this
  allowance. Further requests receive a generic 429 until enough failures age
  out of the window. Unknown accounts still run a dummy password check before
  the limit is reached.
- Each client IP can make 10 login requests in a rolling 10-second window,
  successful or failed. Further requests receive the same generic 429 before
  password verification. This is an app-level fallback for direct access and
  for deployments without an edge limit.
- Five failed current-password checks within 15 minutes temporarily prevent
  password changes for that account for 15 minutes. An admin CLI password reset
  clears both account limits. Limit records older than a day are removed on login.

The IP limit uses the client address that Uvicorn supplies after processing
`X-Forwarded-For` from a trusted proxy. In the homeserver Compose environment,
set `NEXT_TASK_TRUSTED_PROXY_IPS` to the **proxy container's source IP or CIDR**;
Compose passes it to Uvicorn as `FORWARDED_ALLOW_IPS`. Do not use the public
visitor IP or `*`. Keep port 8000 private to the proxy network, and configure
the proxy to append the actual connecting address to `X-Forwarded-For`. Direct
requests and headers from peers outside the trusted range are ignored for this
purpose. Without a trusted proxy setting, every visitor behind that proxy shares
the same IP limits. Uvicorn's trusted-proxy behavior is covered by the auth tests.

For Nginx, also limit bursts before they reach the app. Place the zone in the
Nginx `http` block:

```nginx
limit_req_zone $binary_remote_addr zone=next_task_login:10m rate=1r/s;
```

In the HTTPS `server` block, add an exact login location using the same upstream
and proxy headers as the existing app location:

```nginx
location = /api/auth/login {
    limit_req zone=next_task_login burst=9 nodelay;
    limit_req_status 429;
    proxy_pass http://next-task:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The Nginx bucket allows a short burst then refills at one request per second.
Set up Nginx's real-client-IP handling if another trusted proxy sits in front
of it. Validate the configuration with `nginx -t` before reloading Nginx.

After deployment, test through the public HTTPS address with a nonexistent
identifier: 10 rapid login requests from one client IP return generic 401;
request 11 returns 429. Wait at least 10 seconds, then submit 30 wrong passwords
spaced apart to reach the longer IP failure limit; the next request returns 429.
A request from another client network should still get 401. Use nonexistent
identifiers so this check does not lock a real account. The test suite also
verifies that changing `X-Forwarded-For` on an untrusted connection cannot evade
the limit.

Reset a password with direct server access:

```bash
docker compose --env-file ../.env exec next-task uv run python -m app.cli reset-password user@example.com
```

Existing sessions for that user are revoked. Both CLI commands accept
`--password-stdin` for controlled automation without putting a password in process
arguments. After signing in, create tasks and tags directly. Each account has one
task queue and one scoring formula.

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

Most revisions can be rolled back during development with `uv run alembic downgrade -1`.
The status-to-tag and workspace-removal migrations are one-way; restore a SQLite
backup if either needs to be undone.
Never replace migrations with `Base.metadata.create_all()` in production.

## Gemini text to task

Each user can add a personal Gemini API key in **Settings -> Gemini text to task**.
Users can select **+ New task**, enter natural
language in Quick Capture, choose **Text to task**, and review an editable task before
anything is created. The review includes title, Markdown description, priority,
due date, existing tags, and suggested new tags.

Quick Capture can also save text as a draft. Drafts are full task records that can keep
due date, hierarchy, tags, and other task metadata while remaining on
the dedicated **Drafts** page. **Save draft** keeps priority 0; **Save as task** assigns a
normal priority. Drafts are excluded from normal task lists, Next, and Pomodoro
until activated.

Drafting sends the entered text plus the user's tag
names to Gemini. The personal API key is encrypted in SQLite and is never returned to
the browser after it is saved. Server-side encryption requires a stable value of at least
32 characters:

```dotenv
NEXT_TASK_CREDENTIAL_SECRET=<random value kept outside Git>
```

Set it before the first API key is saved and keep it unchanged across deployments. If
it is lost or replaced, users must save their Gemini keys again.
Each user can choose a text model in Settings from the models Google lists for their
key. The selected model is saved per user and used for future drafts. Replacing or
removing the key resets the selection. `NEXT_TASK_GEMINI_MODEL` sets the server default
until a user chooses a model.

## Tags

Tags with different parents can share a name, such as `Work > Review` and
`Personal > Review`. Names must still be unique among tags with the same direct
parent, including top-level tags. When names repeat, the app adds parent context
to the displayed name, such as `Review (Work)`; the stored name stays `Review`.

## Scoring formulas

Scores are calculated when tasks are read and are not persisted. Available
variables are `priority`, `ageDays`, `idleDays`, `dueOffsetDays`, `hasDueDate`, and
`tagValue`. `tagValue` sums the score values of a task's direct tags and all their
parent tags, counting each tag once. Tag values can be edited on the **Tags** page.
`ageDays` counts time since creation. `idleDays` counts time since the task was last
worked, or since creation if it has never been worked. The default formula adds both,
so working on a task resets its idle contribution while its age keeps growing.
`hasDueDate` is `1` when a due date exists and `0` otherwise. The
`dueOffsetDays` value is negative before the due date, zero on the due date, and
positive after it. Formulas accept numbers, arithmetic, comparisons, boolean
operations, the `exp()` function, and Python-style conditional expressions.

The default formula is:

```text
priority * 25
+ ageDays * 0.25
+ idleDays * 1.00
+ tagValue * 20
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
