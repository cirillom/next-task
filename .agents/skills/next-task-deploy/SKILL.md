---
name: next-task-deploy
description: Deploy, inspect, or roll back Next Task on vmstudas. Use for production image, rootless Docker Compose, environment secrets, database migration, notifier, or health-check work in this repository.
---

# Next Task deployment on vmstudas

The VM facts below were checked on 2026-11-23. Recheck them before acting; the repository's `docker-compose.example.yml` and README describe a reference setup and do not match the live Compose file.

## Layout and release path

- `ssh vmstudas` connects as `cirillo`. The Compose project is `/home/cirillo/services/next-task`; use `/usr/bin/docker --context rootless compose` there. The web service is `app` (container `next-task`), and the worker is `notifier` (container `next-task-notifier`). Use service names with `compose exec`.
- The live `compose.yml` and `.env` are mode `0600`. Compose loads `.env` with `env_file: {path: .env, format: raw}`. The persistent SQLite database is mounted from `./data` to `/data`; rootless UID mapping can prevent host-side reads of `data`.
- The app starts with `uv run alembic upgrade head`. The notifier starts only after the app is healthy and runs `uv run python -m app.notifier`. Both need the same VAPID key and public URL. The public origin is `https://next.studas.com.br`; the VM-local health URL is `http://127.0.0.1:18000/api/health`.
- `.github/workflows/release.yml` validates `main` and publishes versioned and `latest` images to `ghcr.io/cirillom/next-task`. A merged PR, published image, and VM deployment are separate outcomes. Inspect each; do not infer one from another or merge/release merely because a deployment was requested.
- On 2026-11-23 the VM uses a locally built, pinned image `next-task:notifications-8aafd5ef` for both services. The private `/home/cirillo/.local/bin/next-task update` command runs `compose pull` before `up`, so it cannot update this local-only tag. Before using that command again, publish the intended code and switch the VM Compose image back to a pullable GHCR tag; verify the switch will not revert notifications.

## Deploy safely

1. Read `AGENTS.md`, `jj st`, the intended revision, Dockerfile, migration files, and live Compose state. Use the user's requested release boundary. Check app and worker image provenance before replacing either service.
2. Inspect the VM without printing secrets: check `compose ps`, service names, image IDs, `.env` permission and key *names*, database revision, and health. Avoid `docker compose config` output and raw `docker inspect` output because they contain environment values; use `compose config --quiet` and targeted checks instead.
3. Prefer the published release image when that is the authorized artifact. For unreleased code, build an explicitly tagged image from the intended Jujutsu/Git revision. If transferring a source archive, verify it excludes `.env`, use exact source and destination filenames, and build with rootless Docker. Never pull `latest` as a substitute for unreleased changes.
4. Stage environment changes in a distinct mode-`0600` file. Preserve the existing `NEXT_TASK_CREDENTIAL_SECRET` byte-for-byte; changing it can make saved credentials unreadable. Keep SMTP passwords and `NEXT_TASK_VAPID_PRIVATE_KEY` out of Git, logs, and tool output. A local `.env` may contain `localhost` or sample values: set the production HTTPS URL and a valid VAPID subject for the VM. When transferring a local `.env`, specify the full remote staging filename; copying it to the project directory overwrites the live `.env`.
5. Before any migration, create an online SQLite backup with Python's `sqlite3.Connection.backup` inside the running app container and check `PRAGMA quick_check` on source and backup. Back up the current `.env` and `compose.yml` with mode `0600`. Validate the staged Compose file, then start the app and notifier with the intended image. For a local-only tag, use `compose up -d --pull never`; for a published tag, pull that tag first.
6. Verify both containers remain running, the app is healthy, `alembic current` is at the expected revision, and the database passes `PRAGMA quick_check`. Check the public HTTPS health route, `/sw.js`, authentication on the notifications API, worker logs and restart count, and worker outbound HTTPS connectivity. Confirm both containers received the intended settings without printing values. A push was delivered only if a subscribed device actually received it.
7. Remove staged source and secret files by their exact names. Keep rollback backups until the deployment is accepted. Do not recursively delete wildcard-matched pytest directories or unrelated VM files. If rollback is needed, inspect the migration and database state before restoring a backup; do not assume a schema downgrade is safe.

Report the deployed image/revision, app and worker status, migration, health checks, backup location, and any unverified device delivery or update-command limitation.
