# Daily Distillation Prompt Hardening Plan

> **For Hermes:** Improve the scheduled daily knowledge distillation prompt after observing the first end-to-end runs and user correction.

**Status:** done ✓

**Goal:** Make the daily distillation prompt less error-prone: prevent inferred facts from being written as verified facts, especially the `calendar.readonly` scope vs Calendar ACL permission mix-up.

**Architecture:** Audit recent cron outputs, embedded cron prompt, skill instructions, worker prompt/script, and session summaries. Patch the skill and scheduled cron prompt with explicit evidence/verification gates and domain-specific disambiguation rules. Verify by searching for stale language and inspecting the final prompt.

**Tech Stack:** Hermes cron, `daily-knowledge-distillation` skill, `/home/konstantin/docs/`, `session_search`, Python Google Calendar API evidence, targeted markdown patches.

---

## Task 1: Collect evidence from the failed inference

**Objective:** Identify exactly where the distillation process inferred `read-only` incorrectly.

**Files / sources:**
- Read: `/home/konstantin/.hermes/cron/output/62e7a25f4e15/2026-04-29_08-40-32.md`
- Read: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/SKILL.md`
- Read: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/scripts/distillation_worker.py`
- Inspect: cron job `62e7a25f4e15` full embedded prompt
- Search: recent sessions about Calendar service account, calendar digest, events, permissions, `calendar.readonly`, `writer`

**Verification:** Evidence distinguishes:
- API scope used by a script/job;
- actual Calendar ACL/share permission;
- user-created events vs agent-created events;
- old session summaries vs freshly verified tool/API results.

## Task 2: Define prompt hardening rules

**Objective:** Convert the incident into general rules, not a one-off apology.

**Rules to add:**
1. Do not infer external-system permission from a read operation or read-only scope.
2. For Google Calendar, distinguish `calendar.readonly` OAuth/API scope from Calendar ACL roles (`reader`, `writer`, `owner`).
3. If docs/session summaries conflict with current tool/API checks, current verified tool/API result wins.
4. When writing/removing operational facts, include evidence class: `verified_tool_result`, `session_summary`, `model_inference`, `user_correction`.
5. Any candidate involving credentials, permissions, ACLs, OAuth scopes, schedules, model pinning, or write capabilities needs a verification step or must be reported as `Needs user decision`, not written as fact.
6. Report uncertainty explicitly; do not collapse “not tested” into “not enabled”.

## Task 3: Patch skill prompt

**Objective:** Add evidence separation, ambiguity gates, and Google Calendar scope-vs-permission pitfall to `daily-knowledge-distillation` skill.

**File:** `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/SKILL.md`

**Verification:** Search shows explicit rules for:
- scope vs permission;
- `not tested` vs `not enabled`;
- verified API/tool result precedence;
- permission/ACL write gate.

## Task 4: Patch scheduled cron embedded prompt

**Objective:** Ensure the already-scheduled job uses the hardened rules; changing the skill alone is insufficient.

**Target:** Cron job `62e7a25f4e15` embedded prompt via `cronjob update`.

**Verification:** `cronjob list`/jobs metadata confirms prompt contains the new hardening block and still uses:
- provider `openai-codex`
- model `gpt-5.5`
- workers: `glm-5.1:cloud`, `deepseek-v4-pro:cloud`, `gemma4:31b-cloud`
- timeout `200s`
- JSON mode `json_object + enums + strip_codeblock()`.

## Task 5: Final audit report

**Objective:** Report concrete findings, patched files, remaining limitations, and next recommended test.

**Verification:** No stale `read-only (Viewer role)` / `Viewer/read-only` language remains in docs or prompt unless quoted as a known bad example.

## Execution result

Completed on 2026-04-29.

Findings:
- The bad `read-only` conclusion came from stale session summaries and worker candidates that conflated `calendar.readonly` scope with Calendar ACL/share permission.
- The previous prompt had model/timeout/JSON rules, but no explicit evidence gate for permissions, ACLs, scopes, write capability, model pinning, or stale-session conflicts.
- Worker dedup/voting produced low-confidence candidates; final curator must not treat worker candidates as facts without a verification pass.

Changes applied:
- Patched `daily-knowledge-distillation/SKILL.md` with an operational-fact verification gate, evidence ladder, and scope-vs-permission pitfalls.
- Patched `distillation_worker.py` worker prompt and evidence enums: added `verified_tool_result`, `session_summary`, and `model_inference`; instructed workers to mark ambiguous operational claims as skip.
- Patched cron job `62e7a25f4e15` embedded prompt with a mandatory “Evidence and ambiguity hardening” block and Google Calendar-specific `scope ≠ permission` rule.
- Verified `distillation_worker.py` compiles.
- Verified docs no longer contain stale `Viewer/read-only`/`read-only (Viewer role)` claims except this plan's own known-bad example wording.
