#!/usr/bin/env bash
# Keep-alive: refresh the Microsoft portal session cookie and update the
# GitHub secret so CI keeps working. Designed to run on Bob's Mac every
# 20 minutes via launchd (com.bob.msft-portal-keepalive.plist).
#
# Requires: gh authenticated (gh auth login), and .env in the repo folder
# with PORTAL_API_URL, PORTAL_COOKIE, PORTAL_CSRF, PORTAL_UA.

set -euo pipefail

REPO_DIR="$HOME/Downloads/msft-career-tracker"
ENV_FILE="$REPO_DIR/.env"
REPO="benjaminbob21/msft-career-tracker"
LOG="$REPO_DIR/state/keepalive.log"

log() { echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') $*" >> "$LOG"; }

cd "$REPO_DIR"

# Load current env values
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# 1. Ping the applications endpoint with the current session.
http_code=$(curl -s -o /tmp/ka-body.json -w "%{http_code}" "$PORTAL_API_URL" \
  -H "Cookie: $PORTAL_COOKIE" \
  -H "x-csrf-token: $PORTAL_CSRF" \
  -H "user-agent: $PORTAL_UA" \
  -H "accept: application/json" \
  --max-time 30)

if [ "$http_code" != "200" ]; then
  log "PING FAILED http=$http_code — session dead, needs manual re-login"
  exit 1
fi

# 2. Capture the rotated session cookie the portal hands back.
new_session=$(curl -s -D - -o /dev/null "$PORTAL_API_URL" \
  -H "Cookie: $PORTAL_COOKIE" \
  -H "x-csrf-token: $PORTAL_CSRF" \
  -H "user-agent: $PORTAL_UA" \
  -H "accept: application/json" \
  --max-time 30 | tr -d '\r' | awk -F'session=' '/^[Ss]et-[Cc]ookie:.*session=/{print $2}' | cut -d';' -f1 | head -1)

if [ -z "$new_session" ]; then
  log "no rotated session cookie returned — keeping existing one (still valid)"
  exit 0
fi

# 3. Swap the session pair in the cookie string.
new_cookie=$(python3 - "$PORTAL_COOKIE" "$new_session" <<'EOF'
import sys
cookie, new_sess = sys.argv[1], sys.argv[2]
pairs = cookie.split('; ')
replaced = False
for i, p in enumerate(pairs):
    if p.startswith('session='):
        pairs[i] = 'session=' + new_sess
        replaced = True
if not replaced:
    pairs.append('session=' + new_sess)
print('; '.join(pairs))
EOF
)

# 4. Write back to .env (only the cookie changes; csrf stays stable)
python3 - "$ENV_FILE" "$new_cookie" <<'EOF'
import sys
from pathlib import Path
env_file, new_cookie = sys.argv[1], sys.argv[2]
text = Path(env_file).read_text()
import re
text = re.sub(r'PORTAL_COOKIE=".*?"', 'PORTAL_COOKIE="' + new_cookie + '"',
              text, flags=re.S)
Path(env_file).write_text(text)
EOF

# 5. Push the fresh cookie to the GitHub secret.
export PORTAL_COOKIE="$new_cookie"
if gh secret set PORTAL_COOKIE --repo "$REPO" --body "$PORTAL_COOKIE"; then
  log "refreshed session cookie + updated GitHub secret (old expiry pushed out)"
else
  log "cookie refreshed locally but GitHub secret update FAILED"
  exit 1
fi
