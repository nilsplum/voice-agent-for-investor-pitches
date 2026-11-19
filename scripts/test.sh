#!/usr/bin/env bash
# The one entry point of the test suite: everything runs in the containers, against the app's exact
# dependencies. Parts: the backend tests (pytest with a real PostgreSQL; the outside APIs are faked)
# and the frontend checks (the type check against freshly generated types, then the unit tests of the
# conversation logic with Vitest). It stops at the first failing part.
# With --complete, the tests against the real OpenAI and Serper APIs run as well (they need both
# keys and cost a little), and finally the voice conversation: the real app in a real Chrome with
# recorded founder answers (see e2e/test_voice_conversation.py).
source "$(dirname "${BASH_SOURCE[0]}")/helpers/common.sh"
source "$REPO_ROOT/scripts/helpers/preflight.sh"

COMPLETE=""
for arg in "$@"; do
  case "$arg" in
    --complete) COMPLETE="--complete" ;;
    *) fail "Unknown option: $arg"; hint "Usage: ./scripts/test.sh [--complete]"; exit 2 ;;
  esac
done

run_part() {
  local name="$1"
  shift
  info "$name ..."
  if ! "$@"; then
    fail "$name failed (see above)."
    exit 1
  fi
  success "$name passed"
}

# The voice conversation starts the app like start.sh, but in the background (so a running start.sh
# must be stopped first), and stops it again however the test ends. Its founder signs up with a new
# code for a new email; the founder and the conversation stay in the database, like real ones. The
# OpenAI key (for the founder's recorded voice) goes from the backend's CLI into a variable and the
# test container's environment, never into a file. Afterwards the backend's reply time lines of this
# run are printed.
voice_conversation() {
  local since email code key status=0
  compose_up -d --wait || return 1
  trap 'compose stop >/dev/null 2>&1' EXIT
  since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  email="e2e-$(date +%s)@example.com"
  code="$(backend_cli create-access-code "$email")" || return 1
  key="$(backend_cli print-openai-key)" || return 1
  OPENAI_API_KEY="$key" E2E_EMAIL="$email" E2E_CODE="$code" compose --profile e2e run --rm --build e2e || status=$?
  info "Reply times of this conversation (from the backend's log):"
  compose logs --no-color --since "$since" backend | grep -o "event=reply_time.*" || true
  return "$status"
}

preflight_test $COMPLETE
"$REPO_ROOT/scripts/helpers/generate-types.sh"
# compose starts the database first, because the backend depends on it.
run_part "Backend tests" compose run --rm backend pytest $COMPLETE
run_part "Frontend checks" compose run --rm --no-deps frontend npm run check
if [[ -n "$COMPLETE" ]]; then
  run_part "Voice conversation" voice_conversation
fi
success "All tests passed."
