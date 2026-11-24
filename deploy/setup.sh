#!/usr/bin/env bash
# One-time server setup. Safe to run again; never overwrites app.env. Run as root.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
UV_VERSION=0.13.9

# The app runs as one user; builds (which run third-party code) as another
# that cannot read the app's secrets or data.
id twilight-hearth >/dev/null 2>&1 || useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin twilight-hearth
id thbuild >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/thbuild --shell /usr/sbin/nologin thbuild

install -d -o root -g root -m 755 /opt/twilight-hearth /opt/twilight-hearth/releases
install -d -o root -g root -m 700 /etc/twilight-hearth /var/backups/twilight-hearth
install -d -o twilight-hearth -g twilight-hearth -m 750 /var/lib/twilight-hearth

if ! /usr/local/bin/uv --version 2>/dev/null | grep -q "uv $UV_VERSION "; then
    tmp=$(mktemp -d)
    base=https://github.com/astral-sh/uv/releases/download/$UV_VERSION
    (cd "$tmp" && curl -fsSLO "$base/uv-x86_64-unknown-linux-gnu.tar.gz" &&
        curl -fsSLO "$base/uv-x86_64-unknown-linux-gnu.tar.gz.sha256" &&
        sha256sum -c uv-x86_64-unknown-linux-gnu.tar.gz.sha256 &&
        tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz --strip-components=1 &&
        install -m 755 uv /usr/local/bin/uv)
    rm -rf "$tmp"
fi

# The database user signs in as the matching system user, so there is no password.
cd /
psql() { runuser -u postgres -- /usr/bin/psql -v ON_ERROR_STOP=1 -Atqc "$1" "${@:2}"; }
[ "$(psql "select 1 from pg_roles where rolname='twilight-hearth'")" ] || psql 'create role "twilight-hearth" login'
[ "$(psql "select 1 from pg_database where datname='twilight_hearth'")" ] || psql 'create database twilight_hearth owner "twilight-hearth"'
psql 'revoke connect on database twilight_hearth from public'

if [ ! -e /etc/twilight-hearth/app.env ]; then
    umask 077
    cat > /etc/twilight-hearth/app.env <<ENV
TH_ENV=production
TH_PUBLIC_URL=https://twilight-hearth.net
TH_DATABASE_URL=postgresql+psycopg:///twilight_hearth?host=/var/run/postgresql
TH_MEDIA_DIR=/var/lib/twilight-hearth/media
TH_SECRET_KEY=$(openssl rand -hex 32)
TH_GOOGLE_CLIENT_ID=REPLACE_ME
TH_GOOGLE_CLIENT_SECRET=REPLACE_ME
ENV
fi

install -m 644 "$here"/twilight-hearth*.service "$here"/twilight-hearth*.timer /etc/systemd/system/
install -m 755 "$here/backup.sh" /usr/local/sbin/twilight-hearth-backup
install -m 755 "$here/restore-check.sh" /usr/local/sbin/twilight-hearth-restore-check
install -m 755 "$here/deploy.sh" /usr/local/sbin/twilight-hearth-deploy
install -m 755 "$here/run.sh" /usr/local/sbin/twilight-hearth-run
systemctl daemon-reload

install -m 644 "$here/nginx-headers.conf" /etc/nginx/snippets/twilight-hearth-headers.conf
install -m 644 "$here/nginx-proxy.conf" /etc/nginx/snippets/twilight-hearth-proxy.conf
install -m 644 "$here/nginx.conf" /etc/nginx/sites-available/twilight-hearth
ln -sfn ../sites-available/twilight-hearth /etc/nginx/sites-enabled/twilight-hearth
if ! nginx -t; then
    # Never leave the shared nginx unable to restart.
    rm /etc/nginx/sites-enabled/twilight-hearth
    exit 1
fi
systemctl reload nginx
