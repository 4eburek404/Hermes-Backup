# R8B — Controlled Local Enablement Dry-Run Plan

**Project goal:** снизить input-context overhead Hermes безопасно и измеримо.

## Scope

- **Plan only.** No real enablement, no feature flag change, no `~/.hermes` mutation, no production rollout.
- **Terminal outputs only**, CLI-only candidate, isolated artifact root.
- **No runtime changes.** Default config stays `enabled=false`.

## Preconditions

- Tracked tree clean, `git ls-files --deleted` empty
- R6A–R8A validation chain green
- Feature flag default remains `false`
- Backup files out of scope

## Proposed dry-run config (example only, not to apply)

```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: ["cli"]
  output_kinds: ["terminal"]
  artifact_root: /tmp/hermes-dry-run-artifacts
```

## Dry-run procedure

1. Create isolated config copy outside `~/.hermes`
2. Run synthetic terminal-output scenario
3. Capture provider-bound payload dump (`convert_messages()` → `build_kwargs()` → `json.dumps()`)
4. Compare estimated provider input before/after (raw tokens vs compacted tokens)
5. Verify artifact root containment (no files outside configured root)
6. Verify no raw secrets in payload, messages, or artifacts
7. Verify non-terminal outputs unchanged (passthrough)

## Metrics to record

- Raw provider-bound token estimate
- Compacted provider-bound token estimate
- Token delta
- Artifact count
- Blocked count
- Redacted count
- Unexpected passthrough count
- Test command results

## Stop conditions

Disable immediately if any occurs:
- Raw secret appears anywhere in payload/messages/artifacts when enabled
- Raw large terminal output in provider-bound payload (should be compacted summary only)
- Artifact outside configured root
- Non-terminal output compacted unexpectedly
- Deleted tracked file appears
- Any regression test fails

## Rollback

- Keep `enabled=false` in default config
- Delete isolated artifact root
- No migration needed
- No user config touched

## Recommended next tasks

- R8C: implement dry-run harness using isolated config only
- Optional: provider-specific transport matrix validation
- Separate explicit cleanup: remove 16 backup files