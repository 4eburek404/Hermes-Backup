# R9B — Local Enablement Verification

**Commit:** No new commit (local config change only, not pushed)

## What Was Done

Enabled `tool_output_compaction` in `~/.hermes/config.yaml` and verified end-to-end compaction with synthetic data — no real LLM/API calls.

## Config Applied

Appended to `~/.hermes/config.yaml`:
```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: [cli]
  enabled_output_kinds: [terminal]
  artifact_root: /tmp/hermes-tool-output-compaction-artifacts
  secret_policy: redact_or_block
```

Config backup created: `~/.hermes/config.yaml.backup_before_tool_output_compaction_20260511181100`

## Verification Results

### Direct Compaction Measurement

| Metric | Value |
|--------|-------|
| Raw output | 10,799 chars |
| Compacted summary | 2,312 chars |
| **Reduction** | **78.6%** |
| Artifact size | 11,185 bytes |
| Artifact location | `/tmp/hermes-tool-output-compaction-artifacts/r9b-enablement-test/` |
| Raw-in-summary check | `False` (raw output NOT in compacted summary) |
| Restore pointer | `hermes artifact restore hermes-artifact://tool-output/r9b-enablement-test/1` |
| Redaction status | `clean` |

### Smoke Harness (R5B)

All 3 checks passed:
- Disabled: output unchanged, no artifact
- Enabled: compacted (2,548 vs 9,599 chars), artifact created, restore pointer present
- Blocked: BLOCKED summary, no artifact, no raw secrets

### Analyzer Baseline

`analyze_context_overhead.py --limit 5` reported 0 tokens — the sessions index contains only 1 session on `telegram` platform with no usable token data. **Baseline/after comparison was not meaningful from existing sessions.** Direct measurement above is the authoritative result.

### Regression Tests

15/15 passed (chat_payload_dump + provider_bound_messages).

## Key Findings

### 1. Real Config Key: `enabled_output_kinds`

`ToolOutputCompactionConfig.from_mapping()` parses `enabled_output_kinds` (not `output_kinds`). The example config at `docs/tool-output-compaction-cli-local.yaml.example` already uses the correct key.

### 2. `compact_tool_output_with_artifact()` is directly importable

```python
from scripts.tool_output_compaction import compact_tool_output_with_artifact
```

No AIAgent initialization needed for wrapper-level testing. This is the R5B pattern — standalone script with `sys.path.insert(0, repo_root)`.

### 3. Config append works for local enablement

No config overlay mechanism needed — just append the `tool_output_compaction` section to `~/.hermes/config.yaml`. The config parser merges with defaults for missing keys.

### 4. `should_compact()` gate verified

```python
should_compact("terminal", "cli") = True    # compaction active
should_compact("file_read", "cli") = False   # not in enabled_output_kinds
should_compact("terminal", "telegram") = False # not in rollout_platforms
```

### 5. Analyzer sessions may lack CLI data

Existing `sessions.json` may only contain telegram-platform sessions with zero token fields. For real before/after measurement, run CLI sessions with compaction enabled/disabled and compare token counts from provider responses.

## Stop Conditions Status

None triggered:
- ✅ No raw secrets in payload
- ✅ No raw large terminal output in payload (compact summary only)
- ✅ Artifacts inside configured root
- ✅ No non-terminal output compacted
- ✅ No test regressions

## Rollback

Not needed — everything works. To disable:
```yaml
tool_output_compaction:
  enabled: false
```

Or remove the section entirely. Default is `enabled: false`.