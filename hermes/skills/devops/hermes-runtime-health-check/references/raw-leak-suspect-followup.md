# Raw-leak suspect follow-up audit (R15B pattern)

Use when a compaction/effectiveness audit reports large raw-output suspects and the follow-up task is to decide whether they are active production leaks or historical/out-of-scope carry-over.

## Goal

Classify suspects without exposing raw session content, raw terminal output, raw artifact bodies, or secrets. Produce aggregate counts and reason codes only.

## Inputs

- Previous audit report and any hit/locator file.
- `~/.hermes/sessions/` session JSON/JSONL files.
- Active release symlink: `~/.hermes/hermes-agent`.
- Artifact root: `/home/konstantin/.hermes/tool-output-artifacts`.
- Logs: `journalctl --user -u hermes-gateway` and `~/.hermes/logs/agent.log`.

## Sanitized classifier pattern

1. Determine the active-release boundary from symlink mtime:

```python
import os
from pathlib import Path
active = Path('/home/konstantin/.hermes/hermes-agent')
activation_ts = os.lstat(active).st_mtime
active_target = active.resolve()
```

2. Use prior hit data only as a locator. Do not print raw payload. Store/emit only:

- session file basename;
- source line number if known;
- payload length;
- SHA-12 of payload or decoded content;
- session start/mtime;
- platform;
- tool name/output kind;
- booleans for compaction/artifact/secret markers;
- classification and reason code.

3. Classify with explicit reasons:

- `pre_activation_historical` when `session_start < active_release_symlink_mtime`.
- `non_telegram` when platform is outside rollout scope.
- `non_terminal` when output kind is outside `enabled_output_kinds`.
- `secret_blocked_or_redacted` when blocked/redacted markers are present.
- `short_output_passthrough` when below large-output threshold after structural decode.
- `real_post_activation_telegram_terminal_raw_leak` only when post-activation + Telegram + terminal + large + no compaction/artifact/secret marker.
- `unknown` when metadata is insufficient.

4. Add a strict recent-session fallback scan (for example recent 50 sessions) that structurally reads tool messages and counts large unmarked terminal outputs, again without printing content.

## Artifact/log aggregate pattern

Check artifact invariants without reading bodies:

- total file count;
- root permissions;
- file permission distribution;
- symlink count;
- outside-root resolved paths;
- permission errors.

For logs, count pattern matches separately from critical failures. Filter shell-command echoes such as `/bin/bash -c`, `journalctl`, and grep command lines. Treat plain `tool_output_compaction` / `artifact_root` INFO mentions as non-critical. Count critical failures only for hard terms (`file is not a database`, `permission denied`, `ImportError`, `ModuleNotFoundError`) or ERROR/CRITICAL compaction/artifact messages.

## Reporting

Report aggregate counts first:

- total suspects;
- sessions with suspects;
- pre-activation/post-activation counts;
- real post-activation Telegram terminal leak count;
- unknown count;
- strict recent-N count;
- artifact path/permission/symlink/outside-root counts;
- critical log counts;
- mutation status.

Do not include raw lines or payload snippets. Mention that artifact count is a moving counter because the audit itself may generate compacted terminal-output artifacts.

## Commit/push rule

If writing a repo doc, commit/push only when the intended path can be staged without unrelated dirty state. In a dirty worktree, stage nothing broad; report the doc path and unrelated dirty state rather than mixing it into the commit.
