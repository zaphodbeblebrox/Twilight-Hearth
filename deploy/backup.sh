#!/usr/bin/env bash
# Nightly backup. Dumps the database locally, then copies dumps, photos and settings
# off-site when /etc/twilight-hearth/backup.env defines RESTIC_REPOSITORY.
# --local skips the off-site copy.
set -euo pipefail
umask 077
dir=/var/backups/twilight-hearth
offsite=/etc/twilight-hearth/backup.env
out=$dir/hearth-$(date +%Y%m%d-%H%M%S).dump
if [ -r "$offsite" ]; then set -a; . "$offsite"; set +a; fi

ping_hc() {
    if [ -n "${HC_PING_URL:-}" ]; then curl -fsS -m 10 --retry 3 -o /dev/null "$HC_PING_URL$1" || true; fi
}
trap 'ping_hc /fail' ERR

cd /
runuser -u twilight-hearth -- pg_dump -Fc twilight_hearth > "$out.part"
pg_restore --list "$out.part" > /dev/null
mv "$out.part" "$out"
find "$dir" -name 'hearth-*.dump*' -mtime +14 -delete
echo "Local backup: $out"
[ "${1:-}" = --local ] && exit 0

if [ -n "${RESTIC_REPOSITORY:-}" ]; then
    restic backup --quiet --host twilight-hearth --exclude "$offsite" \
        "$dir" /var/lib/twilight-hearth /etc/twilight-hearth
    restic forget --quiet --host twilight-hearth --group-by host \
        --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune
    echo "Off-site backup done"
    ping_hc ""
else
    echo "WARNING: off-site backup is not configured" >&2
fi
