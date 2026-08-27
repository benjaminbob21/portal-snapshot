#!/usr/bin/env python3
"""Microsoft career portal (Phenom) tracker for apply.careers.microsoft.com.

Watches the signed-in dashboard:
  - the six summary tiles (Applications, Interviews, Saved Jobs, Events,
    Forms manager, Offers) and
  - the per-application list (title/location/status) when available,

snapshots them to state/snapshot.json, diffs against the previous run, and
sends a Telegram message on any change (e.g. Applications 1 -> 2).

Env:
  PORTAL_COOKIE   raw Cookie header copied from DevTools (required)
  TELEGRAM_TOKEN  bot token from @BotFather
  TELEGRAM_CHAT   chat id from @userinfobot
  PORTAL_API_URL  optional override for the data endpoint
"""

import html as htmllib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / "state" / "snapshot.json"

DASHBOARD_URL = os.environ.get("PORTAL_API_URL") or (
    "https://apply.careers.microsoft.com/careers/dashboard"
    "?domain=microsoft.com&hl=en"
)

TILES = ["Applications", "Interviews", "Saved Jobs", "Events",
         "Forms manager", "Offers"]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")


def _get(url, accept):
    cookie = os.environ.get("PORTAL_COOKIE", "").strip()
    if not cookie:
        sys.exit("PORTAL_COOKIE not set")
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", accept)
    req.add_header("X-Requested-With", "XMLHttpRequest")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch():
    """Return (source_url, payload). Try JSON endpoints first, then the page."""
    candidates = []
    if "/api/" in DASHBOARD_URL or DASHBOARD_URL.endswith(".json"):
        candidates.append(DASHBOARD_URL)
    base = "https://apply.careers.microsoft.com"
    candidates += [
        base + "/api/apply/v2/candidate/dashboard?domain=microsoft.com&hl=en",
        base + "/widgets?domain=microsoft.com&hl=en",
    ]
    for url in candidates:
        try:
            raw = _get(url, "application/json")
            return url, json.loads(raw)
        except Exception:
            continue

    # Fall back to the dashboard page itself (HTML or embedded state JSON).
    try:
        raw = _get(DASHBOARD_URL, "text/html")
        try:
            return DASHBOARD_URL, json.loads(raw)
        except Exception:
            return DASHBOARD_URL, raw
    except Exception as e:
        sys.exit(f"portal fetch failed: {e}")


def _norm_count(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if s in ("", "-", "–"):
        return 0
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def extract_tiles(payload):
    """Find the six dashboard tile values in JSON or HTML. None if absent."""
    tiles = {}

    def scan_json(obj):
        if isinstance(obj, dict):
            low = {k.lower().replace(" ", "").replace("_", ""): v
                   for k, v in obj.items()}
            for label in TILES:
                if label in tiles:
                    continue
                key = label.lower().replace(" ", "")
                if key in low:
                    lv = low[key]
                    val = lv.get("count") if isinstance(lv, dict) else lv
                    c = _norm_count(val)
                    if c is not None:
                        tiles[label] = c
            for v in obj.values():
                scan_json(v)
        elif isinstance(obj, list):
            for v in obj:
                scan_json(v)

    if isinstance(payload, (dict, list)):
        scan_json(payload)
    if tiles:
        return tiles

    if isinstance(payload, str):
        text = htmllib.unescape(payload)
        for label in TILES:
            # label ... nearest number or dash within the following 400 chars
            m = re.search(
                re.escape(label) + r".{0,400}?>\s*(-|\d+)\s*<", text, re.S | re.I)
            if m:
                tiles[label] = _norm_count(m.group(1))
        if tiles:
            return tiles
    return None


def extract_jobs(payload):
    """Normalize Phenom application list into {job_id: {...}} or None."""
    items = None
    if isinstance(payload, dict):
        data = payload.get("data") or payload
        for key in ("myApplicationsList", "jobs", "applications", "results"):
            v = data.get(key) if isinstance(data, dict) else None
            if isinstance(v, list):
                items = v
                break
            if isinstance(v, dict) and isinstance(v.get("list"), list):
                items = v["list"]
                break
        if items is None and isinstance(data, list):
            items = data
    if not isinstance(items, list):
        return None

    jobs = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        jid = str(it.get("reqId") or it.get("jobSeqNo")
                  or it.get("id") or it.get("title"))
        status = it.get("status") or it.get("statusBag") \
            or it.get("workflowState") or ""
        if isinstance(status, dict):
            status = status.get("status") or json.dumps(status)
        jobs[jid] = {
            "title": str(it.get("title", "")),
            "location": str(it.get("location", "") or it.get("postedLocation", "")),
            "status": str(status),
            "updated": str(it.get("lastUpdatedDate") or it.get("appliedDate", "")),
        }
    return jobs or None


def diff(state_old, state_new):
    lines = []
    ot, nt = state_old.get("tiles", {}), state_new.get("tiles", {})
    for label in TILES:
        if label in nt:
            if label not in ot:
                lines.append(f"🆕 {label}: {nt[label]} (first reading)")
            elif ot[label] != nt[label]:
                lines.append(f"🔁 {label}: {ot[label]} ➜ {nt[label]}")
    oj, nj = state_old.get("applications", {}), state_new.get("applications", {})
    for jid in sorted(nj):
        n = nj[jid]
        if jid not in oj:
            lines.append(f"🆕 APP: {n['title']} ({n['location']}) -> {n['status']}")
        else:
            o = oj[jid]
            if o["status"] != n["status"]:
                lines.append(f"🔁 {n['title']}: {o['status']} ➜ {n['status']}")
            elif o["updated"] != n["updated"]:
                lines.append(f"🔁 {n['title']}: update timestamp changed")
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
    source, payload = fetch()

    tiles = extract_tiles(payload)
    jobs = extract_jobs(payload)

    if not tiles and not jobs:
        # Can't read anything -> almost certainly logged out.
        STATE.parent.mkdir(parents=True, exist_ok=True)
        (STATE.parent / "raw-last-response.txt").write_text(str(payload)[:5000])
        telegram("⚠️ MS career tracker: could not read dashboard "
                 "(auth expired?). Refresh PORTAL_COOKIE secret.")
        sys.exit(1)

    new_state = {"tiles": tiles or {}, "applications": jobs or {}}
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
        f.write(f"{stamp} source={source} tiles={tiles} "
                f"apps={len(new_state['applications'])} changes={len(changes)}\n")

    if changes:
        summary = "\n".join(changes)
        telegram(f"📋 Microsoft portal update:\n\n{summary}")
        print(summary)
    else:
        print(f"No changes (tiles: {tiles}, "
              f"{len(new_state['applications'])} applications)")


if __name__ == "__main__":
    main()
