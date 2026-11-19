#!/usr/bin/env bash
# Shared helpers of the developer scripts in scripts/. Sourced first by every script, never run.
# - The strict-mode convention: a script stops at the first failing command.
# - Output helpers, so every script and preflight check reports the same way.
# - compose: the one way to call docker compose, from the repo root whatever the caller's directory.
# - compose_up: the one way the app is started.
# - backend_cli: runs `python -m app.cli` in a one-off backend container. The scripts never parse
#   secrets/secrets.yaml themselves; whatever needs its values asks the backend, whose config module
#   is the file's only reader.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

info()    { printf '\033[1m%s\033[0m\n' "$*"; }
success() { printf '\033[32m✓\033[0m %s\n' "$*"; }
fail()    { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; }
hint()    { printf '  %s\n' "$*" >&2; }

compose() { (cd "$REPO_ROOT" && docker compose "$@"); }

# The frontend keeps its packages in an anonymous volume (see docker-compose.yml); renewing it on
# every start makes a rebuilt image's packages the ones in use.
compose_up() { compose up --build --renew-anon-volumes "$@"; }

backend_cli() { compose --progress quiet run --rm --no-deps -T backend python -m app.cli "$@"; }
