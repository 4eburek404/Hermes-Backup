# Hermes Dashboard — Web API Reference

Collected from `hermes_cli/web_server.py` (v0.13.0) and live probing.

## Auth

Session token is generated at dashboard startup and embedded in the SPA HTML
as `window.__HERMES_SESSION_TOKEN__`. All `/api/` routes except the public list
require this token as a cookie (`hermes_session=<TOKEN>`) or `Authorization: Bearer <TOKEN>`.

Public paths (no auth): `/api/status`, `/api/config/defaults`, `/api/config/schema`, `/api/model/info`, `/api/dashboard/themes`, `/api/dashboard/plugins`, `/api/plugins/*`.

## Key Endpoints

- **GET `/api/status`** — Version, gateway state, platforms, active sessions
- **GET `/api/config`** — Full config.yaml (auth required)
- **GET `/api/config/defaults`** — Default config values
- **GET `/api/config/schema`** — Config schema for UI rendering
- **GET `/api/model/info`** — Current model, provider, context length, capabilities
- **GET `/api/sessions?limit=N&offset=M`** — List sessions with token/cost stats
- **GET `/api/sessions/search?q=QUERY`** — Full-text search sessions
- **GET `/api/analytics/usage?days=N`** — Token usage, cost, per-model breakdown
- **POST `/api/config`** — Update config values
- **POST `/api/env`** — Set .env variables
- **DELETE `/api/env`** — Remove .env variables
- **POST `/api/gateway/restart`** — Restart the gateway process
- **POST `/api/hermes/update`** — Trigger `hermes update`
- **GET `/api/actions/{name}/status`** — Check status of async actions (restart, update)
- **GET `/api/dashboard/themes`** — Available themes + active theme
- **GET `/api/dashboard/plugins`** — Dashboard plugin manifests
- **POST `/api/dashboard/plugins/rescan`** — Rescan plugin directory

## SPA Frontend

Built Vite/React app served from `hermes_cli/web_dist/` (bundled at install).
Static assets at `/assets/` with immutable cache headers. SPA fallback to `index.html`.

### Response Compression

**As shipped (v0.13.0), the dashboard does NOT serve gzip/brotli.** The SPA bundle
transfers uncompressed (~1.2 MB JS, ~95 KB CSS). This makes first load slow on
high-latency connections (Tailscale relay, mobile).

**Fix:** Add `GZipMiddleware` to `hermes_cli/web_server.py` after the CORS middleware:

```python
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)
```

Measured effect (localhost):

| Asset | Uncompressed | With gzip | Ratio |
|-------|-------------|-----------|-------|
| JS bundle | 1 191 911 B | 346 524 B | ×3.4 |
| CSS | 94 497 B | 15 165 B | ×6.2 |

**Caveat:** This patch lives in the source tree and will be overwritten by `hermes update`. Reapply after updates until upstream ships compression by default.

**Restart required:** After patching web_server.py, kill the dashboard process and start a new one. The dashboard doesn't hot-reload source changes:
```bash
# Kill existing (find PID with: ps aux | grep 'hermes dashboard')
kill <PID>
# Restart
hermes dashboard --host 0.0.0.0 --port 9119 --insecure --no-open
```

Verify: `curl -s -H "Accept-Encoding: gzip" -o /dev/null -w "%{size_download}" http://127.0.0.1:9119/assets/index-*.js` — should show ~346K instead of ~1.2M.

## Remote Access

Default binds 127.0.0.1 only. For remote:
- `ssh -L 9119:127.0.0.1:9119 user@host` — safest
- Tailscale — works if host is on the tailnet
- `--insecure --host 0.0.0.0` — **dangerous**, exposes API keys on network

UFW: `sudo ufw allow in on tailscale0 to any port 9119 proto tcp` for Tailscale-only access.