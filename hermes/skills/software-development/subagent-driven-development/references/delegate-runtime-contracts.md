# Hermes `delegate_task` runtime contracts and tuning

Session source: 2026-05-07 deep analysis of `/home/konstantin/.hermes/hermes-agent` after repeated subagent handoff failures.

## Why this matters

`delegate_task` can return a runtime result that is not equivalent to a usable child handoff. Parent agents must gate on both runtime fields and the child `SUBAGENT_RESULT`; otherwise they may silently redo the task and later report mixed/unsupported evidence.

## Runtime acceptance gate

After every delegated task, inspect the raw runtime result before trusting the child text:

- `status`
- `exit_reason`
- `error`
- `diagnostic_path`
- `api_calls`
- `duration_seconds`

Treat these as not-success until parent evidence is verified:

- empty child result
- timeout / interrupted result
- truncated or schema-less child text
- `exit_reason=max_iterations` even if `status=completed`
- missing or unverifiable evidence handles

Recovery order:

1. Check artifacts, diff, tests, and files the child claims as evidence.
2. Inspect Hermes diagnostics/logs, especially `diagnostic_path` if present.
3. Retry once with a narrower task and explicit missing contract.
4. If parent fallback is necessary, label it as parent fallback and verify independently.

## Practical local config profile

For reliability-first subagent work, prefer conservative delegation settings:

```yaml
delegation:
  child_timeout_seconds: 1200
  max_iterations: 12
  max_concurrent_children: 1
  max_spawn_depth: 1
  subagent_auto_approve: true
  model: ""
  provider: ""
  base_url: ""
```

Rationale:

- `child_timeout_seconds: 1200` gives slow reasoning/network calls enough time to finish and write the handoff.
- `max_iterations: 12` gives the child enough turns for tool use plus final `SUBAGENT_RESULT`.
- `max_concurrent_children: 1` avoids provider throttling, approval races, and file conflicts while reliability is the priority. For explicit dual-model checks, temporarily raise it to `2` and keep the task read-only/bounded.
- `max_spawn_depth: 1` avoids nested subagent chains until contracts are stable.
- `subagent_auto_approve: true` avoids child stalls on tool approvals.
- Blank `model/provider/base_url` inherits the parent runtime; pin them only when a specific strong child model/provider is desired.

## Dual-process parallel pattern

For high-stakes research/review, run two independent **Hermes/agent processes** when budget allows:

- Process A: `DeepSeek-v4-pro` with increased shell/process timeout for slow reasoning/network tasks.
- Process B: `gemma4-31b` with the same task and independent wording.
- Launch both in parallel, e.g. two background `hermes chat -q ... --model ...` commands or two tmux sessions.
- Both prompts must cap output: final `SUBAGENT_RESULT` only, max 20 bullets total, no raw logs unless an artifact path is requested.
- Parent verifies evidence handles; agreement is not proof, disagreement creates `facts_to_verify` for a final pass.

Caveat: normal `delegate_task(tasks=[...])` uses one configured delegation model for all children, so use separate processes for heterogeneous model checks.

Do not write `~/.hermes/config.yaml` without explicit user approval. When inspecting it, print only delegation-related non-secret scalar fields and redact credentials.

## Evidence hierarchy

For root-cause or tuning claims, prefer:

1. Local runtime code/tests/config in `/home/konstantin/.hermes/hermes-agent`.
2. Local git history/commits in the same repo.
3. Local website docs in the repo.
4. Web/GitHub search with URLs and source dates.
5. Hypotheses clearly marked as hypotheses.

## Verification commands used in the session

```bash
cd /home/konstantin/.hermes/hermes-agent
pytest -q tests/tools/test_delegate_subagent_timeout_diagnostic.py tests/tools/test_delegate_toolset_scope.py tests/tools/test_delegate.py -q
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill subagent-driven-development --json
git diff --check
```

Expected result for the skill after the 2026-05-07 update: audit `ok=true`, `issues=[]`, `warnings=[]`.
