# Tool Output Compaction — Rollout Readiness

**Project goal:** снизить input-context overhead Hermes безопасно и измеримо.

## Validation chain

| Step | Commit | Description |
|------|--------|-------------|
| R6A | `003091a5` | Configured smoke — default/off path + enabled terminal-only path behind feature flag |
| R6B | `6ab968cd` | Agent loop insertion smoke — compaction integrated into conversation loop |
| R6C | `f79138b6` | Analyzer measurement validation — before/after reduction on synthetic sessions |
| R6D | *(no commit)* | Restore/safety stabilization — clean tracked tree, no deleted files |
| R6E | `ab963e19` | Validation status document |
| R7A | `f6a943e2` | Runtime path mock — full insertion sequence with mocked tool invocation |
| R7B | `64cede8f` | Session snapshot roundtrip — persist/reload compacted conversation, verify consistency |
| R7C | `099701b2` | Provider-bound message validation — analyzer `sanitize_message_for_standard_provider` produces correct provider-bound view |
| R7D-1 | `b97035e3` | ChatCompletions payload boundary — transport is pure offline function |
| R7D-2 | `ab93b6b5` | ChatCompletions payload dump — full compaction→transport→JSON pipeline |
| R8A | `acc0e0f0` | Rollout readiness document |

## What is ready for controlled local enablement

- terminal outputs only — `file_read`, `search`, `web` toolset compaction is not validated
- feature flag only — `tool_output_compaction.enabled` must be explicitly set to `true`; default is `false`
- isolated artifact root — `tool_output_compaction.artifact_root` stores `.raw` files; must be an explicit path
- no default config change — default config remains `enabled: false`
- no ContextCompressor — compaction is independent of context compression
- no production rollout — this is controlled local enablement only

## Controlled local enablement criteria

1. Explicit config only. Set `tool_output_compaction.enabled: true` in user config; never change default.
2. Single platform first. Prefer `cli` only via `rollout_platforms: ["cli"]`.
3. Small session count. Run a limited number of sessions with compaction enabled.
4. Compare before/after estimated provider input. Use `analyze_context_overhead.py` on session snapshots.
5. Inspect payload/log dumps for absence of raw large terminal output and secrets.
6. Verify artifacts stay under configured root. No `.raw` file outside `artifact_root`.

## Stop conditions

Disable compaction immediately if:
- raw secret appears in payload, messages, or artifacts when compaction enabled
- raw large terminal output appears in provider-bound payload (should only contain summary + restore pointer)
- artifact written outside configured `artifact_root`
- any deleted tracked file appears during work
- unexpected runtime behavior in non-terminal tools
- test regression in R6A–R7D-2

## Rollback

- set `tool_output_compaction.enabled: false`
- remove or ignore isolated artifact root directory
- no migration required — default/off path passes original output unchanged

## Recommended next tasks

- R8B: controlled local enablement dry-run plan
- Optional: provider-specific transport matrix validation (Anthropic/Codex/Ollama)
- Separate: cleanup 16 backup files with explicit permission