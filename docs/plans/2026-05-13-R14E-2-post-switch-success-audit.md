# R14E-2 post-switch success audit plan

**Goal:** Закрепить успешный switch d04c50f2f614 read-only audit'ом, проверить runner и обновить ops-baseline/report без switch/restart/symlink/rollback.

**Constraints:**
- НЕ выполнять switch, restart gateway, symlink changes, rollback.
- Live audit только read-only.
- Runner менять только если нужна минимальная правка диагностики/таймаута/reporting; перед этим backup.
- Git commit только если меняются файлы внутри git repo; ~/.hermes/ops сами по себе не коммитить.

## Steps

1. Live audit: readlink active target, systemd state/show, runtime skill dirs, SQLite integrity, artifact_root.
2. Parse switch report `/home/konstantin/.hermes/ops/switch_logs/switch_d04c50f2f614_20260513_134753.report.md` for requested fields.
3. Review runner `/home/konstantin/.hermes/ops/switch_to_d04c50f2f614.sh` for graceful restart path, no stop/start/restart/SIGKILL in normal path, timeout policy, rollback timing, diagnostics.
4. If runner needs a minimal fix: create timestamped backup under `/home/konstantin/.hermes/ops/runner_backups/`, patch only diagnostics/timeouts/report fields, run `bash -n`, compute hashes.
5. Create/update `/home/konstantin/.hermes/ops/RELEASE_STATUS.md` with production baseline.
6. Create final report `/home/konstantin/.hermes/ops/R14E-2_post_switch_success_audit.md` in requested A–P format.
7. Verify syntax/hashes if runner changed; show git status only if repo files changed.

Generated: 2026-05-13 14:01:34 CEST (+0200).
