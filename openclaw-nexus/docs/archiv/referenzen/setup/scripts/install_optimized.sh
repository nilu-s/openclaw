#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
WORKSPACE_ROOT="${OPENCLAW_WORKSPACE_ROOT:-/workspace}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$OPENCLAW_HOME" "$WORKSPACE_ROOT"

if [ -f "$OPENCLAW_HOME/openclaw.json" ]; then
  cp "$OPENCLAW_HOME/openclaw.json" "$OPENCLAW_HOME/openclaw.json.bak.$STAMP"
fi

cp "$ROOT/config/openclaw.json" "$OPENCLAW_HOME/openclaw.json"
mkdir -p "$OPENCLAW_HOME/agents" "$WORKSPACE_ROOT/skills" "$WORKSPACE_ROOT/tools" "$WORKSPACE_ROOT/profiles" "$WORKSPACE_ROOT/nexusctl"
rsync -a --delete "$ROOT/agents/" "$OPENCLAW_HOME/agents/"
rsync -a --delete "$ROOT/skills/" "$WORKSPACE_ROOT/skills/"
rsync -a --delete "$ROOT/tools/" "$WORKSPACE_ROOT/tools/"
rsync -a --delete "$ROOT/profiles/" "$WORKSPACE_ROOT/profiles/"
rsync -a --delete "$ROOT/nexusctl/" "$WORKSPACE_ROOT/nexusctl/"

python3 "$ROOT/scripts/validate_optimized_setup.py" "$ROOT"

echo "Installed optimized OpenClaw/Nexusctl setup. Backup stamp: $STAMP"
echo "Next: run openclaw config schema or openclaw doctor if available, then restart the gateway."
