# MS Career Portal Tracker

Monitors your Microsoft careers portal dashboard (Phenom/pcsx API) and sends instant Telegram alerts when any application status or dashboard tile changes.

## Architecture

- **Host:** Ubuntu VM (`~/msft-career-tracker`)
- **Cadence:** Cron job runs `scripts/run-tracker.sh` every 15 minutes.
- **Session keep-alive:** Every probe automatically captures the rotated `session=` cookie from Microsoft and self-updates `.env` in place.
- **Notifications:** Telegram message on any tile/application change or on auth failure (HTTP 401/403).

## Checked Endpoints

- `/api/pcsx/dashboard/summary` (Applications, Interviews, Saved Jobs, Events, Forms, Offers)
- `/api/pcsx/dashboard/applications` (per-application title, location, status, withdrawn flag)

## Maintenance

- **Auth expired (HTTP 401/403):** You will get an immediate Telegram alert. Re-grab the curl from your browser Network tab, update `.env` on the VM, and run `bash scripts/run-tracker.sh`.
- **Logs:** Check `state/track-cron.log` and `state/history.log` on the VM.
