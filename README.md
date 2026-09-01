# portal-snapshot

A small utility that periodically captures a snapshot of a remote dashboard
and stores it locally. Designed to run unattended in a CI environment.

## Usage

1. Configure the required environment variables (see `.github/workflows/snapshot.yml`).
2. Push to GitHub. The workflow runs on a schedule and commits the snapshot
   to the `state/` folder.
3. Inspect `state/snapshot.json` for the latest captured state.

## Notes

- The snapshot is diffed against the previous one; changes are logged to
  `state/history.log`.
- No external services are required beyond the configured endpoint.
