---
name: daily-knowledge-distillation
description: Use when distilling recent Hermes sessions into curated file-backed long-term memory. Update /home/konstantin/docs/ conservatively, avoid duplicates/secrets/raw logs, use add/update/remove/skip, batch large inputs candidate-only, and report what changed or was skipped.
version: 1.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [memory, knowledge-management, distillation, docs, cron, curation]
    related_skills: [hermes-agent, writing-plans]
---

# Daily Knowledge Distillation

## Overview

Turn recent Hermes conversations into curated persistent knowledge for Konstantin. Route: facts → fact_store, procedures → skills, details → docs, MEMORY = index+guardrails only. The goal is not to append text; it is to keep `/home/konstantin/docs/` and `fact_store` accurate, useful, non-duplicative, and less stale. A successful run may make no changes.

Konstantin prefers compact curated memory. Do not blindly save interesting sentences, daily diaries, raw logs, long model outputs, secrets, or temporary task progress.

## When to Use

Use for:

- the scheduled daily knowledge-distillation cron;
- manual requests to “distill”, “выжать знания”, “актуализировать docs”, or clean/curate memory;
- durable updates about user preferences, Hermes/Ollama/Codex/cron/memory infrastructure, runbooks, plans, decisions, and reusable pitfalls.

Do not use for:

- external semantic memory setup;
- raw transcript archival;
- model benchmarking/setup details except as brief references. Use `/home/konstantin/docs/runbooks.md` for those procedures.

## Canonical Destinations

Read `/home/konstantin/docs/README.md` first. Route candidates as follows:

```text
user-context.md     user identity, communication contract, durable preferences, work-context hypotheses
infrastructure.md   Hermes/Ollama/Codex/cron/memory paths, providers, automations, risks
runbooks.md/skills  repeatable commands, procedures, troubleshooting, operational pitfalls
plans/*.md          multi-step intentions, status, verification criteria
session_search      detailed history, raw evidence, transcripts, temporary context
fact_store          atomic durable facts, entity recall, trust feedback (default for facts)
built-in memory     index pointers + known-wrong + holographic hygiene + DO-NOT-EDIT guardrail ONLY
                    facts → fact_store; procedures → skills; details → docs. No behavioral rules that SOUL/USER cover.
```

## Execution Modes

Declare mode before any side effect.

### Normal distillation

For scheduled cron or explicit “update/actualize docs”. Allowed: read sources, patch `/home/konstantin/docs/` conservatively, update plan status with evidence, and send audit report. Built-in memory may be updated only for: index pointers, known-wrong entries, holographic hygiene triggers, or the DO-NOT-EDIT guardrail. All other facts go to fact_store (search before add, update not duplicate). Behavioral rules already in SOUL/USER must not be duplicated in MEMORY; report the memory change. Forbidden unless explicitly requested: cron/model/config/credential/memory-provider changes or scheduling new jobs from a cron run.

### Dry-run

For analysis, proposed changes, review, or “do not edit docs/files”. Allowed: read and report proposals; scratch files only under `/tmp` if needed. Forbidden: editing docs, `plans/`, skills, config, built-in memory, cron, credentials, or external systems.

### Benchmark

For comparing models/prompts. Allowed: fixed prompt/result/raw-output files under `/tmp` and final comparison. Forbidden: editing docs/plans/skills/config/memory/cron/model pinning/credentials, creating plan files unless explicitly allowed, or storing model rankings as durable facts before raw outputs/limitations are reviewed.

### Ad-hoc interaction-pattern retrospective

Use this mode when Konstantin asks to analyze interaction history, extract effective/failed patterns, or run an ensemble over session evidence. This is not routine memory writing: default to `/tmp` artifacts, no raw transcripts, no credentials/credential paths, and no docs/memory/skill edits unless explicitly requested. Build a safe JSON evidence packet from docs + fact_store + targeted `session_search`, run requested models on the same packet, save raw and compact synthesis JSON, secret-scan artifacts, then report evidence → analysis → guardrails. See `references/interaction-patterns-ensemble-2026-05-06.md` for a worked pattern and model notes.

If the user says “do not edit files”, interpret broadly: no docs, `plans/`, skills, config, memory, cron, or credentials. Only `/tmp` scratch is acceptable; report that target files were untouched.

## Workflow

### 1. Read current state

Before sessions, read:
1. `/home/konstantin/docs/README.md`
2. `/home/konstantin/docs/user-context.md`
3. `/home/konstantin/docs/infrastructure.md`
4. `/home/konstantin/docs/runbooks.md`
5. relevant `plans/*.md` when recent work mentions plans.
6. `fact_store` — probe relevant entities (user, project names, tools mentioned in snippets) to check for existing facts and avoid duplicates.

Purpose: avoid duplicates and contradictions.

### 2. Gather source material with a budget

Use `session_search` to inspect recent sessions. If date filtering is unavailable, state that limitation and use the most recent relevant sessions.

Default source budget:

- target evidence packet: 8k–12k chars;
- hard cap: 15k chars unless the selected model reliably handles more;
- usually 8–12 high-signal snippets, not full transcripts;
- relevant docs sections only;
- raw logs/model outputs/command dumps only as one-line summaries.

Priority when material is too large:

1. direct user corrections / “remember” / “avoid this mistake”;
2. verified infrastructure changes: paths, job IDs, model pinning, schedules;
3. completed plan status changes;
4. reusable runbook lessons and pitfalls;
5. durable user/work preferences;
6. other items only if they clearly prevent future mistakes.

If there is no useful material, output “no changes”. Do not invent facts.

### 2.5 Multi-agent ensemble extraction (2-tier architecture)

Use the 2-tier ensemble when distillation runs as a scheduled cron job and cost/quality tradeoff favors small parallel workers + one high-quality curator. Fall back to single-agent for ad-hoc manual requests.

**Architecture:**

```
Orchestrator / cron entrypoint (OpenAI Codex gpt-5.5)
  ├── session_search → gather snippets
  ├── execute_code: parallel HTTP → 2 Ollama Cloud worker models (same data, independent extraction)
  ├── merge + dedup + vote counting
  └── gpt-5.5 curator logic: curate + write docs
```

**Worker models (tier 1 — extraction only):**

| Model | Ollama tag | Label | max_tokens | JSON behavior | Notes |
|---|---|---|---|---|---|
| GLM 5.1 | `glm-5.1:cloud` | `glm` | 3000 | `json_object` ✅, wraps ` ```json ` | Fast (8-10s), Russian-native |
| Gemma 4 31B | `gemma4:31b-cloud` | `gemma` | 3000 | `json_object` ✅, wraps ` ```json ` | Cross-validation voice (5-10s), different architecture |

`deepseek-v4-pro:cloud` is intentionally excluded from the production worker pool. Verified cron-shaped repro on 2026-05-01: with the same worker HTTP call (`json_object`, English system prompt, 12k snippet packet, `max_tokens=3000`, `timeout=200`) it exited in 92.6–113s but consumed the full 3000 completion tokens mostly in hidden `message.reasoning` (~12.7k chars) and returned only 127 chars of incomplete JSON content; result = non-parseable worker output, not a useful candidate list. Do not add it back without a fresh task-specific benchmark and explicit user decision. See `references/deepseek-worker-repro-2026-05-01.md` for the repro transcript and guardrail rationale; use `scripts/reproduce_deepseek_worker.py` when re-benchmarking.

**Curator/orchestrator model (tier 0/2 — cron entry + final decisions + write):**

| Role | Model | Notes |
|---|---|---|
| Cron entry / orchestrator / primary curator | `gpt-5.5` via OpenAI Codex | Single model for the cron job session and final curation. It gathers snippets, calls Ollama workers through `execute_code`, merges/votes candidates, reads current docs, makes final accept/reject/update/remove decisions, writes targeted patches, and returns audit report. |
| Fallback curator | `gpt-oss:120b-cloud` | Use only if OpenAI Codex / gpt-5.5 is unavailable, and report that fallback explicitly. |

> **Runtime-state rule:** do not treat compacted session summaries or old benchmark notes as authoritative for curator availability. Verify the current runtime/provider state before reporting that gpt-5.5 is unavailable, and phrase fallback decisions as conditional unless freshly checked.

**Why same data in all workers (not different slices):**

Cross-validation is the core value. If 2 of 3 models find the same claim, confidence is higher. Different slices would be cheaper but kill voting — gemma can't confirm what glm found if it didn't see the same sessions.

**Worker prompt design (critical):**

1. **System prompt in ENGLISH** — glm-5.1:cloud returns empty content with `json_object` mode + Russian system prompt (verified bug). English system prompt + Russian data fields (claim, reason) avoids this.
2. **Mandatory: `json_object` + explicit enum values in system prompt**. Do NOT use `json_schema` strict mode — it is broken for ALL models through Ollama Cloud. Every tested model (glm, deepseek, gemma, gpt-oss, kimi) ignores `json_schema` enum constraints: they produce their own categories instead of the defined enum, and return float confidence (e.g. `0.95`, `1.0`) instead of string enum (`"high"`, `"medium"`, `"low"`). The `json_object` mode + enums written as text in the prompt is the only reliable approach — all 7 tested models comply.
3. **Fallback parser**: 3-level — direct JSON parse → strip ` ```json...``` ` fences → find first `{...}` block. Handles all observed model quirks. Models that wrap in codeblocks: glm-5.1, gemma4, gpt-oss:20b, kimi-k2.6. Models that return raw JSON: deepseek-v4-pro, deepseek-v4-flash, gpt-oss:120b. The difference is cosmetic — same 2-line parser handles both.
4. **Thinking models**: deepseek-v4-pro and deepseek-v4-flash may return hidden reasoning as either `message.reasoning_content` or `message.reasoning`. Reasoning tokens count toward max_tokens. For daily distillation DeepSeek V4 Pro was repro-tested with cron-shaped input and returned incomplete JSON after spending the budget on reasoning; this is the operational root cause for excluding it from the production worker pool.
5. **Timeout per worker**: 200 seconds for every worker. Skip failed workers, continue with results that returned.
6. **kimi-k2.6 is not viable as a worker**: 3.5–7K reasoning tokens on trivial prompts, output truncation at 1500 completion tokens, unreliable JSON. Do not use.

**JSON Schema for worker response:**

```json
{
  "type": "object",
  "properties": {
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "claim": {"type": "string", "description": "Declarative factual statement in Russian. One thought per entry."},
          "evidence_type": {"type": "string", "enum": ["direct_user_instruction", "repeated_correction", "verified_infrastructure", "verified_tool_result", "session_summary", "model_inference", "agent_mistake_lesson"]},
          "durability": {"type": "string", "enum": ["high", "medium", "low"]},
          "destination": {"type": "string", "enum": ["user-context.md", "infrastructure.md", "runbooks.md", "fact_store", "memory", "skip"]},
          "action": {"type": "string", "enum": ["add", "update", "remove", "skip"]},
          "reason": {"type": "string", "description": "Why worth saving. In Russian."}
        },
        "required": ["claim", "evidence_type", "durability", "destination", "action", "reason"],
        "additionalProperties": false
      }
    }
  },
  "required": ["candidates"],
  "additionalProperties": false
}
```

**Merge + dedup + voting:**

- Normalize claims (lowercase, strip punctuation, collapse whitespace) for dedup.
- Claims found by 2+ workers → `confidence: high/medium`. Single-model claims → `confidence: low`.
- Auto-skip: `durability=low` + `confidence=low` → remove from curated list.
- Sort: high confidence first, then high durability.
- Pass merged list with vote metadata to curator.

**Curator receives:**

- Merged candidate list (~2-3k chars, not raw sessions)
- Current state of `/home/konstantin/docs/` files (read by curator)
- Instruction: accept/reject/skip each candidate, write changes, return audit report

**Reference implementation:** `scripts/distillation_worker.py` in the skill directory (`~/.hermes/skills/note-taking/daily-knowledge-distillation/scripts/distillation_worker.py`). Contains: worker system prompt, JSON schema, API call utils, 3-level fallback parser, merge/dedup with voting, curator format function, and `run_distillation()` async entry point. Run via `execute_code` — import and call `run_distillation(session_snippets)`.

**Legacy single-batch mode (still valid for manual runs):**

When not using the ensemble, use simple batching. Batching is candidate-only. Never patch docs per batch. Split batches around 4k–7k chars or 3–5 related snippets. Batch workers return candidates only. Merge serially. Only the controller performs final decision, docs patch, and verification.

### 3. Extract candidates, not conclusions

Use this schema mentally or in scratch:

```text
Candidate:
- claim
- evidence/source summary
- evidence type: direct_user_instruction | repeated_correction | verified_infrastructure | verified_tool_result | session_summary | model_inference | agent_mistake_lesson | current_session | raw_log
- durability: high | medium | low
- destination: user-context.md | infrastructure.md | runbooks.md | fact_store | memory | skip
  (default for facts: fact_store; memory only for index/guardrails)
- action: add | update | remove | skip
- reason/risk
```

Usually write only high-durability items. Medium is acceptable only when operationally important and scoped. Low is skipped.

### 4. Candidate quality gate

Before any write, answer:

1. Will this matter weeks from now?
2. Is evidence direct, verified, or inferred?
3. Will saving it prevent a future mistake or clarification?
4. Is it already in built-in memory, docs, or a skill?
5. Is docs the right destination, or should it remain in `session_search`?
6. Is it raw output, task progress, temporary state, or a one-off incident?
7. Does writing require explicit approval?
8. Can it update an existing entry instead of adding one?
9. Is the claim about permissions, ACLs, OAuth/API scopes, credentials, cron schedules, model pinning, or write capability? If yes, it requires a current tool/API/config verification or must be written as explicitly unverified / `Needs user decision`.
10. Does the claim collapse “not tested”, “not used by this script”, “read-only scope”, or “not observed in sessions” into “not enabled” or “impossible”? If yes, reject or rephrase.
11. Does the candidate turn a single incident or unverified explanation into a broad rule/prohibition? If yes, reject or shrink it to the minimal verified command/procedure/pitfall. Do not create “rails” from conjecture.

Default action preference: `skip` → `update` → `add` → `remove`. Remove only with clear evidence that an entry is obsolete, duplicated, misleading, or unsafe.

For candidates with `destination=fact_store`: ensure the claim is atomic (one assertion per entry), includes an entity name for `fact_store` tagging, and is checked for duplicates via `fact_store search`/`probe` before adding. Apply holographic hygiene: search before add → update not duplicate.

Evidence ladder:

```text
direct user instruction / repeated correction        high
current verified tool/API/config result              highest for current operational state
verified command/path/job/config/schedule             high if stable
session summary of old run                            medium; verify before changing operational facts
one agent mistake                                     save only as abstracted rule
model recommendation / benchmark interpretation       save only scoped with limitations
model inference from snippets                         low; never enough for permissions/write capability
current chat/model/session state                      usually skip
raw output/log/transcript                             skip
```

**Operational-fact verification gate:** claims about external-system permissions, account roles, OAuth scopes, API write capability, credentials, cron schedules, delivery targets, provider/model pinning, or filesystem paths must be either:

- backed by a fresh tool/API/config check in the current run;
- copied from an already verified current doc section and marked as such; or
- left out / reported under `Needs user decision`.

Never infer permissions from a successful read. A successful `list`/digest proves read access only. It does not prove the account lacks write access.

### 5. Agent mistake handling

When Konstantin corrects the agent, do not save the incident as a diary item. Extract the durable behavioral rule.

Bad: `On 2026-04-27 the assistant created a benchmark plan incorrectly.`

Good: `When the user says not to edit files, treat that as including docs, plans, skills, config, memory, and cron unless explicitly exempted.`

Save the rule only if it is likely to change future behavior.

### 6. Edit conservatively

Before editing:
1. read the target file (or probe/update fact_store for fact_store destinations);
2. search `/home/konstantin/docs/` for key terms; `fact_store search` for fact candidates;
3. decide add/update/remove/skip.

Prefer targeted patches. Good: add one row, replace an outdated fact, add one pitfall, mark plan status with evidence. Bad: daily “Today” sections, full session summaries, overlapping preference bullets, whole-file rewrites without structural need.

### 7. Secrets and privacy

Never save credential values: OAuth tokens, API keys, passwords, tokenized webhook URLs, cookies, full auth JSON. Credential **file paths** are also sensitive metadata — store only section references like "(see himalaya config)" or "(see gcal section below)", not actual filesystem paths.

### 8. Post-write verification

After any edit:

1. re-read the changed section;
2. search for duplicates/conflicts;
3. confirm no secrets, raw logs, token-like values, or transcripts were saved;
4. confirm mode compliance: dry-run/benchmark must not edit docs/plans/skills/config/memory/cron;
5. ensure final report describes actual changes;
6. report failed/partial patches explicitly.

Fix or revert questionable edits before finalizing.

## Plans Handling

Konstantin's rule: for multi-step AI-agent work, what is not in `/home/konstantin/docs/plans/` is not really planned.

During normal distillation:

- update existing plan status/checklists only with evidence;
- create a plan only for clear future multi-step work and only if the current mode permits edits;
- never treat plan files as exempt from “do not edit files”.

## Cron Guidance

For the daily cron: be autonomous; do not ask questions; skip if uncertain; do not schedule jobs; use small patches; put uncertainty under `Limitations` or `Needs user decision`; end with the audit report delivered to Telegram.

Setup/maintenance and model-benchmark procedures live in `/home/konstantin/docs/runbooks.md`.

## Audit Report Format

Keep final reports compact:

```text
## Daily knowledge distillation
Mode:
Sources checked:
Docs — Added/Updated/Removed/Skipped:
Fact-store — Added/Updated/Removed/Skipped:
Built-in memory changed:
Needs user decision:
Files changed:
Limitations:
```

If nothing changed, say so and explain why. “No changes” is a valid success.

## Common Pitfalls

1. Appending instead of curating → prefer update/replace/skip.
2. Saving task progress as knowledge → keep durable facts/procedures/decisions only.
3. Duplicating built-in memory → docs/fact_store expand; MEMORY is index+guardrails only, not a fact mirror.
4. Treating absence as obsolescence → do not delete because something was not mentioned today.
5. Storing secrets → redact values; paths to credential files are also risky — prefer "(see config)" over actual paths.
6. Creating long daily reports in docs → reports go to Telegram/output; docs get distilled knowledge.
7. Patching docs per batch → batches produce candidates only; controller performs one serial merge/write/verify.
8. Cron job without pinned model → model defaults to Hermes default, which may not support Russian or json_object. Always pin model explicitly. unpinned = asking for language/format surprises.
9. Russian system prompt + glm-5.1:cloud + json_object → empty content (verified bug). Use English system prompt, Russian data fields.
10. **NEVER use `ollama run` / `ollama pull` for cloud models (`:cloud` suffix).** `ollama run` (CLI) attempts to pull local blob layers for the model, regardless of whether it's a cloud proxy. On a 35 GB disk, this fills the filesystem in minutes — the April 29 incident crashed Hermes gateway (ENOSPC on transcript/session writes). Cloud models (`gemma4:31b-cloud`, `glm-5.1:cloud`, etc.) are remote proxies with zero local blobs; they work exclusively through the Ollama HTTP API (`http://127.0.0.1:11434/v1/chat/completions`). If you need to call a cloud model from `execute_code`, use `aiohttp`/`requests` to the HTTP endpoint — NEVER `ollama run`, `ollama pull`, or any CLI command that triggers blob download. This is a **hard block**, not a warning: a single `ollama run gemma4:31b` costs ~7 GB and can take down the entire Hermes process.
11. `json_schema` strict mode through Ollama Cloud does NOT enforce enum constraints for ANY model. Root cause: cloud models (`:cloud` suffix, 0.0 GB local size) are remote proxies — the GBNF grammar sampler only runs on locally-loaded models. Proof: (a) models produce ` ```json ` codeblocks under json_schema — impossible under real grammar enforcement; (b) float confidence (`0.95`) instead of string enum (`"high"`); (c) custom GBNF grammar via `/api/chat` causes empty output for some models and is ignored by others; (d) `json_schema`, `json_object`, and `none` produce identical output given the same prompt. Use `json_object` + explicit enum values in the system prompt — every tested model complies. See `references/json-schema-benchmark.md` for full root-cause analysis.
11. Thinking models (deepseek-v4-pro, deepseek-v4-flash) → reasoning tokens count toward max_tokens but don't appear in content. If max_tokens too low, content is empty after thinking. Set 3000+ for thinking models as workers.
12. Markdown codeblock wrapping is cosmetic, not structural. Some models return ` ```json{...}``` `, others return raw `{...}`. Both parse through the same fallback parser in ~2 lines. Do not select models based on wrapping behavior.
13. kimi-k2.6 is not viable as a distillation worker: 3.5–7K reasoning tokens on trivial prompts, output truncation, unreliable JSON. Exclude from the pool.
14. Credential paths in docs → even paths are leaked metadata. Store only "(see config)" or section references, not actual file paths.
15. Ad-hoc retrospective ensembles are not the same as cron distillation workers. DeepSeek V4 Pro can be useful for a one-off interaction analysis with a larger token budget and raw JSON artifacts, even though it remains excluded from the scheduled daily worker pool at `max_tokens=3000`. Always state endpoint, model tag, token budget, parse status, and limitations instead of turning one benchmark shape into a universal model rule.
16. Updating this skill does **not** update the already-scheduled cron job prompt. When the daily distillation architecture changes, audit and patch both places: `SKILL.md` and the embedded prompt for job `62e7a25f4e15` in `~/.hermes/cron/jobs.json`/cron metadata. `cronjob list` shows only a preview; inspect the full prompt before concluding the scheduled job matches the skill.
16. Scope vs permission confusion → never equate an API/OAuth scope used by one script with the external-system account's real permissions. Example: Google Calendar digest jobs may intentionally use `https://www.googleapis.com/auth/calendar.readonly` for safe reads, while the service account ACL can still be `writer`. Verify ACL/share role separately before writing “read-only”, “Viewer”, “writer”, or “Make changes required”.
17. “Not tested” is not “not enabled”. If write operations were not attempted, say “write operation not tested in this run”; do not write “write access is disabled” unless a current permission check or failed write proves it.
19. **Facts go to fact_store, not built-in memory.** A claim about the world, configuration, or observation is a fact → `destination=fact_store`. Built-in memory only accepts: index pointers, known-wrong entries, holographic hygiene triggers, and the DO-NOT-EDIT guardrail. If a candidate looks like a durable fact that doesn't fit those four categories, it belongs in fact_store.
20. **fact_store duplicates are easy to create.** Always `fact_store search` or `probe` before `add`. If a similar fact exists, `update` it instead of creating a new entry.
21. **Cron fact_store availability comes from the `memory` toolset.** There is no separate `fact_store` toolset in cron metadata. For scheduled distillation, verify `enabled_toolsets` includes `memory`; then the session gets `fact_store` / `fact_feedback`. When fixing this, update both cron metadata and the embedded prompt/tool guidance, then verify with `cronjob list` plus full `jobs.json` prompt inspection.
22. **Root cause must be reproduced, not narrated.** If a model/cron worker is suspected, run the production-shaped worker path first (same model, endpoint, prompt, response format, token budget, timeout, and input size). Do not answer with broad explanations like “source-of-truth drift” until the actual runtime failure mode is captured. For DeepSeek details, see `references/deepseek-worker-repro-2026-05-01.md`.

## Verification Checklist

- [ ] Declared mode: normal, dry-run, or benchmark.
- [ ] Read docs README and relevant target files before writing.
- [ ] Checked recent sessions or stated limitation.
- [ ] Kept source packet within budget or used candidate-only batching.
- [ ] Parallel workers, if any, were read/extract/review only and did not mutate state.
- [ ] Ran write candidates through the quality gate.
- [ ] Avoided duplicates, low-durability items, raw logs, transcripts, secrets, and token-like values.
- [ ] Updated/replaced instead of blindly appending.
- [ ] Abstracted agent mistakes into durable rules.
- [ ] Updated plan status only with evidence and permitted mode.
- [ ] If built-in memory was changed, it was index/guardrails only (no facts that belong in fact_store), non-duplicative of SOUL/USER, and reported in the audit.
- [ ] Checked fact_store for existing entries before adding facts (search before add).
- [ ] Re-read changed sections and checked duplicates/conflicts.
- [ ] Final report lists mode, sources, added/updated/removed/skipped, files changed, limitations.

## Success Standard

The knowledge base is more trustworthy, not necessarily larger. Future usefulness beats extraction volume.
