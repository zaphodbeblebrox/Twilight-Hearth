#!/usr/bin/env bash
# Run a backend command as the app, with its settings. Example:
#   sudo twilight-hearth-run python -m app.cli invite --admin
set -euo pipefail
set -a; . /etc/twilight-hearth/app.env; set +a
cd "${TH_RELEASE:-/opt/twilight-hearth/current}/backend"
command=$1; shift
exec runuser -u twilight-hearth -- ".venv/bin/$command" "$@"
