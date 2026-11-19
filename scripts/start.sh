#!/usr/bin/env bash
# Starts the app: the preflight checks, fresh frontend types, then every container in the
# foreground (Ctrl+C stops them all). The app runs at http://localhost:5173.
source "$(dirname "${BASH_SOURCE[0]}")/helpers/common.sh"
source "$REPO_ROOT/scripts/helpers/preflight.sh"

preflight_start
"$REPO_ROOT/scripts/helpers/generate-types.sh"

info "Starting the app at http://localhost:5173 (Ctrl+C stops it) ..."
compose_up
