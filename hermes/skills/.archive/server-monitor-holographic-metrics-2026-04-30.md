# Server Monitor Holographic Metrics Deployment — 2026-04-30

Session-specific deployment example for Konstantin's `server_monitor_iOS_app` dashboard.

## Context

- Repository: `/home/konstantin/github_repo/server_monitor_iOS_app`
- Production path: `/home/konstantin/dashboard`
- Service: `server-monitor.service`
- Public endpoint: `https://175557-1.tail52935a.ts.net/dashboard`
- Source metrics DB: `/home/konstantin/.hermes/memory_store.db`
- Holographic metrics are aggregate-only; do not expose fact `content`.
- Cache default: `SERVER_MONITOR_HOLOGRAPHIC_REFRESH_SECONDS=21600` seconds, minimum 300 seconds.

## Deployment pattern used

1. Create a timestamped backup under production:
   - `/home/konstantin/dashboard/backups/20260430155003`
2. Copy only intended artifacts from repo to production:
   - `vps_dashboard/server_monitor.py` -> `server_monitor.py`
   - `vps_dashboard/static/server_monitor.js` -> `static/server_monitor.js`
   - `vps_dashboard/static/server_monitor.css` -> `static/server_monitor.css`
   - `vps_dashboard/templates/server_monitor.html` -> `templates/server_monitor.html`
   - `scripts/validate_live_transport.py` -> `scripts/validate_live_transport.py`
   - `requirements.txt` -> `requirements.txt`
3. Run production syntax checks before/around restart:
   - Python compile for server and live validation script.
   - JS syntax had already been checked in repo.
4. Restart:
   - `sudo systemctl restart server-monitor.service`
5. Verify `systemctl is-active server-monitor.service` and recent journal lines.

## Verification matrix used

Use credentials from `/home/konstantin/dashboard/server-monitor.env` without printing values.

- Unauthenticated local `/api/stats` -> `401`
- Unauthenticated public `/api/stats` -> `401`
- Browser dashboard follow -> `200` with login marker
- Authenticated public `/api/stats` -> `200`
- Authenticated public `/dashboard` -> `200`
- Rendered dashboard HTML contains `holographic-growth`
- API payload:
  - `holographic.available == true`
  - `holographic.total_facts == 44` at deploy time
  - `holographic.cache.ttl_seconds == 21600`
  - no fact `content` exposed
- Live/WebSocket validation still passed:
  - snapshot event ok
  - resume sample ok
  - reset event ok

## Lesson

If the user asks “как я проверю?” or expects a dashboard feature to be checkable, commit/push alone is insufficient. Deploy to the live systemd service, validate the public URL, and report the exact URL plus checks performed.