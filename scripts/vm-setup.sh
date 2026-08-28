#!/usr/bin/env bash
# One-time setup for the MS portal keep-alive on an Ubuntu/Debian VM.
# Run as your normal user (needs sudo for installing gh + cron entry).

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/msft-career-tracker}"
KEEPALIVE_SRC="$(cd "$(dirname "$0")" && pwd)/keepalive.sh"

echo "==> Installing gh CLI if missing"
if ! command -v gh >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq curl
  curl -sS https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
    sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
    sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  sudo apt-get update -qq && sudo apt-get install -y -qq gh
fi

echo "==> Authenticating gh (one-time, interactive)"
gh auth status >/dev/null 2>&1 || gh auth login

echo "==> Installing repo folder + keepalive script"
mkdir -p "$REPO_DIR/scripts" "$REPO_DIR/state"
cp "$KEEPALIVE_SRC" "$REPO_DIR/scripts/keepalive.sh"
chmod +x "$REPO_DIR/scripts/keepalive.sh"

echo "==> Copying .env (cookie/csrf/ua/telegram) from this Mac"
if [ -f "$REPO_DIR/.env" ]; then
  echo "    .env already exists on VM, skipping copy"
else
  echo "    transfer it now:  scp ~/Downloads/msft-career-tracker/.env vm:$REPO_DIR/.env"
  exit 1
fi

echo "==> Installing cron job (every 20 min)"
CRON_LINE="*/20 * * * * $REPO_DIR/scripts/keepalive.sh"
( crontab -l 2>/dev/null | grep -v msft-career-tracker; echo "$CRON_LINE" ) | crontab -
crontab -l | grep msft-career-tracker

echo "==> Test run"
bash "$REPO_DIR/scripts/keepalive.sh" && tail -1 "$REPO_DIR/state/keepalive.log"
echo "DONE. Keep-alive now runs on this VM every 20 minutes."