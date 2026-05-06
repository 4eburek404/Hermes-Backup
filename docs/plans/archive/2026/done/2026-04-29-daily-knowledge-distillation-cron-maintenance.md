# Daily Knowledge Distillation Cron Maintenance Plan

> **For Hermes:** Use this plan to audit, patch, and verify the daily knowledge-distillation cron job. Do not change cron/skills/docs beyond the steps explicitly listed here.

**Status:** done ✓

**Goal:** Bring the daily knowledge-distillation cron job to the current target architecture: OpenAI Codex gpt-5.5 as the cron job model, cron entrypoint, orchestrator, and curator; Ollama Cloud worker ensemble for extraction; gpt-oss:120b-cloud only as fallback; then verify end-to-end.

**Architecture:** The cron entrypoint remains a lightweight orchestrator. It gathers recent sessions, runs worker extraction via `distillation_worker.py`, merges/deduplicates/votes candidates, then hands the curated candidate packet to a high-quality curator. The curator applies the quality gate and patches `/home/konstantin/docs/` conservatively.

**Tech Stack:** Hermes cron jobs, `daily-knowledge-distillation` skill, Ollama Cloud OpenAI-compatible API, `execute_code`, `delegate_task`, `/home/konstantin/docs/`.

---

## Current known state

- Cron job: `62e7a25f4e15`
- Name: `Ежедневная дистилляция знаний`
- Schedule: `0 18 * * *` = 21:00 UTC+5 for Konstantin
- Delivery: `origin` — Telegram DM
- Cron job model / entry / orchestrator / curator: `OpenAI Codex gpt-5.5`
- Toolsets: `session_search`, `file`, `terminal`, `web`
- Skill: `daily-knowledge-distillation`
- Worker pool target:
  - `glm-5.1:cloud`
  - `deepseek-v4-pro:cloud`
  - `gemma4:31b-cloud`
- Curator target: `OpenAI Codex gpt-5.5`
- Fallback curator: `gpt-oss:120b-cloud`
- Resolved issue: cron prompt previously described `gpt-oss:120b-cloud` as primary curator and `glm-5.1:cloud` as cron entry/orchestrator; this plan now targets OpenAI Codex gpt-5.5 for cron entry/orchestrator/curator.
- Required timeout target: `200s` for all worker models.

---

## Phase 1 — Audit-only

### Task 1.1: Inspect cron job configuration

**Objective:** Establish the exact current state of job `62e7a25f4e15` before changing anything.

**Files / Systems:**
- Read: Hermes cron job metadata for `62e7a25f4e15`
- Do not modify anything.

**Steps:**
1. Run `cronjob list`.
2. Locate job `62e7a25f4e15`.
3. Record:
   - model/provider;
   - schedule;
   - delivery target;
   - enabled toolsets;
   - attached skills;
   - last/next run;
   - prompt preview.
4. If possible, retrieve full prompt via `cronjob update/list` mechanisms without modifying it.

**Verification:**
- Produce a table: expected vs actual.
- Confirm no side effects were made.

---

### Task 1.2: Inspect skill content

**Objective:** Find stale curator instructions and other mismatches in the skill.

**Files:**
- Read: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/SKILL.md`
- Read: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/scripts/distillation_worker.py`
- Read: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/references/json-schema-benchmark.md`

**Steps:**
1. Search for `gpt-oss`, `gpt-5.5`, `insufficient_quota`, `missing_scope`.
2. Search for `timeout`, `deepseek`, `json_schema`, `json_object`.
3. Identify each outdated statement and classify:
   - must patch now;
   - acceptable historical note;
   - should remove to avoid future confusion.

**Verification:**
- Produce a patch checklist with exact target sections.

---

### Task 1.3: Verify model-name consistency

**Objective:** Avoid mixing runtime dialogue model, cron entry model, worker models, and curator model.

**Expected model roles:**

```text
Dialogue/runtime model: current session-dependent; not the cron design source of truth.
Cron job model / entry / orchestrator: OpenAI Codex gpt-5.5.
Worker models: glm-5.1:cloud, deepseek-v4-pro:cloud, gemma4:31b-cloud.
Curator model: OpenAI Codex gpt-5.5.
Fallback curator: gpt-oss:120b-cloud.
```

**Verification:**
- Every file/prompt must use the same role mapping.
- `gpt-oss:120b-cloud` must not be described as the primary curator unless gpt-5.5 is unavailable.

---

## Phase 2 — Patch

### Task 2.1: Patch `SKILL.md` curator section

**Objective:** Replace stale curator guidance.

**File:**
- Modify: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/SKILL.md`

**Required change:**
- Cron job model / entry / orchestrator / primary curator: `OpenAI Codex gpt-5.5`
- Fallback curator: `gpt-oss:120b-cloud`
- Remove or rewrite current-state claims that say `gpt-5.5` is unavailable.

**Example target wording:**

```text
Curator / orchestrator model (tier 0/2 — cron entry + final decisions + write):
- Cron job model / entry / orchestrator / primary curator: OpenAI Codex gpt-5.5.
- Fallback: gpt-oss:120b-cloud if gpt-5.5 is unavailable.
```

**Verification:**
1. Search `SKILL.md` for `gpt-oss`, `gpt-5.5`, `insufficient_quota`, `missing_scope`.
2. Confirm stale availability claims are not presented as current facts.

---

### Task 2.2: Patch cron prompt

**Objective:** Ensure job `62e7a25f4e15` actually instructs the runtime to use the current architecture.

**System:**
- Modify: cron job `62e7a25f4e15`

**Required prompt content:**

```text
Cron job model / entry / orchestrator: OpenAI Codex gpt-5.5.
Worker extraction models: glm-5.1:cloud, deepseek-v4-pro:cloud, gemma4:31b-cloud.
Curator: OpenAI Codex gpt-5.5.
Fallback curator: gpt-oss:120b-cloud only if gpt-5.5 is unavailable.
Do not recursively create or schedule cron jobs.
```

**Verification:**
1. Run `cronjob list` after update.
2. Confirm model/provider remains pinned.
3. Confirm toolsets remain `session_search`, `file`, `terminal`, `web`.
4. Confirm schedule and delivery were not accidentally changed.

---

### Task 2.3: Patch worker timeout if audit confirms it

**Objective:** Improve reliability of the 3-worker vote, especially for `deepseek-v4-pro`.

**File:**
- Modify: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/scripts/distillation_worker.py`

**Required design:** 200 seconds for every worker.

**Target behavior:**

```text
glm-5.1:cloud        200s
gemma4:31b-cloud     200s
deepseek-v4-pro:cloud 200s
```

**Fallback behavior:** failed/timeout worker is skipped; the run continues with returned workers.

**Verification:**
- Run worker extraction on a small sample.
- Confirm timeout is logged per worker.
- Confirm one failed worker does not fail the entire extraction phase.

---

### Task 2.4: Clean conflicting durable facts if needed

**Objective:** Prevent stale model availability facts from reappearing.

**Systems:**
- Holographic memory / fact_store
- Built-in memory only if absolutely necessary

**Steps:**
1. Search facts for `gpt-5.5`, `gpt-oss`, `distillation`, `curator`.
2. Update existing facts instead of adding duplicates.
3. Remove facts that say `gpt-5.5` is currently unavailable if they are no longer true.
4. Avoid adding to built-in memory unless the fact must be always visible.

**Verification:**
- `gpt-5.5` appears as primary curator.
- `gpt-oss:120b-cloud` appears only as fallback.

---

## Phase 3 — Dry run without docs writes

### Task 3.1: Run worker extraction only

**Objective:** Verify workers, parser, merge/dedup/voting without touching docs.

**Mode:** dry-run, no docs writes, no memory writes, no cron changes.

**Expected report:**

```text
workers:
- glm: ok/failed
- deepseek-v4-pro: ok/timeout/failed
- gemma: ok/failed

candidates_before_dedup: N
candidates_after_dedup: M
high_confidence: K
low_confidence: L
```

**Verification:**
- JSON parses through fallback parser.
- `json_object` is used, not `json_schema`.
- Low-durability + low-confidence candidates are auto-skipped.

---

### Task 3.2: Dry-run curator handoff

**Objective:** Verify that gpt-5.5 can act as curator on merged candidates.

**Mode:** dry-run only.

**Curator should return:**
- accepted candidates;
- rejected candidates;
- candidates needing user decision;
- proposed target files;
- no actual docs writes.

**Verification:**
- OpenAI Codex gpt-5.5 is used as cron job model, entrypoint, orchestrator, and primary curator.
- `gpt-oss:120b-cloud` is not used unless gpt-5.5 fails.

---

## Phase 4 — Controlled end-to-end test

### Task 4.1: Run cron job manually

**Objective:** Verify the actual scheduled job works end-to-end.

**System:**
- Run: cron job `62e7a25f4e15`

**Expected behavior:**
- Sessions are collected.
- Worker candidates are generated.
- Curator applies quality gate.
- Docs are patched only if high-value changes exist.
- Audit report is delivered to Telegram.

**Verification:**
- Job status becomes `ok`.
- Report is compact and in Russian.
- If no durable updates exist, “no changes” is accepted as success.

---

### Task 4.2: Verify side effects

**Objective:** Ensure the run improved docs without polluting them.

**Check changed files for:**
- no raw logs;
- no transcripts;
- no credential values;
- no credential file paths unless already intentionally documented;
- no duplicate preference bullets;
- no stale curator claims;
- no task-progress diary entries.

**Verification:**
- Re-read changed sections.
- Search for duplicates/conflicts.
- If an edit is bad, revert or patch immediately.

---

## Phase 5 — Final report

### Task 5.1: Produce final maintenance report

**Format:**

```text
## Cron job distillation maintenance
Mode:
Cron job:
Changed:
Verified:
Skipped:
Risks:
Next decisions:
```

**Required contents:**
- whether skill changed;
- whether cron prompt changed;
- whether worker timeout changed;
- dry-run result;
- end-to-end result;
- remaining risks.

---

## Acceptance criteria

Implementation is successful when:

1. `cronjob list` shows `62e7a25f4e15` active/scheduled.
2. `SKILL.md` and cron prompt state that OpenAI Codex gpt-5.5 is the cron job model, entrypoint, orchestrator, and curator.
3. Cron prompt clearly states:
   - cron job model / entry / orchestrator / curator: `OpenAI Codex gpt-5.5`;
   - workers: `glm-5.1:cloud`, `deepseek-v4-pro:cloud`, `gemma4:31b-cloud`;
   - fallback: `gpt-oss:120b-cloud`.
4. Worker script uses `json_object + explicit enums + strip_codeblock`, not `json_schema` strict mode.
5. Worker timeout is 200s for all workers.
6. Manual job run completes with status `ok`.
7. Telegram report is compact, Russian, and actionable.
8. Docs are not polluted with raw logs, task progress, secrets, or duplicates.

---

## Execution result

Completed on 2026-04-29.

Evidence:
- Cron metadata for `62e7a25f4e15` shows enabled job with model `gpt-5.5`, provider `openai-codex`, schedule `0 18 * * *`, and skill `daily-knowledge-distillation`.
- Embedded prompt contains the target architecture markers: `gpt-5.5`, `glm-5.1:cloud`, `deepseek-v4-pro:cloud`, `gemma4:31b-cloud`, `json_object`, `calendar.readonly`, and `200s` timeout guidance.
- `distillation_worker.py` config uses `timeout: 200` for all three workers and `response_format: {"type": "json_object"}`.
- Scheduled run verified the worker ensemble end-to-end: `glm`, `deepseek-v4-pro`, and `gemma4` all returned parseable candidates; curator rejected duplicates already covered by docs and avoided reintroducing the stale Calendar read-only/Viewer claim.

## Notes

- A successful distillation run may make no docs changes.
- The goal is a more trustworthy knowledge base, not a larger one.
- If a future model switch changes curator availability again, update skill + cron prompt together.
