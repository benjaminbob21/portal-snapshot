#!/usr/bin/env bash
# Cron wrapper: runs the portal tracker on the VM every ~15 min, captures
# the rotated session cookie locally (no repo / GH secret dependency),
# and logs to state/track-cron.log.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

mkdir -p state
ENV_FILE="$PWD/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found" >> state/track-cron.log
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC') ===" >> state/track-cron.log
python3 scripts/track.py >> state/track-cron.log 2>&1 || true

if [ -f state/rotated-session.txt ]; then
  new_sess=$(cat state/rotated-session.txt)
  if [ -n "$new_sess" ]; then
    python3 - "$ENV_FILE" "$new_sess" <<'PYEOF'
import sys, re
from pathlib import Path

env_file, new_sess = sys.argv[1], sys.argv[2]
path = Path(env_file)
content = path.read_text()

m = re.search(r'PORTAL_COOKIE="([^"]+)"', content)
if m:
    old_cookie = m.group(1)
    new_cookie = re.sub(r'session=[^;]+', f'session={new_sess}', old_cookie)
    content = content[:m.start(1)] + new_cookie + content[m.end(1):]
    path.write_text(content)
    print("Updated PORTAL_COOKIE in .env with rotated session")
PYEOF
  fi
  rm -f state/rotated-session.txt
fi
