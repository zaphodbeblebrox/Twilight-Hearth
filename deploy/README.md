# Deployment

Twilight Hearth shares `twilight` with another app, so it has its own users, database,
ports and nginx site.

    Cloudflare Tunnel -> nginx 127.0.0.1:8110 -> uvicorn 127.0.0.1:8100 -> Postgres (socket)

| What | Where |
|---|---|
| Settings and secrets | `/etc/twilight-hearth/app.env` |
| Releases | `/opt/twilight-hearth/releases`, live one at `current` |
| Photos | `/var/lib/twilight-hearth/media` |
| Local backups (14 days) | `/var/backups/twilight-hearth` |

## First time

1. Copy this folder to the server and run `sudo bash setup.sh`. Run it again after
   changing anything in this folder.
2. `sudoedit /etc/twilight-hearth/app.env` and fill in the Google client id and secret.
   For importing photos and documents, also add `TH_ANTHROPIC_API_KEY`, from a workspace
   with prepaid credit and no auto-reload.
3. `sudo twilight-hearth-deploy`
4. In the Cloudflare tunnel, add public hostname `twilight-hearth.net` with service
   `http://localhost:8110`.
5. `sudo twilight-hearth-run python -m app.cli invite --admin` prints your invite.

## Everyday

    sudo twilight-hearth-deploy              # deploy main
    sudo systemctl restart twilight-hearth   # after changing app.env
    journalctl -u twilight-hearth -f
    sudo systemctl start twilight-hearth-backup
    sudo systemctl start twilight-hearth-restore-check

A deploy backs up the database, migrates, switches, and goes back to the previous code
if the new version is not healthy. Migrations are not undone, so keep each one
compatible with the previous version.

## Off-site backups

Create `/etc/twilight-hearth/backup.env` (root, mode 600), then run `restic init` with
those settings. Keep RESTIC_PASSWORD somewhere else too; backups are useless without it.

    RESTIC_REPOSITORY=
    RESTIC_PASSWORD=
    AWS_ACCESS_KEY_ID=
    AWS_SECRET_ACCESS_KEY=
    HC_PING_URL=
    HC_RESTORE_PING_URL=
