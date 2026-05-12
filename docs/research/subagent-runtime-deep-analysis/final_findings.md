# Subagent/delegate_task runtime deep analysis — findings

Date: 2026-05-07
Repo: `/home/konstantin/.hermes/hermes-agent`
Branch/HEAD inspected: `skills-improvements @ c829460ab2f0`
Current messaging session note: model switched to `gpt-5.5` via OpenAI Codex; persistent `~/.hermes/config.yaml` still has global default `glm-5.1:cloud` via `ollama-local`.

## Evidence sources

- Local code: `tools/delegate_tool.py`, `hermes_cli/config.py`.
- Local tests: `tests/tools/test_delegate.py`, `tests/tools/test_delegate_subagent_timeout_diagnostic.py`, `tests/tools/test_delegate_toolset_scope.py`.
- Local docs + current web docs fetched from `https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation`, `.../guides/delegation-patterns`, `.../user-guide/configuration`.
- Git history in local repo plus GitHub Search API artifacts under `/home/konstantin/docs/research/subagent-runtime-deep-analysis/api_responses/`.

## Local runtime facts

### Config defaults

From `hermes_cli/config.py:856-890`:

```yaml
delegation:
  model: ""                  # inherit parent model
  provider: ""               # inherit parent provider/credentials
  base_url: ""               # direct OpenAI-compatible endpoint
  api_key: ""                # direct endpoint key, fallback OPENAI_API_KEY only
  inherit_mcp_toolsets: true
  max_iterations: 50
  child_timeout_seconds: 600
  reasoning_effort: ""       # inherit parent reasoning level
  max_concurrent_children: 3
  max_spawn_depth: 1
  orchestrator_enabled: true
  subagent_auto_approve: false
```

Actual sanitized local `~/.hermes/config.yaml` has the same delegation values and no `DELEGATION_MAX_CONCURRENT_CHILDREN` / `DELEGATION_CHILD_TIMEOUT_SECONDS` env overrides.

### Timeout/concurrency/max_iterations behavior

From `tools/delegate_tool.py`:

- `max_concurrent_children`: config > env `DELEGATION_MAX_CONCURRENT_CHILDREN` > default 3; floor 1; warns above 10; batches above cap return tool error, not truncation (`lines 324-359`, `1895-1904`).
- `child_timeout_seconds`: config > env `DELEGATION_CHILD_TIMEOUT_SECONDS` > default 600; floor 30; implemented as `future.result(timeout=child_timeout)` around child `run_conversation()` (`lines 362-386`, `1410-1530`).
- Timeout result: `status="timeout"`, `exit_reason="timeout"`, `api_calls`, `duration_seconds`, and optional `diagnostic_path`. If API calls = 0, dump file is written to `~/.hermes/logs/subagent-timeout-...log`; if API calls > 0, message says likely stuck on slow API/network request (`lines 1455-1526`).
- Heartbeat to parent: every 30s. Current branch treats no-progress idle as stale after 5 cycles = 150s, and same-tool as stale after 20 cycles = 600s (`lines 476-487`, `1278-1338`). This can stop parent activity updates before child hard timeout.
- `max_iterations`: config-authoritative. The model-facing schema intentionally does not expose `max_iterations`; caller-supplied values are ignored. Each child gets its own independent 50-turn budget (`tests/tools/test_delegate.py:72-76`, `tools/delegate_tool.py:1868-1882`, `_build_child_agent:963-967`).
- Exit semantics: if child returns any final summary, runtime marks `status="completed"` even if `completed=False`; `exit_reason` then distinguishes `completed` vs `max_iterations` (`tools/delegate_tool.py:1541-1599`). Parent must check `exit_reason`, not just `status`.
- `delegate_task` is synchronous and not durable. If parent turn is interrupted, children are interrupted and result may not reach user-visible response (web docs `Lifetime and Durability`).
- Dangerous command prompts in subagent threads are non-interactive: default auto-deny; `delegation.subagent_auto_approve: true` auto-approves only if explicitly enabled (`config.py:881-889`, `delegate_tool.py:59-106`).

### Current local config implication

With current config and current session model override:

- Subagents inherit the parent runtime model/provider because `delegation.model/provider` are empty.
- If parent is `gpt-5.5` via OpenAI Codex, children use the same slow/high-reasoning runtime unless the runtime parent is different.
- 600s hard timeout may be okay for simple tasks but can be tight for high-reasoning review/research.
- 150s idle heartbeat stale threshold is the more likely source of parent-turn/gateway interruption before the child returns.

## Commits relevant to subagent reliability

Commits present in current HEAD:

- `90e521112` — initial `delegate_task` tool: isolated child agents, single/batch up to 3.
- `14396e3fe` — default `max_iterations` 25 -> 50.
- `68ab37e89` — independent subagent iteration budgets; config-controlled `delegation.max_iterations`.
- `7ccdb7436` — `max_concurrent_children` configurable; error on excess instead of silent truncation.
- `a093eb47f` — propagate child activity to parent to avoid gateway inactivity timeout.
- `718e8ad6f` — configurable `delegation.reasoning_effort`.
- `48ecb98f8` — `role="orchestrator"` and `max_spawn_depth`, default flat.
- `dd8ab4055` — hard child timeout and stale detection.
- `64e616568` — remove model-facing `max_iterations`; config authoritative.
- `50d97edbe` — default `child_timeout_seconds` 300 -> 600 because high-reasoning models timed out at 300s.
- `7634c1386` — diagnostic dump for 0-API-call timeout.
- `fcc05284f` — tool-activity-aware heartbeat stale detection.
- `023b1bff1` — non-interactive approval resolution to avoid TUI deadlock.

Relevant upstream/local-history commits NOT in current HEAD but present in repo/GitHub search:

- `0cc63043e` — increases heartbeat stale thresholds from idle 150s -> 450s and in-tool 600s -> 1200s. Directly relevant to “subagent runs but parent gets no information”.
- `d17eff29d` — guards `_load_config()` against `delegation: null` crashing.
- `83080772f` — honors `delegation.provider` by clearing parent provider-preference filters.
- `83bbe9b45` — passes `target_model` to runtime provider resolution.
- `9faaa292b` — child inherits parent fallback chain.
- `e795b7e3a` — expands composite toolsets before intersection, so parent composite toolset does not strip child `web`/`terminal` unexpectedly.
- `69692039e` — docs correction for Claude Code ACP flag.

## Web/docs findings

Current web docs confirm:

- Only final summary returns to parent; child intermediate tool calls do not enter parent context.
- Batch default is 3 concurrent children; configurable by `delegation.max_concurrent_children` or env.
- `child_timeout_seconds` default is 600, timer resets on activity, and 0-API-call timeouts produce diagnostic dump.
- `delegate_task` is synchronous, not durable; parent interrupt cancels children.
- `max_spawn_depth` default is 1; orchestrator requires depth >=2.

Docs inconsistency found:

- Web docs still show a `delegate_task(..., max_iterations=10)` example, but local tests and current schema say `max_iterations` is intentionally not exposed to model and config is authoritative. This should be corrected in docs/skill references.
- Local `delegate_tool.py:1852-1853` has a stale comment saying “default 2” while the actual default and tests say `max_spawn_depth=1`.

## Recommended changes

### Immediate config tuning (no code changes)

Conservative reliability profile for high-reasoning subagents:

```yaml
delegation:
  max_iterations: 80
  child_timeout_seconds: 1200
  max_concurrent_children: 2
  max_spawn_depth: 1
  orchestrator_enabled: true
  subagent_auto_approve: false
  reasoning_effort: "high"
```

Rationale:

- Increase timeout to 20 minutes for slow reasoning/network stalls.
- Increase iteration budget so a child can finish and return a structured handoff.
- Reduce concurrency to 2 to avoid provider rate limits, latency spikes, and token spend multiplication.
- Keep nested delegation flat until parent-child contract is stable.
- Keep dangerous commands auto-denied unless running trusted automation.
- Use `reasoning_effort: high` only if `xhigh` children are too slow; for low-risk mechanical subtasks use `medium`, but this may reduce reliability on complex analysis.

CLI form:

```bash
hermes config set delegation.max_iterations 80
hermes config set delegation.child_timeout_seconds 1200
hermes config set delegation.max_concurrent_children 2
hermes config set delegation.max_spawn_depth 1
hermes config set delegation.subagent_auto_approve false
hermes config set delegation.reasoning_effort high
```

### Core/runtime changes worth applying/cherry-picking

Priority order:

1. `0cc63043e` heartbeat stale thresholds: prevents parent/gateway from deciding the child went quiet after only 150s.
2. `d17eff29d` null-config guard: small robustness patch.
3. `e795b7e3a` composite toolset expansion: prevents empty child toolset when parent uses composite toolsets.
4. `9faaa292b`, `83bbe9b45`, `83080772f`: provider/fallback reliability if delegation provider/model overrides are used.
5. Fix stale docs/comments: remove `max_iterations` call example from docs, fix `default 2` comment in `delegate_tool.py`.

### Skill/contract behavior

The skill-level contract remains necessary because runtime does not validate semantic success. Runtime can say `status="completed"` for a summary even when `exit_reason="max_iterations"`; parent must require a structured `SUBAGENT_RESULT` and treat timeout/error/interrupted/empty/unverifiable/max_iterations as not safe to continue.

Minimum parent acceptance gate:

- `delegate_task` returned JSON with `results`.
- Every child result has `status`, `summary`, `exit_reason`, `api_calls`, `duration_seconds`.
- Child summary contains `SUBAGENT_RESULT` with `status: PASS|FAIL|BLOCKED|PARTIAL`, evidence, files touched, verification, open issues, and `safe_to_continue`.
- Parent must not silently do the delegated work after lost/empty/timeout child result; it must retry, narrow the task, or report the delegation failure.

## Verification performed

```bash
pytest -q tests/tools/test_delegate_subagent_timeout_diagnostic.py tests/tools/test_delegate_toolset_scope.py tests/tools/test_delegate.py -q
```

Result: passed, 100% for selected delegate tests.

Artifacts:

- `/home/konstantin/docs/research/subagent-runtime-deep-analysis/git_commits_subagents.md`
- `/home/konstantin/docs/research/subagent-runtime-deep-analysis/git_commits_subagents.json`
- `/home/konstantin/docs/research/subagent-runtime-deep-analysis/github_api_commit_summary.md`
- `/home/konstantin/docs/research/subagent-runtime-deep-analysis/extracts/`
- `/home/konstantin/docs/research/subagent-runtime-deep-analysis/api_responses/`
