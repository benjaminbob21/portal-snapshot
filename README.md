# MS Career Portal Tracker

GitHub Action that checks your Microsoft careers portal applications every 6
hours and pings Telegram when a status changes.

## One-time setup

### 1. Capture your auth cookie

1. Log in at https://apply.careers.microsoft.com (your dashboard shows the
   Applications / Interviews / Saved Jobs / Events / Forms manager / Offers tiles)
2. DevTools (Cmd+Opt+I) -> Network tab -> refresh the page
3. Click the main page/API request -> Request Headers -> copy the whole `cookie:` header value

### 2. Create a Telegram bot

1. Message **@BotFather** -> `/newbot` -> save the token
2. Message your new bot once ("hi"), then message **@userinfobot** to get your chat id

### 3. Add repo secrets + variable

| Name | Type | Value |
|---|---|---|
| `PORTAL_COOKIE` | Secret | cookie header from step 1 |
| `TELEGRAM_TOKEN` | Secret | BotFather token |
| `TELEGRAM_CHAT` | Secret | chat id from step 2 |
| `PORTAL_API_URL` | Variable | see below |

`PORTAL_API_URL` must point at the JSON endpoint that returns your application
list. The default in `scripts/track.py` points at the search page; if it 404s,
inspect DevTools for an XHR request returning `myApplicationsList` style JSON
and use that URL.

### 4. Push and run once

Push this repo to GitHub, open the Actions tab, run **track-portal**
manually, verify the snapshot lands in `state/snapshot.json`.

## Maintenance

- **Auth expires:** Microsoft cookies rotate periodically. If parsing fails,
  the bot DMs you a warning -- repeat step 1, update the secret.
- **Cadence:** change the cron in `.github/workflows/track.yml`.
