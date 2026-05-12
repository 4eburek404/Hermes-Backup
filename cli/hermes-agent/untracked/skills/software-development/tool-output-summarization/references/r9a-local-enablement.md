# R9A — Local Enablement Documentation

**Commit:** `31510e2e` — "Document local enablement for tool output compaction"

## Files Created

- `docs/tool-output-compaction-cli-local.yaml.example` — Example config for CLI+terminal-only enablement with isolated artifact root. NOT an active config — reference only.
- `docs/tool-output-compaction-local-enablement.md` — Operator instructions: how to enable locally, verify payload, disable, files not to commit, stop conditions, rollback.

## Example Config Key Fields

```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: [cli]
  enabled_output_kinds: [terminal]
  artifact_root: /tmp/hermes-tool-output-compaction-artifacts
  short_output_threshold: 200
  secret_policy: redact_or_block
```

- Isolated artifact root outside `~/.hermes` and outside repo
- CLI platform only, terminal output kind only
- No `file_read`, `search`, or `web` compaction

## Operator Enablement Steps

1. `mkdir -p /tmp/hermes-tool-output-compaction-artifacts`
2. Add `tool_output_compaction` section to `~/.hermes/config.yaml` (or config overlay)
3. Run CLI session with large terminal output
4. Verify: compacted summary in payload, raw saved to artifact root, no raw secrets
5. To disable: set `enabled: false` or remove section

## Files NOT to Commit

- `~/.hermes/config.yaml` — local user config
- `/tmp/hermes-tool-output-compaction-artifacts/` — runtime artifacts
- Session logs/dumps under `~/.hermes/sessions/`
- Any file with API keys/tokens/auth headers

## .gitignore Pitfall

`docs/examples/` was blocked by a broad `examples/` rule in `.gitignore`. `git check-ignore -v` revealed the rule. Solution: place example file directly under `docs/` with `.example` suffix → `docs/tool-output-compaction-cli-local.yaml.example`.

## Validation Before Enablement

Run full test chain:
```bash
pytest tests/test_tool_output_compaction_chat_payload_dump.py \
       tests/test_tool_output_compaction_provider_bound_messages.py \
       tests/test_tool_output_compaction_session_snapshot_roundtrip.py \
       tests/test_tool_output_compaction_runtime_path_mock.py \
       tests/test_tool_output_compaction_chat_payload_boundary.py -q
```

## Stop Conditions

- Raw secret in payload when compaction enabled
- Raw large terminal output in provider-bound payload
- Artifact outside configured artifact root
- Non-terminal output compacted unexpectedly
- Test regression in validation chain