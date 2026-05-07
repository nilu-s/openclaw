#!/usr/bin/env bash
set -euo pipefail

# Stable CI runner: disables ambient pytest plugins that can keep background
# telemetry/event-loop threads alive after tests have passed.
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-1}
export NEXUSCTL_TIMEOUT_SECONDS=${NEXUSCTL_TIMEOUT_SECONDS:-2}
export NEXUSCTL_AUTH_TIMEOUT_SECONDS=${NEXUSCTL_AUTH_TIMEOUT_SECONDS:-2}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR/.."

if command -v timeout >/dev/null 2>&1; then
  timeout ${NEXUSCTL_TEST_SUITE_TIMEOUT:-180s} python -m pytest "$@"
else
  python -m pytest "$@"
fi
