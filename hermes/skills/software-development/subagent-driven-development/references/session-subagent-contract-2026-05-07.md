# Session note: strict subagent contract retrofit (2026-05-07)

Use this reference when diagnosing or improving delegation runs where the parent launches subagents but receives no usable information and completes the task manually.

## Observed failure pattern

- Parent dispatches a subagent, but the child result is missing, vague, truncated, or inspected the wrong checkout/path.
- Parent continues by doing the task itself, then reports success without separating child evidence from parent fallback.
- Review subagents can return false blockers when their context points at a stale checkout instead of the active source path.

## Corrective pattern captured in the skill

1. Every `delegate_task` prompt starts with explicit `CURRENT CONTEXT` and names the live repo/path, task scope, source freshness, language, and allowed side effects.
2. Every child must end with `SUBAGENT_RESULT` containing status, evidence handles, files touched, checks, open issues, and `safe_to_continue`.
3. Parent treats missing/empty/truncated/non-schema output as `UNVERIFIED`, not success.
4. Parent verifies evidence directly before continuing: read the claimed file, inspect diff, run check commands, fetch artifact/URL, or confirm paths.
5. If the child inspected the wrong path, mark that review invalid for the active repo and rerun/verify against the correct path.
6. If parent fallback is necessary, label it explicitly in notes/report and verify independently.

## Minimal blocker-review contract

For a narrow verifier, include:

```text
CURRENT CONTEXT: <live date/time/timezone>; language=<...>; task_scope=narrow blocker review only; source freshness=<live repo/path>.
ACTIVE TARGET PATH: <absolute path>
DO NOT inspect sibling/stale checkouts unless asked.
CHECK ONLY:
- <blocker 1>
- <blocker 2>
RETURN CONTRACT:
End with SUBAGENT_RESULT exactly as defined in subagent-driven-development.
Evidence must include file path inspected, search terms, and command/check results.
```

## Evidence from this session

- A delegated review reported blockers from `/home/konstantin/code/Hermes/hermes/...` while the edited source was `/home/konstantin/.hermes/hermes-agent/...`.
- Parent targeted search on the active file found stale interactive-question phrases absent and `SUBAGENT_RESULT` present.
- `git diff --check` and skill audit passed on the active repo after patches.
