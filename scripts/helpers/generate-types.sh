#!/usr/bin/env bash
# Regenerates frontend/src/api/types.ts from the backend's OpenAPI schema, so the frontend's types
# always follow the backend's Pydantic models. Run by start.sh and test.sh; test.sh then type-checks
# the frontend against the result. The regenerated file is committed with the change that caused it.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

info "Generating the frontend types from the backend's API ..."
backend_cli openapi > "$REPO_ROOT/frontend/src/api/.openapi.json"
compose --progress quiet run --rm --no-deps -T frontend npm run --silent types
