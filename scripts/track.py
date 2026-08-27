#!/usr/bin/env python3
"""Microsoft career portal (Phenom) application tracker.

Fetches the authenticated myapplications endpoint, snapshots statuses to
state/snapshot.json, diffs against the previous snapshot, and sends a
Telegram message for anything new/changed.

Env:
  PORTAL_COOKIE   raw Cookie header copied from DevTools (required)
  TELEGRAM_TOKEN  bot token from @BotFather
  TELEGRAM_CHAT   chat id from @userinfobot
"""

import json
import os
import sys
import time
from pathlib import Path

import urllib.request

STATE = Path(__file__).resolve().parent.parent / "state" / "snapshot.json"

# Phenom hosts Microsoft's portal. Adjust path if the endpoint changes.
API_URL = os.environ.get(
    "PORTAL_API_URL",
    "https://careers.microsoft.com/professionals/us/en/search-results",
)


def fetch():
    cookie = os.environ.get("PORTAL_COOKIE", "").strip()
    if not cookie:
        sys.exit("PORTAL_COOKIE not set")
    req = urllib.request.Request(API_URL)
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
    req.add_header("Accept", "application/json")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def extract_jobs(payload):
    """Normalize Phenom response into {job_id: {...}}.

    The exact shape varies; both common layouts are handled.
    """
    jobs = {}
    items = None
    if isinstance(payload, dict):
        data = payload.get("data") or payload
        for key in ("myApplicationsList", "jobs", "results", "list"):
            if isinstance(data, dict) and isinstance(data.get(key), list):
                items = data[key]
                break
            if isinstance(data.get(key), dict) and "list" in data[key]:
                items = data[key]["list"]
                break
        if items is None and isinstance(data, list):
            items = data
    if not isinstance(items, list):
        return None  # auth likely expired / layout changed

    for it in items:
        jid = str(it.get("reqId") or it.get("jobSeqNo")
                  or it.get("id") or it.get("title"))
        status = (it.get("status") or it.get("statusBag")
                  or it.get("workflowState") or "")
        if isinstance(status, dict):
            status = status.get("status") or json.dumps(status)
        jobs[jid] = {
            "title": it.get("title", ""),
            "location": it.get("location", "") or it.get("postedLocation", ""),
            "status": str(status),
            "updated": it.get("lastUpdatedDate") or it.get("appliedDate", ""),
        }
    return jobs


def diff(old, new):
    lines = []
    for jid in sorted(new):
        n = new[jid]
        if jid not in old:
            lines.append(f"🆕 NEW: {n['title']} ({n['location']}) -> {n['status']}")
        elif old[jid]["status"] != n["status"]:
            lines.append(f"🔁 {n['title']}:\n"
                         f"   {old[jid]['status']} ➜ {n['status']}")
    return lines


def telegram(text):
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT", "")
    if not (token and chat):
        print("Telegram not configured; skipping notify")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def main():
    payload = fetch()
    new = extract_jobs(payload)

    # Response that doesn't parse => probably logged out. Notify loudly.
    if new is None:
        telegram("⚠️ MS career tracker: could not parse portal response "
                 "(auth expired?). Refresh PORTAL_COOKIE secret.")
        prev_text = json.dumps(payload)[:300]
        (STATE.parent / "raw-last-response.txt").write_text(prev_text)
        sys.exit(1)

    old = {}
    if STATE.exists():
        try:
            old = json.loads(STATE.read_text())
        except Exception:
            pass

    changes = diff(old, new)
    summary = "\n".join(changes) if changes else None

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(new, indent=2))
    # CI audit trail of every check
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    log_path = STATE.parent / "history.log"
    with open(log_path, "a") as f:
        f.write(f"{stamp} apps={len(new)} changes={len(changes)}\n")

    if summary:
        telegram(f"📋 Microsoft portal update:\n\n{summary}")
        print(summary)
    else:
        print(f"No changes ({len(new)} applications tracked)")


if __name__ == "__main__":
    main()
