# Tool Output Compaction Raw Artifact Restore Policy

Use this reference when designing, reviewing, or implementing future safe restore of raw tool-output artifacts created by Hermes `tool_output_compaction`.

This is a policy/spec reference, not runtime integration. It must not be used as permission to read raw artifacts, raw sessions, change production config, restart the gateway, weaken `secret_policy`, expand compaction scope, or implement restore inside `run_agent.py`/`scripts/tool_output_compaction.py` without an explicit task.

## Current audit baseline

- R15A: compaction worked; 458/555 terminal outputs compacted; R14+ sessions were 100% compacted; estimated savings 5,160,937 tokens / 61.95%; verdict `PASS_WITH_WARNINGS`.
- R15B: 32 raw-leak suspects were classified; all 32 were `pre_activation_historical`; real post-activation Telegram terminal leaks: 0; verdict `PASS`.
- R15C: 84 blocked secret outputs were classified; 43 likely true secret, 1 likely false positive, 40 ambiguous; blocked outputs did not create raw artifacts; no fresh critical compaction errors; verdict `PASS_WITH_WARNINGS`.
- Current allowed compaction scope remains **Telegram + terminal only**. Do not expand scope while working on restore policy or helper code.

## Purpose

Raw artifact restore exists only to recover exact details that a compacted summary omitted. It is not a browsing mode, curiosity feature, bulk dump path, or bypass around secret blocking.

## Restore is allowed when the user/task asks for exact omitted details

Allowed request classes include:

- exact lines;
- full traceback;
- failing test output;
- full diff;
- exact JSON/YAML/log structure;
- previous terminal output inspection;
- “why did it fail?” when the compacted summary is insufficient;
- “show exact command output”;
- “inspect artifact”.

Even for allowed cases, return a bounded excerpt by default and run all safety checks first.

## Restore is not allowed

Reject restore when any of these is true:

- the compacted output was secret-blocked;
- artifact is absent;
- artifact path is outside `artifact_root`;
- artifact path is a symlink or resolves through a symlink escape outside `artifact_root`;
- artifact fails secret re-scan;
- request is broad or curiosity-only and the summary is enough;
- artifact is too large and no bounded slice was requested;
- artifact path points into `/tmp` or any other non-configured root;
- the artifact would represent a blocked-output artifact, because blocked outputs should not create raw artifacts.

## Required safety checks

Before returning any content, a safe artifact reader must verify:

1. Load `artifact_root` from config. Current production root: `/home/konstantin/.hermes/tool-output-artifacts`.
2. Resolve the requested artifact path or artifact reference to a canonical path.
3. Ensure the resolved path is under `artifact_root`.
4. Reject symlink paths and symlink escape attempts.
5. Never read artifacts from `/tmp`.
6. Enforce a max bytes limit before reading/returning content.
7. Enforce a max lines limit before returning content.
8. Run secret re-scan before returning content.
9. If the secret re-scan hits a likely secret, block or redact content; prefer blocked summary for high-confidence secret hits.
10. Never read blocked-output artifacts; blocked outputs should not create raw artifacts.
11. Log a restore access event without raw content.

## Restore output policy

Default response shape:

- bounded excerpt + metadata;
- command/status/summary if available;
- artifact path/reference only if safe to expose;
- no huge full dump by default;
- exact line-range slices allowed when bounded;
- if a secret is detected, return a blocked summary, not content.

## Machine-readable compacted summary proposal

Compacted terminal summaries should eventually include these fields so restore decisions do not depend on brittle prose parsing:

```yaml
artifact_ref: <opaque safe reference>
output_kind: terminal
platform: telegram
artifact_root_id: <configured-root-id>
safe_relative_path: <relative path under artifact_root>
raw_size_bytes: <int>
raw_line_count: <int>
secret_policy_result: clean|redacted|blocked
restore_hint: <short human hint>
when_to_restore:
  - exact lines
  - full traceback
  - failing test output
restore_allowed: true|false
```

Do not store absolute paths in user-visible summaries unless a safety review says it is acceptable. Prefer opaque `artifact_ref` or safe relative paths.

## R15D-2 implementation plan

Next implementation task should be helper-only, tests first, with no production integration:

1. Add a safe artifact reader helper.
2. Write tests before runtime wiring.
3. Do not change production config, gateway, compaction scope, or `secret_policy`.
4. Do not integrate into `run_agent.py` yet.
5. Do not modify `scripts/tool_output_compaction.py` unless the task explicitly scopes that file.

Required tests:

- path traversal tests;
- symlink escape tests;
- max bytes tests;
- max lines tests;
- secret re-scan tests;
- blocked secret output tests;
- missing artifact tests;
- `/tmp` artifact rejection tests;
- broad-request/no-slice rejection tests where applicable.

## Explicit non-goals

- no config changes;
- no compaction scope expansion;
- no `ContextCompressor` work;
- no file_read/search/web compaction;
- no automatic restore of secret-heavy outputs;
- no weakening of `secret_policy`;
- no gateway restart as part of policy/spec work.

## Documentation validation checklist

A raw artifact restore policy/spec is incomplete unless it explicitly mentions:

- `artifact_root`;
- no symlink escape;
- max bytes;
- max lines;
- secret re-scan;
- blocked secret outputs not restorable;
- no scope expansion;
- R15A/R15B/R15C summary;
- current scope: Telegram + terminal only.
