# Context Optimization Planning Workflow

Use this reference when asked to plan Hermes input-context overhead optimization from existing baseline/audit artifacts without implementing runtime changes.

## Trigger

A user asks for a planning-only Hermes context/input-overhead optimization plan, especially with constraints like:
- no runtime/config/prompt-builder/transport/context-compressor/toolset/analyzer changes;
- no `state.db`, JSONL transcript, or request dump reads;
- no real LLM/API calls;
- no commit/push;
- preserve baseline and distinguish provider input from snapshot/storage overhead.

## Safe workflow

1. Load `hermes-agent` and a planning skill.
2. Check branch and dirty state first:
   ```bash
   git status --short --branch --untracked-files=all
   git log -2 --oneline
   git diff --stat
   git diff --name-only
   ```
3. Verify the checkpoint before writing the plan:
   ```bash
   python -m py_compile scripts/analyze_context_overhead.py
   pytest tests/test_analyze_context_overhead.py -q
   ```
   If tests are unexpectedly missing because a tracked test file is deleted in the worktree, restore only that tracked file if doing so is necessary to satisfy the explicit checkpoint verification and does not conflict with the user's requested changes. Report it as pre-existing state correction.
4. Generate the requested baseline report with the analyzer only. Do not read prohibited data sources directly.
5. Read only the allowed baseline/audit docs and generated report artifacts.
6. Write only the requested plan markdown file. Keep it cautious:
   - confirmed vs estimated vs uncertain;
   - provider input vs snapshot/storage overhead;
   - no claims that optimization has already happened;
   - target ranges as hypotheses requiring experiments.
7. Re-run verification and safety checks:
   ```bash
   python -m py_compile scripts/analyze_context_overhead.py
   pytest tests/test_analyze_context_overhead.py -q
   git status --short --branch --untracked-files=all
   git diff --stat
   git diff -- <plan-file>
   git diff | grep -Ei 'api[_-]?key|token|secret|password|authorization|bearer' || true
   ```
   For a new untracked plan file, `git diff -- <plan-file>` is empty unless the file is intent-to-add. Use `git add -N <plan-file>` if the user explicitly requested a diff for the new file, but do not commit.

## Plan content checklist

Include:
- scope and non-goals;
- baseline source paths;
- current known facts;
- confirmed provider input;
- snapshot/storage overhead;
- uncertain items;
- optimization priorities;
- safe staged order;
- validation metrics;
- rollback strategy;
- recommended future task queue.

Recommended stages for context-overhead optimization plans:
1. preserve baseline and success criteria;
2. tool outputs policy;
3. toolset narrowing;
4. cronjob schema reduction;
5. skills mandatory/index reduction;
6. system prompt hygiene;
7. prompt caching alignment;
8. compression/context-compressor tuning;
9. staged validation.

## Pitfalls

- Do not count Codex storage/transcript fields as standard chat-completions provider input.
- Do not treat prompt caching as logical token reduction; it is a cost/latency dimension.
- Do not promise percentage savings without before/after experiments.
- Do not read `state.db`, JSONL transcripts, or request dumps when the task forbids them.
- Do not delete backup files while cleaning status.
- `grep -Ei 'token|secret'` may match benign words like "tokens" in docs; report false positives clearly rather than editing them away.
