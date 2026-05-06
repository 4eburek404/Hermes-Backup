# SessionDB stale open sessions

Use this reference when a Hermes dashboard or `~/.hermes/state.db` appears to show many `open` sessions (`ended_at IS NULL`).

## What was learned

`SessionDB.sessions.ended_at IS NULL` is not a reliable live-process or actively-running-agent metric. It means the logical Hermes conversation session has not been closed via `SessionDB.end_session(...)`. Gateway cache eviction, restarts, drain timeouts, provider/model failures, and compression chains can leave DB rows logically open even when no process is stuck.

Dashboard or monitoring code must not label raw `COUNT(*) WHERE ended_at IS NULL` as active sessions. Prefer separating:

- `open_sessions`: all rows with `ended_at IS NULL`.
- `recent_open_sessions` / `active_sessions`: open rows whose last activity is within a defined recency window, e.g. 6h.
- `stale_open_sessions`: open rows older than the recency window.

Last activity should be based on `COALESCE(MAX(messages.timestamp), sessions.started_at)` rather than only `started_at`.

## Investigation workflow

1. Check whether there are live stuck processes before touching the DB:
   - `systemctl --user status hermes-gateway.service`
   - `ps`/process checks for Hermes agents, if available.
2. Inspect SessionDB counts:
   - total sessions
   - open sessions
   - stale open by age buckets, e.g. `6-24h`, `1-2d`, `>2d`
   - newest/fresh open rows with source/model/message/tool counts.
3. Back up `~/.hermes/state.db` before any write.
4. If the user approves cleanup, close only clearly stale rows and preserve auditability:
   - set `ended_at` to the current time
   - set `end_reason='stale_cleanup'`
   - leave fresh open rows untouched.
5. Correlate stale rows with:
   - `journalctl --user -u hermes-gateway.service --since ...`
   - gateway logs for restarts, tracebacks, `Agent cache idle-TTL evict`, drain timeouts, compression/session split events, provider errors, ENOSPC/disk errors.
6. Compare against `~/.hermes/sessions/sessions.json` if present; gateway SessionStore and SessionDB are separate concepts.

## Durable monitoring fix

For dashboards or external monitors:

- Do not equate DB `open` with live active work.
- Show active/recent and stale separately.
- Make the recency window configurable, with a sane default (6h was used in this case) and a lower bound (e.g. 300 seconds).
- If stale rows are nonzero, surface them as hygiene debt rather than urgent active load.

## Possible Hermes-core fix

If repeated stale rows keep accumulating after cleanup, investigate Hermes-core lifecycle rather than only the dashboard:

- startup reconciliation: on gateway startup, close DB sessions not represented in current SessionStore and older than a safe threshold, with `end_reason='stale_startup_reconcile'`;
- ensure cache eviction/session expiry/shutdown paths call `SessionDB.end_session(...)` when they truly end a logical session;
- avoid closing current logical sessions merely because a cached agent was evicted.

## Pitfalls

- Do not report “many open sessions” as “many stuck agents” without process/log evidence.
- Do not delete stale rows; close them with an explicit `end_reason` so audits remain possible.
- Do not blame the model when the causal factor is gateway lifecycle, DB semantics, restarts, ENOSPC, provider timeouts, or dashboard metric design.
- Do not deploy only a cosmetic dashboard change if the user explicitly asks to understand why rows accumulated; finish log correlation and state the confidence level.