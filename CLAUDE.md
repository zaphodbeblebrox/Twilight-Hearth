# Claude instructions for Twilight Hearth

## Always ship app changes to the server

Whenever a task changes the app (backend, frontend, migrations, deploy files,
dependencies), finish it by deploying to production. The user has given standing
approval for this, so do it without asking:

1. **Test first. Nothing is pushed or deployed until this passes.**
   - **Add or update tests** in `backend/tests` whenever the change has testable logic.
   - **Backend**, in `backend/`: `uv run pytest` must show no failures and
     `uv run ruff check .` must be clean. Tests use a throwaway Postgres. Never point
     them at the live database.
   - **Migrations:** after changing `app/models.py`, add one with
     `uv run alembic revision --autogenerate`, review it, and make sure
     `uv run alembic upgrade head` and `uv run alembic check` pass. Each migration must
     work with the previous version of the code, because a failed deploy goes back to
     the old code but does not undo migrations.
   - **API types:** after changing the API, regenerate `frontend/openapi.json` and
     `frontend/src/schema.d.ts` as described in [README.md](README.md).
   - **Frontend**, in `frontend/`: `npm ci` if dependencies changed, then
     `npm run build` (typecheck and build) must succeed. There are no frontend unit
     tests yet. For visible changes, also check them in a browser.
     If Node is not installed locally, build in a scratch clone at `~/hearth-verify` on
     the server (reset it to `origin/main`, then `git apply` the diff, using `git add -N`
     so new files are included). Never build in `/opt/twilight-hearth`.
   - **Known baseline (2026-11-24):** backend 61/61. Any failure, or a drop in the
     count without a reason, blocks the deploy. Fix it first.
2. **Commit** on `main` with a clear message, then `git push origin main`.
3. **Deploy:** `ssh twilight "sudo twilight-hearth-deploy"`. It backs up the database,
   builds `main`, migrates, switches, and goes back if the new version is unhealthy.
   If anything in `deploy/` changed, first copy that folder to
   `~/twilight-hearth-deploy` on the server and run
   `ssh twilight "sudo bash ~/twilight-hearth-deploy/setup.sh"`.
4. **Confirm** that `systemctl is-active twilight-hearth nginx` is active,
   `https://twilight-hearth.net/api/health` answers, and `https://twilight-scribe.net`
   still answers. Then report the deployed commit.

If any step fails, stop and report it with the output instead of pushing a broken
build. Changes that don't touch the app (docs, research, answering questions) don't
need a deploy.

## Shared server

`twilight` also runs the live app Twilight Scribe. Never change its files, database,
services, ports (80, 8000, 8080), tunnel route or backups.

This repository is public. Never commit secrets, personal information, or anything from
`/etc/twilight-hearth`.

## Design

[docs/PLAN.md](docs/PLAN.md) holds the decisions and [deploy/README.md](deploy/README.md)
the server layout. All reads of recipes and images go through `app/permissions.py`, and
revisions are never edited. If a change affects what is collected or who can see it,
update `frontend/public/privacy.html` in the same change.

Long remote scripts: write them to the scratchpad and run
`ssh twilight "bash -s" < file`.
