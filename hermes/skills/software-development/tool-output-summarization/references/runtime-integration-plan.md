# Runtime Integration Plan: compact_tool_output_with_artifact()

**Created:** 2025-05-11 | **Branch:** context-input-baseline | **Commit:** 5b5abcda

Full plan lives in the repo at `docs/context-tool-output-runtime-integration-plan.md`.

## Key Decisions

- **Integration point A** (recommended): compaction runs on raw `function_result` **before** `maybe_persist_tool_result()` at both call sites (concurrent ~L10172, sequential ~L10560)
- **Behind feature flag** `tool_output_compaction.enabled: false` by default
- **Config** as `ToolOutputCompactionConfig` dataclass, mirrors `BudgetConfig` pattern
- **Rollback**: single config change or commit revert; no data migration needed

## Feature Flag Design

```yaml
tool_output_compaction:
  enabled: false
  artifact_root: /tmp/hermes/artifacts
  max_raw_chars: 50000
  short_output_threshold: 200
  secret_policy: redact_or_block
  enabled_output_kinds:
    - terminal
    - file_read
  rollout_platforms:
    - cli
```

## Implementation Task Split

| Task | Description |
|------|-------------|
| R1 | Locate exact tool-result insertion point (DONE — two sites identified) |
| R2 | Add config parsing only, default false |
| R3 | Integrate wrapper behind flag for terminal only |
| R4 | Add artifact cleanup hooks |
| R5 | Fixture/session replay validation |
| R6 | Opt-in local rollout |

## Required Tests Before Enabling

1. Existing 96 Hermes tests pass
2. Existing 78 compaction tests pass
3. Config default false → `enabled=False`
4. Config explicit false → compaction never called
5. Runtime path with flag=false identical to current behavior
6. Runtime path with flag=true → summary in messages, artifact on disk
7. Blocked secret does not enter message history
8. Redacted secrets removed from history, artifact has redacted body
9. Short output < 200 chars passes through, no artifact
10. Restore pointer works via `read_file`
11. Rollback test: set enabled=false → behavior identical to baseline
12. Dedup: repeated output gets reference, no duplicate artifact
13. Interaction with `maybe_persist_tool_result()`: summary still too large → persistence kicks in

## Risks

- Missing critical debugging detail in summaries
- Artifact leakage (`/tmp/hermes/artifacts/` permissions)
- Restore pointer stale (artifact deleted before read)
- Blocked secret removes necessary context
- Over-aggressive dedup (exact-match only, SHA-256)
- Mismatch with ContextCompressor later
- Disk growth over long sessions

## Simulation Baseline

| Metric | Value |
|--------|-------|
| raw_tokens | 782,216 |
| compact_tokens | 286,783 |
| savings | 495,433 (63.34%) |
| artifacts written | 314 |
| redacted | 49 |
| blocked | 21 |
| dedup | 1,332 |
| skipped short | 190 |