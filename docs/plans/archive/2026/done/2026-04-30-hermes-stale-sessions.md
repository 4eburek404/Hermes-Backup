# Plan: Hermes stale sessions cleanup and root-cause fix

## Goal
Find why Hermes dashboard showed many stale `open sessions`, clean existing stale rows safely, and implement a durable fix so stale SessionDB rows do not accumulate silently.

## Context
- Dashboard showed `open sessions` around 35.
- Live process inspection did not show 35 running Hermes agents.
- `~/.hermes/state.db` had many `sessions.ended_at IS NULL` rows older than 6 hours.
- Work touches Hermes runtime/session state and may change local Hermes Agent code/config.

## Non-goals
- Do not delete transcripts or messages.
- Do not expose tokens, passwords, message contents, or raw private logs.
- Do not change unrelated model/provider configuration.

## Steps
- [x] Back up `~/.hermes/state.db` and close existing stale open rows older than 6 hours.
- [x] Inspect SessionDB lifecycle: `create_session`, `end_session`, compression, cron, CLI close, gateway reset paths.
- [x] Correlate stale rows with gateway logs, restarts, compression and cache eviction.
- [x] Implement a durable fix with tests or a safe operational mitigation.
- [x] Add a dashboard view/card for a guest Hermes Agent instance running in Docker, so the main dashboard can distinguish the primary local Hermes runtime from a disposable/guest containerized instance.
- [x] Verify state DB counts, dashboard, and gateway service after the stale-session display fix.
- [x] Verify guest Docker Hermes visibility after the guest-instance dashboard work.

## Verification
- `state.db` has no stale open sessions older than threshold after cleanup.
- The cause is documented as checked facts vs hypothesis.
- The fix/mitigation is verified with automated test or direct DB/dashboard check.
- Gateway remains active after any deploy/restart.

## Risks / pitfalls
- Marking a session ended while `sessions.json` still points to it can cause future appends to an ended row unless the gateway reopens or rotates it intentionally.
- SessionDB `ended_at IS NULL` is not the same thing as a currently running process.
- Stale cleanup must not touch the current active session.

## Status
Current status: done

## Notes
- Existing stale rows were backed up and closed; open count dropped to 2.
- Backup inspected: before cleanup there were 36 open SessionDB rows; 34 were stale >6h and 22 were stale >24h. Stale rows were mostly `glm-5.1:cloud`/telegram plus older deepseek/gpt/gemma rows.
- Current DB after cleanup: 2 open rows, 2 active within 6h, 0 stale >6h.
- Journal correlation found gateway restarts, drain timeout with active agent interruption, provider/model failures, prompt-too-long, API timeout, and prior ENOSPC-related instability. These explain why logical SessionDB rows can remain `ended_at IS NULL`; no evidence showed 35 live Hermes processes.
- Checked fact: dashboard's old metric treated every `sessions.ended_at IS NULL` row as `open sessions`, which is not equivalent to live/running sessions.
- Mitigation implemented in `server_monitor_iOS_app` branch `fix/hermes-stale-session-display`, commit `83ed59e`: dashboard now counts recent active open sessions separately from total open/stale rows using a 6h threshold (`SERVER_MONITOR_HERMES_OPEN_SESSION_RECENT_SECONDS`, minimum 300s).
- Deployed to `/home/konstantin/dashboard`; backup `/home/konstantin/dashboard/backups/20260430193836-stale-session-display`; `server-monitor.service` active.
- Verified local and public authenticated `/api/stats` return `200` and Hermes meta now shows `active sessions 2`; stats include `Active=2`, `Open=2`. Unauthenticated local API remains `401`.
- Guest Hermes Docker dashboard card implemented in commit `15156d4`: backend inspects configured containers (`SERVER_MONITOR_HERMES_GUEST_DOCKER_CONTAINERS`, default `hermes-guest,hermes-guest-dashboard`), frontend renders `svc-hermes-guest` card.
- Deployed guest card to `/home/konstantin/dashboard`; backup `/home/konstantin/dashboard/backups/20260430194341-guest-hermes-docker-card`.
- Verified local/public authenticated `/api/stats`: `hermes_guest.code=online`, `2/2 running`; public dashboard HTML contains `svc-hermes-guest`.
