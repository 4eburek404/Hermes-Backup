# R15B Raw-Leak Suspects Audit Pattern

Use this reference when auditing whether tool-output compaction leaked raw terminal output after production activation.

## Session lesson

A raw-leak audit must separate historical/pre-activation suspects from live post-activation failures. R15B found that the scary aggregate number (`32` suspects across `17` sessions) was entirely historical: all suspect sessions started before the active release symlink mtime. The post-activation strict structured recent-window count was `0`.

## Safe audit shape

1. Capture live provenance before interpreting leaks:
   - active release target (`readlink -f ~/.hermes/hermes-agent` or production symlink path);
   - active symlink mtime / deployment timestamp;
   - gateway service state;
   - config section for `tool_output_compaction`;
   - artifact root existence, permissions, symlink status.
2. Build a sanitized classifier rather than printing raw session/tool/artifact content.
3. Classify each suspect by:
   - session start vs activation timestamp;
   - platform (`telegram` vs other);
   - tool/output kind (`terminal` vs non-terminal);
   - short-output passthrough;
   - secret blocked/redacted status;
   - unknown/unclassifiable.
4. Treat `pre_activation_historical` as carry-over evidence, not a live failure.
5. Count `real_post_activation_telegram_terminal_leaks` separately and make it the primary verdict gate.
6. For recent-window verification, prefer structured session fields over grep-only scans.
7. For artifact verification, report counts and metadata only: file modes, symlink count, outside-root count, permission/read errors, and artifact count. Do not dump artifact bodies.
8. For fresh errors, filter log noise:
   - ignore shell command echoes such as `/bin/bash -c ...` that contain the search terms because the audit command itself was logged;
   - ignore INFO/DEBUG config mentions of `tool_output_compaction` or `artifact_root`;
   - count hard failures like `file is not a database`, `permission denied`, `ImportError`, `ModuleNotFoundError`, or ERROR/CRITICAL lines paired with compaction/artifact terms.

## Minimal verdict fields

```yaml
raw_leak_suspects_total: <int>
sessions_with_suspects: <int>
pre_activation_historical: <int>
post_activation: <int>
real_post_activation_telegram_terminal_leaks: <int>
strict_structured_recent_50_raw_leak_count: <int>
artifact_count: <int>
artifact_root_mode: "0o700"
artifact_file_modes: {"0o600": <int>}
artifact_symlink_count: <int>
artifact_outside_root_count: <int>
fresh_critical_compaction_errors: <int>
verdict: PASS|FAIL|INCONCLUSIVE
```

## Pitfalls

- Do not equate “suspect string exists in historical sessions” with a current production leak.
- Do not use release build time as the activation boundary when the active symlink mtime or service start timestamp is available.
- Do not print raw matched payloads while proving there is no raw leak; use IDs, timestamps, byte counts, hashes, and classification labels.
- Artifact count can grow during the audit because the current Telegram session may itself create compacted tool-output artifacts. Growth is not a config mutation by itself.
- If a tool-call/iteration limit interrupts the audit, report the last verified aggregate and the exact remaining command; do not mark the report complete.
