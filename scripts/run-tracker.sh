#!/usr/bin/env bash
# Cron wrapper: runs the portal tracker on the VM.
# Maps .env names to what track.py expects and logs output.
set -euo pipefail
cd "$HOME/msft-career-tracker"
set -a
# shellcheck disable=SC1090
source .env
set +a
export TELEGRAM_TOKEN="$TELEGRAM_BOT_TOKEN"
export TELEGRAM_CHAT="$TELEGRAM_CHAT_ID"
python3 scripts/track.py >> state/track-cron.log 2>&1
