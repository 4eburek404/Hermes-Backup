# Tool Output Compaction Audit

Read-only audit procedure for verifying Hermes tool_output_compaction after enablement.

## Prerequisites

- Active Hermes gateway on host runtime (systemd --user)
- `tool_output_compaction.enabled: true` in config.yaml
- Access to artifact_root and journalctl

## Health Checks (5 signs)

1. **Hermes answers in Telegram** — send a ping, expect a response.
2. **Gateway not crashing** — `systemctl --user is-active hermes-gateway` → `active`.
3. **No fresh critical errors** — journalctl grep returns empty for the critical pattern list.
4. **Compaction actually fires** — after a large terminal output, a `.raw` artifact appears and Telegram gets a summary, not the full dump.
5. **Artifacts inside artifact_root only** — no `.raw` files leaked outside the configured persistent artifact root (`/home/konstantin/.hermes/tool-output-artifacts` in the current deployment).

## Audit Procedure

### 1. Runtime status

```bash
readlink -f ~/.hermes/hermes-agent
# Expected: /home/konstantin/.hermes/releases/hermes-agent-<commit>
systemctl --user is-active hermes-gateway  # → active
docker ps | grep -i hermes  # Should show NO hermes runtime container
ps aux | grep -E '[h]ermes|[p]ython.*hermes_cli'
```

### 2. Config verification (no secrets)

```bash
grep -A12 "tool_output_compaction" ~/.hermes/config.yaml
```

Expected (current persistent-artifact deployment):
```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: [telegram]
  enabled_output_kinds: [terminal]
  artifact_root: /home/konstantin/.hermes/tool-output-artifacts
  secret_policy: redact_or_block
```

### 3. Log health (last 2 hours, exclude grep command lines)

```bash
journalctl --user -u hermes-gateway --since "2 hours ago" --no-pager \
  | grep -Ei "ImportError|ModuleNotFoundError|traceback|exception|file is not a database|503|server overloaded|ToolOutputCompactionConfig|No adapter available|python-telegram-bot" \
  | grep -v "grep -E" | grep -v "__hermes"
```

Error interpretation:
- `503` → provider/model route issue (not runtime)
- `ImportError`/`ModuleNotFoundError` → runtime/release problem
- `file is not a database` → memory DB corruption
- `No adapter available` + `python-telegram-bot not installed` → old venv without telegram-bot (pre-release-switch)

Historical errors before current gateway start are expected during release-switch cycles.

### 4. Artifact analysis

```bash
# Total
find /home/konstantin/.hermes/tool-output-artifacts -maxdepth 4 -type f | wc -l
du -sb /home/konstantin/.hermes/tool-output-artifacts | cut -f1

# Recent (non-simulated)
find /home/konstantin/.hermes/tool-output-artifacts -maxdepth 4 -type f \
  -not -path '*/r9c-simulated/*' -printf "%TY-%Tm-%Td %TH:%TM %s %p\n" | sort

# Top-5 largest
find /home/konstantin/.hermes/tool-output-artifacts -maxdepth 4 -type f \
  -printf "%s %p\n" | sort -rn | head -5

# Permissions
ls -la /home/konstantin/.hermes/tool-output-artifacts/
```

Check:
- All artifacts inside artifact_root → no leaks
- Root dir permissions: `drwx------ konstantin:konstantin`
- Artifact metadata: `redaction_status: clean` or `redacted`

### 5. Effectiveness analysis

#### Manual method (R12B evidence)

For a known large terminal output:

1. Record raw artifact size: `wc -c <path>.raw`
2. Estimate raw tokens: `raw_bytes / 4`
3. Estimate compact tokens: count tokens in the Telegram response (~chars/4)
4. Savings = raw_tokens - compact_tokens

Example (250-line synthetic, 48793 bytes):
- Raw tokens: ~12,200
- Compact tokens: ~25
- Savings: ~12,175 tokens (99.8%)

#### Analyzer method

```bash
cd ~/.hermes/releases/hermes-agent-$(readlink -f ~/.hermes/hermes-agent | grep -oP 'd\w+$' | head -1) 2>/dev/null || true
python scripts/analyze_context_overhead.py \
  --sessions-dir ~/.hermes/sessions \
  --limit 1 \
  --simulate-tool-output-summarization \
  --simulate-tool-output-artifacts-dir /home/konstantin/.hermes/tool-output-artifacts \
  --out-md /tmp/hermes-compaction-audit.md \
  --out-json /tmp/hermes-compaction-audit.json
```

**Critical interpretation:** The analyzer runs on the POST-compression snapshot. `savings_percent: -0.81%` means compact-vs-compact overhead (artifact metadata ~18 tokens/msg), NOT that compaction wastes tokens. Real savings = raw_tokens of original output minus compact tokens of summary.

Key analyzer fields:
- `tool_output_summarization_simulation.enabled` — whether compaction is active
- `output_kind_counts` — breakdown by terminal/file_read/short_output
- `secret_scan_counts` — blocked/redacted/clean
- `artifacts.written_count` — how many artifacts were created
- `artifacts.skipped_short_count` — outputs too short for compaction
- `top_predicted_savings` — per-message breakdown (note: measures compact-overhead, not raw savings)

### 6. Compaction test command

In Telegram, ask Hermes to run a synthetic large output:

```bash
python - <<'PY'
for i in range(180):
    print(f"MONITOR_COMPACTION_LINE_{i:03d} " + "x" * 160)
PY
```

After execution:
- Telegram should show a compact summary, not 180 lines
- A new `.raw` artifact should appear
- No critical errors in logs

## Status Interpretation

| Signal | Good | Bad |
|--------|------|-----|
| Gateway | `active` | `inactive` / crash loop |
| Telegram | responds | silent |
| Large terminal output | summary in chat | full dump in chat |
| Artifacts | .raw files appear in root | no artifacts / outside root |
| secret_scan | `redacted`/`clean` | `blocked` on non-secrets |
| ImportError | none in current gateway | present after restart |
| 503 on ping | none | recurring |

## Raw artifact restore policy

If a future task asks to design or implement raw artifact restore, follow the repo policy `docs/hermes-compaction-raw-artifact-restore-policy.md` first. Key guardrails: restore exists only to recover exact details omitted by a compacted summary; keep scope Telegram + terminal only; read only under configured artifact_root; reject symlink/path traversal and `/tmp`; enforce max bytes/max lines; perform secret re-scan before returning content; blocked secret outputs are not restorable and should not create raw artifacts.

## Soft rollback (compaction only)

```yaml
# ~/.hermes/config.yaml
tool_output_compaction:
  enabled: false
```

```bash
systemctl --user restart hermes-gateway
```

This disables compaction but keeps the release runtime active.

## Full runtime rollback

1. `systemctl --user stop hermes-gateway`
2. `ln -sfn /home/konstantin/.hermes/hermes-agent.pre_r12a_messagingfix_<timestamp> ~/.hermes/hermes-agent`
3. `systemctl --user start hermes-gateway`
4. Verify.

## Next steps after audit

- Persistent artifact_root is already the current baseline: `/home/konstantin/.hermes/tool-output-artifacts`. Treat `/tmp` artifact roots as stale/unsafe unless the task is explicitly auditing historical data.
- Consider expanding `enabled_output_kinds` to include `file_read` and `search` only under an explicitly approved future task; do not expand scope during Telegram terminal audits.
- Run full `analyze_context_overhead.py` across multiple sessions for aggregate stats.

## Audit evidence format

Save temporary reports to `/tmp/hermes-compaction-audit.md` and `/tmp/hermes-compaction-audit.json`. These are disposable — not production data.

Full production runbook: `/home/konstantin/docs/hermes-runtime-management.md`