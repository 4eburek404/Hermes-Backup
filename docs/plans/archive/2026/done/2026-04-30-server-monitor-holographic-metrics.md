# Plan: Server Monitor Holographic Metrics

## Goal
Add slow-refresh Holographic memory metrics to `server_monitor_iOS_app` web dashboard: a time-series XY chart showing cumulative fact growth and compact counters for the most useful fact-store dimensions.

## Context
- User requested an XY graph where fact count growth is visible.
- Holographic facts live in `/home/konstantin/.hermes/memory_store.db`.
- The live system collector updates every 5 seconds; Holographic memory changes much more slowly, so metrics must use a separate slow cache rather than querying SQLite every live sample.
- Current implementation branch: `feat/holographic-metrics` from `feat/auth-without-tailscale-login`.
- Production dashboard is deployed from `/home/konstantin/dashboard`, but deployment is a separate explicit step after implementation/verification.

## Non-goals
- Do not expose fact contents in the dashboard; show aggregate metrics only.
- Do not write to the Holographic database.
- Do not add a 5-second polling loop for Holographic data.
- Do not change iOS API models unless needed; web dashboard is the target for this task.
- Do not reveal secrets from dashboard env/config files.

## Steps
- [x] Create implementation branch.
- [x] Create durable plan.
- [x] Inspect backend API payload and frontend chart integration points.
- [x] Add backend read-only SQLite metrics collector with long TTL cache.
- [x] Add focused tests for Holographic metrics aggregation/cache behavior.
- [x] Add web dashboard card and XY cumulative facts chart.
- [x] Validate Python, JavaScript, diff hygiene, and auth/API smoke checks.
- [x] Update project docs if implementation changes API/dashboard contract.
- [x] Commit and push branch.

## Verification
- Python syntax check passes: `.venv/bin/python -m py_compile vps_dashboard/server_monitor.py scripts/validate_live_transport.py`.
- JavaScript syntax check passes: `node --check vps_dashboard/static/server_monitor.js`.
- `git diff --check` passes.
- Test coverage for aggregation/cache passes.
- `/api/stats` includes aggregate `holographic` payload for web profile and does not include fact contents.
- Holographic metrics payload reports long refresh interval / cache metadata.

## Risks / pitfalls
- SQLite DB can be missing or locked; dashboard must degrade with unavailable status rather than fail `/api/stats`.
- Fact contents may contain sensitive operational notes; UI/API should expose aggregates only.
- Existing `/api/stats` is also used by iOS; avoid breaking iOS contract.
- Cache TTL should be long because facts update slowly. Initial target: 6 hours, configurable by env.

## Status
Current status: done

## Notes
- Implemented and pushed on branch `feat/holographic-metrics`, commit `a5e5684`.
- Backend reads `/home/konstantin/.hermes/memory_store.db` read-only and exposes only aggregate `holographic` metrics in web `/api/stats`; iOS-trimmed payload remains unchanged.
- Cache TTL defaults to 21600 seconds / 6 hours and is configurable with `SERVER_MONITOR_HOLOGRAPHIC_REFRESH_SECONDS`.
- Verification passed: unit tests, py_compile, JS syntax, `git diff --check`, and local `/api/stats` smoke with `content_exposed=False`.
- Production deploy was performed after the initial branch push: files were copied to `/home/konstantin/dashboard`, backup `/home/konstantin/dashboard/backups/20260430155003` was created, `server-monitor.service` restarted active, public auth/dashboard/API/live checks passed.
