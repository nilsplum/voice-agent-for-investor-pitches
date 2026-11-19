#!/usr/bin/env bash
# Every preflight check of the developer scripts, each its own function, bundled once per script
# (preflight_setup, preflight_start, preflight_test). A failing check prints a high-level reason
# and a practical fix, then returns 1; because the scripts run with `set -e`, the first failing
# check stops them. The checks that need the secrets ask the backend (backend_cli), which prints
# the details itself. Sourced after common.sh, never run directly.

check_docker_installed() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker is not installed."
    hint "Install Docker Desktop (https://www.docker.com/products/docker-desktop/), start it, then run this script again."
    return 1
  fi
}

check_docker_running() {
  if ! docker info >/dev/null 2>&1; then
    fail "Docker is not running."
    hint "Start Docker Desktop, wait until it reports that it is running, then run this script again."
    return 1
  fi
  success "Docker is running"
}

check_secrets_file() {
  if [[ ! -f "$REPO_ROOT/secrets/secrets.yaml" ]]; then
    fail "secrets/secrets.yaml is missing."
    hint "Run ./scripts/setup.sh first. It creates the file and names the values to fill in."
    return 1
  fi
}

check_secrets_complete() {
  if ! backend_cli check-secrets; then
    fail "secrets/secrets.yaml is not complete."
    hint "Fill in the values named above in secrets/secrets.yaml."
    return 1
  fi
  success "Secrets are complete"
}

check_internet() {
  if ! backend_cli check-internet; then
    fail "The app cannot reach the internet."
    return 1
  fi
  success "Internet connection works"
}

check_openai_key() {
  if ! backend_cli check-openai-key; then
    fail "The OpenAI key does not work."
    return 1
  fi
  success "OpenAI key works"
}

check_serper_key() {
  if ! backend_cli check-serper-key; then
    fail "The Serper key does not work."
    return 1
  fi
  success "Serper key works"
}

preflight_setup() {
  check_docker_installed
  check_docker_running
}

preflight_start() {
  check_docker_installed
  check_docker_running
  check_secrets_file
  check_secrets_complete
  check_internet
  check_openai_key
  check_serper_key
}

# Usage: preflight_test [--complete]. The keys are needed only by the tests against the real APIs.
preflight_test() {
  check_docker_installed
  check_docker_running
  check_secrets_file
  if [[ "${1:-}" == "--complete" ]]; then
    check_secrets_complete
    check_internet
    check_openai_key
    check_serper_key
  fi
}
