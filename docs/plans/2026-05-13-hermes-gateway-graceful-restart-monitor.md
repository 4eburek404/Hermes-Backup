# Hermes gateway graceful restart + monitor plan

**Goal:** Перезапустить Hermes gateway безопасным self-referential способом и собрать post-restart evidence для оптимизации/улучшений.

**Constraints:**
- Current chat runs through the gateway being restarted; do not run a blocking `systemctl restart` from this agent process.
- Use external `systemd-run` runner so monitoring survives gateway restart.
- Prefer graceful restart path: `SIGUSR1 -> exit 75 -> systemd RestartForceExitStatus=75`, not hard stop/start.
- Do not change release symlink or rollback.
- Do not change config/code during first monitoring pass; produce evidence and recommendations first.

## Steps

1. Capture live baseline: active target, gateway MainPID/state/restart policy, SQLite integrity, runtime skills, artifact root, recent critical logs.
2. Create external runner under `/home/konstantin/.hermes/ops/restart_monitor/`.
3. Runner waits briefly so this Telegram response can be delivered, then sends SIGUSR1 to current MainPID.
4. Runner waits for old PID exit and new PID activation, honoring observed `RestartUSec` with timeout floor 180s.
5. Runner monitors 5 minutes after new PID starts: systemd state, PID stability, resource fields, critical journal patterns, SQLite, skills, artifact root.
6. Runner writes markdown report and raw log; no switch/restart/symlink/rollback beyond the requested gateway restart.
7. Use the report to decide optimization: config/code change only after concrete evidence.

Generated: 2026-05-13 14:21:26 CEST / 17:21:26 Asia/Yekaterinburg.
