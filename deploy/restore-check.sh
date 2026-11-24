#!/usr/bin/env bash
# Prove that a backup can be restored, using a throwaway database.
# Uses the newest off-site copy when configured, or the newest local dump.
set -euo pipefail
umask 077
scratch=twilight_hearth_restore_check
tmp=$(mktemp -d)
cd /
cleanup() {
    runuser -u postgres -- dropdb --if-exists "$scratch"
    rm -rf "$tmp"
}
trap cleanup EXIT
source=/var/backups/twilight-hearth
if [ -r /etc/twilight-hearth/backup.env ]; then set -a; . /etc/twilight-hearth/backup.env; set +a; fi
if [ -n "${RESTIC_REPOSITORY:-}" ]; then
    restic restore latest --quiet --host twilight-hearth --target "$tmp"
    source=$tmp/var/backups/twilight-hearth
fi
dump=$(ls -1 "$source"/hearth-*.dump | sort | tail -1)
runuser -u postgres -- dropdb --if-exists "$scratch"
runuser -u postgres -- createdb "$scratch"
runuser -u postgres -- pg_restore --exit-on-error --no-owner -d "$scratch" < "$dump"
query() { runuser -u postgres -- psql -v ON_ERROR_STOP=1 -Atqc "$1" "$scratch"; }
version=$(query 'select version_num from alembic_version')
[ -n "$version" ]
if [ -n "${RESTIC_REPOSITORY:-}" ]; then
    query 'select id from images' | while read -r id; do
        [ -s "$tmp/var/lib/twilight-hearth/media/$id.webp" ] || { echo "Missing photo $id" >&2; exit 1; }
    done
fi
echo "Restored $(basename "$dump"): schema $version, $(query 'select count(*) from recipes') recipes, $(query 'select count(*) from users') users"
if [ -n "${HC_RESTORE_PING_URL:-}" ]; then curl -fsS -m 10 -o /dev/null "$HC_RESTORE_PING_URL" || true; fi
