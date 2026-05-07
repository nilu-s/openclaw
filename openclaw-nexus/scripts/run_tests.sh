#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "python or python3 is required to run OpenClaw Nexus tests" >&2
    exit 127
  fi
fi

MODE="unit"
if [[ $# -gt 0 ]]; then
  case "$1" in
    smoke|fast|unit|integration|slow|timeout-risk|all|debug|ci)
      MODE="$1"
      shift
      ;;
    -*|tests|tests/*|nexusctl/tests|nexusctl/tests/*|./tests/*|./nexusctl/tests/*)
      MODE="unit"
      ;;
    *)
      echo "Usage: $0 [smoke|fast|unit|integration|slow|timeout-risk|all|debug|ci] [pytest args...]" >&2
      exit 2
      ;;
  esac
fi

"$PYTHON_BIN" scripts/validate_project.py

PYTEST_ARGS=("--basetemp" "${PYTEST_BASETEMP:-/tmp/openclaw-nexus-pytest}")
PYTHON_OPTS=()

case "$MODE" in
  smoke)
    PYTEST_ARGS+=("tests/test_archive_policy.py" "tests/test_blueprint_contract.py" "tests/test_policy_contract.py" "tests/test_test_strategy.py" "tests/test_package_contract.py" "-q" "--durations=15")
    ;;
  fast|unit)
    PYTEST_ARGS+=("-m" "not integration and not slow and not timeout_risk" "--durations=25")
    ;;
  integration)
    PYTEST_ARGS+=("-m" "integration" "-vv" "--durations=50")
    ;;
  slow)
    PYTEST_ARGS+=("-m" "slow" "-vv" "-s" "--durations=50")
    ;;
  timeout-risk)
    PYTEST_ARGS+=("-m" "timeout_risk" "-vv" "-s" "--durations=50")
    ;;
  all)
    PYTEST_ARGS+=("--durations=50")
    ;;
  debug)
    export PYTHONFAULTHANDLER=1
    PYTHON_OPTS+=("-X" "faulthandler")
    PYTEST_ARGS+=("-vv" "-s" "--full-trace" "--durations=50")
    ;;
  ci)
    PYTEST_ARGS+=("--strict-markers" "--durations=50")
    ;;
  *)
    echo "Unsupported test mode: $MODE" >&2
    exit 2
    ;;
esac

PYTEST_ARGS+=("$@")

export PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-1}"
export PYTHONPATH="nexusctl/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$MODE" == "timeout-risk" ]]; then
  if ! "$PYTHON_BIN" - <<'PY'
from conftest import TIMEOUT_RISK_TESTS
raise SystemExit(0 if TIMEOUT_RISK_TESTS else 1)
PY
  then
    echo "No timeout-risk tests are currently registered."
    exit 0
  fi
fi

echo "Running pytest mode: $MODE"
echo "Command: $PYTHON_BIN ${PYTHON_OPTS[*]} -m pytest ${PYTEST_ARGS[*]}"

exec "$PYTHON_BIN" "${PYTHON_OPTS[@]}" -m pytest "${PYTEST_ARGS[@]}"
