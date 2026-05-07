# Daily Knowledge Distillation — Detailed Workflow

Turn recent Hermes conversations into compact, curated, file-backed knowledge for Konstantin.

## Applicability

Use for:
- Scheduled daily knowledge-distillation cron
- Manual requests to "distill", "выжать знания", "актуализировать docs", or clean/curate memory
- Durable updates about user preferences, infrastructure, runbooks, plans, decisions, reusable pitfalls

Do NOT use for:
- External semantic memory setup
- Raw transcript archival
- Model benchmarking/setup details (brief references go to `runbooks.md`)

## Workflow

### 1. Read current state

Before processing sessions, read:
1. `/home/konstantin/docs/README.md`
2. `/home/konstantin/docs/user-context.md`
3. `/home/konstantin/docs/infrastructure.md`
4. `/home/konstantin/docs/runbooks.md`
5. Relevant `plans/*.md` when recent work mentions plans

Purpose: avoid duplicates and contradictions.

### 2. Gather source material with a budget

Use `session_search` to inspect recent sessions (no date filter available — state this limitation and use most recent relevant sessions).

**Default source budget:**
- Target evidence packet: 8k–12k chars
- Hard cap: 15k chars
- Usually 8–12 high-signal snippets, not full transcripts
- Relevant docs sections only
- Raw logs/model outputs/command dumps only as one-line summaries

**Priority when material exceeds budget:**
1. Direct user corrections / "remember" / "avoid this mistake"
2. Verified infrastructure changes: paths, job IDs, model pinning, schedules
3. Completed plan status changes
4. Reusable runbook lessons and pitfalls
5. Durable user/work preferences
6. Other items only if they clearly prevent future mistakes

If there is no useful material, output "no changes". Do not invent facts.

### 2.5 Multi-agent ensemble extraction (2-tier architecture)

Use the 2-tier ensemble for scheduled cron jobs. Fall back to single-agent for ad-hoc manual requests.

**Architecture:**
```
Orchestrator / cron entrypoint (gpt-5.5)
  ├── session_search → gather snippets
  ├── execute_code: parallel HTTP → 2 Ollama Cloud workers (same data, independent extraction)
  ├── merge + dedup + vote counting
  └── gpt-5.5 curator: curate + write docs
```

**Worker models (tier 1 — extraction only):**

| Model | Ollama tag | Label | max_tokens | JSON behavior | Notes |
|---|---|---|---|---|---|
| GLM 5.1 | `glm-5.1:cloud` | `glm` | 3000 | `json_object` ✅, wraps ` ```json ` | Fast (8-10s), Russian-native |
| Gemma 4 31B | `gemma4:31b-cloud` | `gemma` | 3000 | `json_object` ✅, wraps ` ```json ` | Cross-validation voice (5-10s) |

`deepseek-v4-pro:cloud` is excluded from the production worker pool pending an explicit user decision, but do **not** frame this as “DeepSeek is bad.” The 2026-05-07 benchmarks showed configuration-specific failure modes and the fix: legacy `/v1/chat/completions` spent budget on hidden reasoning; native `/api/chat` + `format:"json"` + `think:false` removed hidden reasoning; the old verbose worker prompt still truncated visible JSON; a tuned output contract (`max 10 candidates`, concise claim/reason) made DeepSeek pass repeated production-shaped JSON benchmarks even at `num_predict=3000`. Do not add it back to `WORKER_MODELS` without a fresh multi-run task-specific benchmark under the intended config and user approval. The worker script has a manual/native branch for this model (`/api/chat`, `format:"json"`, `think:false`, `options.num_predict`) so benchmarks can test DeepSeek without rerouting GLM/Gemma or changing the production pool. See `references/deepseek-native-distillation-benchmark-2026-05-07.md`.

**Curator (tier 0/2):** `gpt-5.5` via OpenAI Codex. Fallback: `gpt-oss:120b-cloud` (report explicitly).

> **Runtime-state rule:** Do not treat compacted session summaries or old benchmark notes as authoritative for curator availability. Verify current runtime/provider state before reporting that gpt-5.5 is unavailable.

**Why same data in all workers:** Cross-validation — if both worker models find the same claim, confidence is higher. Different slices would be cheaper but kill voting.

**Worker prompt design (critical):**
1. **System prompt in ENGLISH** — `glm-5.1:cloud` returns empty content with `json_object` mode + Russian system prompt (verified bug).
2. **Mandatory: `json_object` + explicit enum values** in system prompt. Do NOT use `json_schema` strict mode — broken for ALL Ollama Cloud models. See `references/json-schema-benchmark.md`.
3. **3-level fallback parser:** direct JSON parse → strip `\`\`\`json...\`\`\`` fences → find first `{...}` block.
4. **Thinking models:** reasoning tokens may appear as `message.reasoning_content` or `message.reasoning` and count toward `max_tokens`. For DeepSeek V4 Pro, do not blame the model when the worker fails; first check endpoint, thinking control, output cap, and token budget. Manual DeepSeek benchmarks should use the worker's native Ollama branch (`/api/chat`, `format:"json"`, `think:false`) plus a concise output contract (`max 10 candidates`, short claim/reason). Native `think:false` removes the hidden-reasoning failure mode; the concise output cap prevents visible JSON truncation. Always check `done_reason`, parse success, valid candidate count, and repeated-run stability.
5. **Timeout per worker:** 200s. Skip failed workers, continue with results that returned.
6. **kimi-k2.6 is NOT viable** as a worker: 3.5–7K reasoning tokens, output truncation, unreliable JSON.

### 3. Extract candidates, not conclusions

Candidate schema:

| Field | Values |
|---|---|
| claim | Declarative factual statement (Russian for this user). One thought per entry. |
| evidence_type | `direct_user_instruction`, `repeated_correction`, `verified_infrastructure`, `verified_tool_result`, `session_summary`, `model_inference`, `agent_mistake_lesson` |
| durability | `high`, `medium`, `low` |
| destination | `user-context.md`, `infrastructure.md`, `runbooks.md`, `memory`, `skip` |
| action | `add`, `update`, `remove`, `skip` |
| reason | Why worth saving (Russian) |

Default action preference: `skip` → `update` → `add` → `remove`. Remove only with clear evidence.

### 4. Candidate quality gate

Before any write:
1. Will this matter weeks from now?
2. Is evidence direct, verified, or inferred?
3. Will saving it prevent a future mistake or clarification?
4. Is it already in built-in memory, docs, or a skill?
5. Is docs the right destination, or should it remain in `session_search`?
6. Is it raw output, task progress, temporary state, or a one-off incident?
7. Does writing require explicit approval?
8. Can it update an existing entry instead of adding one?
9. Is the claim about permissions, ACLs, OAuth/API scopes, credentials, cron schedules, model pinning, or write capability? If yes, it requires current verification or must be written as explicitly unverified.
10. Does the claim collapse "not tested" into "not enabled"? If yes, reject or rephrase.

**Evidence ladder:**

| Evidence type | Trust level |
|---|---|
| Direct user instruction / repeated correction | highest |
| Current verified tool/API/config result | highest for operational state |
| Verified command/path/job/config/schedule | high if stable |
| Session summary of old run | medium; verify before changing operational facts |
| One agent mistake | save only as abstracted rule |
| Model recommendation / benchmark interpretation | save only scoped with limitations |
| Model inference from snippets | low; never enough for permissions/write capability |
| Current chat/model/session state | usually skip |
| Raw output/log/transcript | skip |

### 5. Merge + dedup + voting

- Normalize claims (lowercase, strip punctuation, collapse whitespace) for dedup.
- Claims found by 2+ workers → `confidence: high/medium`. Single-model claims → `confidence: low`.
- Auto-skip: `durability=low` + `confidence=low` → remove from curated list.
- Sort: high confidence first, then high durability.
- Pass merged list with vote metadata to curator.

### 6. Edit conservatively

Before editing:
1. Read the target file
2. Search `/home/konstantin/docs/` for key terms
3. Decide add/update/remove/skip

Prefer targeted patches. Good: add one row, replace an outdated fact, add one pitfall. Bad: daily "Today" sections, full session summaries, overlapping preference bullets.

### 7. Post-write verification
8. Report verification level precisely: implemented-only, static/unit/mocked, live smoke, or production-shaped benchmark. Do not say a model/provider was “checked” in production if only unit/mocked or tiny live smoke verification was run. For the detailed reporting pattern, see `references/verification-claims-2026-05-07.md`.

After any edit:
1. Re-read the changed section
2. Search for duplicates/conflicts
3. Confirm no secrets, raw logs, or token-like values were saved
4. Confirm mode compliance: dry-run/benchmark must not edit docs/plans/skills/config/memory/cron
5. Ensure final report describes actual changes
6. Report failed/partial patches explicitly

## Audit Report Format

```text
## Daily knowledge distillation
Mode:
Sources checked:
Added:
Updated:
Removed:
Skipped:
Needs user decision:
Files changed:
Built-in memory changed:
Limitations:
```

If nothing changed, say so. "No changes" is a valid success.

## Cron Guidance

For daily cron: be autonomous; no questions; skip if uncertain; don't schedule jobs; small patches; put uncertainty under `Limitations` or `Needs user decision`; end with audit report delivered to Telegram.

Setup/maintenance and model-benchmark procedures live in `/home/konstantin/docs/runbooks.md`.

## Distillation-Specific Pitfalls

1. Appending instead of curating → prefer update/replace/skip.
2. Saving task progress as knowledge → keep durable facts/procedures/decisions only.
3. Duplicating built-in memory → docs may expand, not mirror line-for-line.
4. Treating absence as obsolescence → do not delete because something was not mentioned today.
5. Storing secrets → redact values; paths to credential files are also risky.
6. Creating long daily reports in docs → reports go to Telegram/output; docs get distilled knowledge.
7. Patching docs per batch → batches produce candidates only; controller performs one serial merge/write/verify.
8. Cron without pinned model → model defaults to Hermes default, which may not support Russian or json_object. Always pin explicitly.
9. Russian system prompt + `glm-5.1:cloud` + `json_object` → empty content (verified bug). Use English system prompt, Russian data fields.
10. **NEVER use `ollama run` / `ollama pull` for cloud models (`:cloud` suffix).** This fills the filesystem and can crash Hermes (ENOSPC). Cloud models use HTTP API only.
11. `json_schema` strict mode is broken for Ollama Cloud — use `json_object` + explicit enum values. See `references/json-schema-benchmark.md`.
12. Thinking models (deepseek-v4-pro) → reasoning tokens can consume `/v1` `max_tokens`; native `/api/chat` with `format:"json"` + `think:false` avoids hidden reasoning. If native JSON still fails, tune the output contract before judging the model: cap candidates (`max 10`), shorten claim/reason, then test `num_predict` budgets. Keep DeepSeek out of production `WORKER_MODELS` until repeated task-shaped benchmarks pass under the intended config and the user explicitly approves.
13. Markdown codeblock wrapping is cosmetic. Same 2-line fallback parser handles both.
14. kimi-k2.6 is not viable as a distillation worker.
15. Credential paths in docs → even paths are leaked metadata. Store only "(see config)".
16. Updating this skill does NOT update the scheduled cron job prompt. Audit and patch both.
17. Scope vs permission confusion → never equate an API/OAuth scope with the account's real permissions.
18. "Not tested" is not "not enabled".
20. Verification wording pitfall: “implemented”, “unit/mocked verified”, “live smoke verified”, and “production-shaped benchmark passed” are different claims. If only a tiny payload was run, say live smoke; do not imply the model is production-ready or comparable to the cron workload.