#!/usr/bin/env python3
"""Microsoft career portal tracker for apply.careers.microsoft.com (pcsx API).

Watches:
  - /api/pcsx/dashboard/summary       -> the six tile counts
  - /api/pcsx/dashboard/applications  -> per-application entries

Snapshots to state/snapshot.json, diffs against the previous run, and sends a
Telegram message on any change (e.g. Applications 1 -> 2, status updates).

Env:
  PORTAL_COOKIE   raw cookie string from the browser session (required)
  PORTAL_CSRF     x-csrf-token from the same request (required)
  PORTAL_UA       user-agent of the browser used to capture the cookie
  TELEGRAM_TOKEN  bot token from @BotFather
  TELEGRAM_CHAT   chat id
"""

import json
import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / "state" / "snapshot.json"

BASE = "https://apply.careers.microsoft.com"
SUMMARY_URL = BASE + "/api/pcsx/dashboard/summary"
APPLICATIONS_URL = BASE + "/api/pcsx/dashboard/applications"

# Tile label -> summary key
TILE_KEYS = {
    "Applications": "applications",
    "Interviews": "interviews",
    "Saved Jobs": "savedpositions",
    "Events": "events",
    "Forms manager": "forms",
    "Offers": "offers",
}

DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 "
              "Safari/605.1.15")


def _get_json(url):
    cookie = os.environ.get("PORTAL_COOKIE", "").strip()
    csrf = os.environ.get("PORTAL_CSRF", "").strip()
    if not cookie or not csrf:
        sys.exit("PORTAL_COOKIE / PORTAL_CSRF not set")
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookie)
    req.add_header("x-csrf-token", csrf)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", os.environ.get("PORTAL_UA") or DEFAULT_UA)
    req.add_header("Referer", BASE + "/careers/dashboard"
                                  "?domain=microsoft.com&hl=en")
    ctx = ssl.create_default_context()
    if not ctx.get_ca_certs():
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        payload = json.load(r)
    if not isinstance(payload, dict) or payload.get("status") != 200:
        raise RuntimeError(f"unexpected response from {url}: "
                           f"{str(payload)[:200]}")
    return payload.get("data") or {}


def fetch_summary():
    data = _get_json(SUMMARY_URL)
    counts = (data.get("count") or {})
    tiles = {}
    for label, key in TILE_KEYS.items():
        entry = counts.get(key) or {}
        tiles[label] = {
            "total": entry.get("totalCount", 0),
            "actionable": entry.get("actionableItemsCount", 0),
        }
    return tiles


def fetch_applications():
    data = _get_json(APPLICATIONS_URL)
    items = data.get("applications") or []
    apps = {}
    for it in items:
        aid = str(it.get("applicationId") or it.get("pid") or it.get("displayJobId"))
        apps[aid] = {
            "title": it.get("positionTitle", ""),
            "location": it.get("positionLocation", ""),
            "status": it.get("currentStatus", ""),
            "applied_on": it.get("appliedOn", ""),
            "withdrawn": bool(it.get("isWithdrawn")),
        }
    return apps


def flatten(state):
    out = {}
    for label, v in state.get("tiles", {}).items():
        out[f"tile:{label}"] = v
    for aid, v in state.get("applications", {}).items():
        out[f"app:{aid}"] = v
    return out


def diff(old, new):
    fo, fn = flatten(old), flatten(new)
    lines = []
    for key in sorted(fn):
        n = fn[key]
        if key not in fo:
            lines.append(f"🆕 {key}: {json.dumps(n, ensure_ascii=False)}")
            continue
        o = fo[key]
        if o == n:
            continue
        if key.startswith("tile:"):
            label = key[5:]
            for field in ("total", "actionable"):
                if o.get(field) != n.get(field):
                    lines.append(f"🔁 {label}: {o.get(field)} ➜ {n.get(field)}")
        else:
            title = n.get("title") or key
            for field in ("status", "withdrawn", "location"):
                if o.get(field) != n.get(field):
                    lines.append(f"🔁 {title}: {field} {o.get(field)} ➜ "
                                 f"{n.get(field)}")
    for key in sorted(set(fo) - set(fn)):
        if key.startswith("app:"):
            lines.append(f"❌ removed: {fo[key].get('title') or key}")
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
    try:
        tiles = fetch_summary()
        apps = fetch_applications()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            telegram("⚠️ MS career tracker: portal rejected the session "
                     f"(HTTP {e.code}). Refresh PORTAL_COOKIE/PORTAL_CSRF.")
            sys.exit(1)
        raise

    new_state = {"tiles": tiles, "applications": apps}
    old_state = {}
    if STATE.exists():
        try:
            old_state = json.loads(STATE.read_text())
        except Exception:
            pass

    changes = diff(old_state, new_state)

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(new_state, indent=2))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(STATE.parent / "history.log", "a") as f:
        f.write(f"{stamp} apps={len(apps)} changes={len(changes)}\n")

    if changes:
        summary = "\n".join(changes)
        telegram(f"📋 Microsoft portal update:\n\n{summary}")
        print(summary)
    else:
        print(f"No changes (tiles: "
              f"{ {k: v['total'] for k, v in tiles.items()} }, "
              f"{len(apps)} applications)")


if __name__ == "__main__":
    main()
