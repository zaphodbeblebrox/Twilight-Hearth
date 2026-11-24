#!/usr/bin/env bash
# Build and switch to a version: sudo twilight-hearth-deploy [git-ref, default main]
# Only code changes are rolled back on failure; migrations must stay compatible with
# the previous version.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run with sudo" >&2; exit 1; }
exec 9>/run/twilight-hearth-deploy.lock
flock -n 9 || { echo "Another deploy is running" >&2; exit 1; }

ref=${1:-main}
repo=https://github.com/zaphodbeblebrox/Twilight-Hearth.git
root=/opt/twilight-hearth
work=$(mktemp -d /var/lib/thbuild/build.XXXXXX)
trap 'rm -rf "$work"' EXIT
chown thbuild: "$work"
as_build() { runuser -u thbuild -- env -i HOME=/var/lib/thbuild PATH=/usr/local/bin:/usr/bin:/bin "$@"; }

cd "$work"
as_build git init -q src
cd src
as_build git fetch -q --depth 1 "$repo" "$ref"
as_build git checkout -q FETCH_HEAD
sha=$(as_build git rev-parse --short=12 HEAD)
release=$root/releases/$(date +%Y%m%d%H%M%S)-$sha
echo "Building $ref at $sha"

(cd frontend && as_build npm ci --no-audit --no-fund && as_build npm run build)
rm -rf .git frontend/node_modules
# Root owns the release, so neither the build user nor the app can change running code.
cp -r --no-preserve=ownership . "$release"
# Built at its final path because virtual environments cannot be moved.
install -d -o thbuild "$release/backend/.venv"
(cd "$release/backend" && as_build uv sync -q --frozen --no-dev --no-cache --no-managed-python \
    --python /usr/bin/python3 --link-mode copy)
chown -R root:root "$release"
chmod -R u=rwX,go=rX "$release"

if [ -e "$root/current" ]; then
    /usr/local/sbin/twilight-hearth-backup --local
fi
TH_RELEASE=$release /usr/local/sbin/twilight-hearth-run alembic upgrade head

previous=$(readlink "$root/current" || true)
ln -sfn "$release" "$root/current.new"
mv -T "$root/current.new" "$root/current"

healthy() {
    for _ in $(seq 20); do
        curl -fsS -m 2 -o /dev/null http://127.0.0.1:8100/api/health 2>/dev/null && return 0
        sleep 1
    done
    return 1
}
systemctl restart twilight-hearth || true
if ! healthy; then
    echo "New version is not healthy" >&2
    journalctl -u twilight-hearth -n 20 --no-pager >&2
    if [ -n "$previous" ]; then
        ln -sfn "$previous" "$root/current.new"
        mv -T "$root/current.new" "$root/current"
        systemctl restart twilight-hearth
        echo "Went back to $previous" >&2
    else
        systemctl stop twilight-hearth
    fi
    exit 1
fi
systemctl enable -q twilight-hearth
systemctl enable -q --now twilight-hearth-backup.timer twilight-hearth-restore-check.timer
ls -1d "$root"/releases/* | sort | head -n -5 | while read -r old; do
    [ "$old" = "$previous" ] || rm -rf "$old"
done
echo "Running $release"
