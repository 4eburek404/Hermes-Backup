---
name: konstantin-plan-governance
description: Use when creating, updating, closing, archiving, or reviewing durable multi-step plans for Konstantin. Acts as a thin procedural hook to the canonical /home/konstantin/docs/plans/README.md policy; do not duplicate that policy here.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [plans, planning, governance, docs, memory, workflow]
    related_skills: [plan, writing-plans, docs-review]
---

# Konstantin Plan Governance

## Overview

This is a **thin procedural hook** for Konstantin's durable plan workflow. It exists to make the agent load the right local policy before mutating plan state.

Do not treat this skill as the full policy. The canonical source of truth is:

```text
/home/konstantin/docs/plans/README.md
```

Layering model:

- **This skill**: thin trigger, routing, and enforcement hook.
- **`/home/konstantin/docs/plans/README.md`**: full canonical policy.
- **Holographic `fact_store`**: retrieval pointer and durable atomic facts.
- **Built-in memory**: always-on index to the docs system.
- **Builtin `plan` / `writing-plans` skills**: generic plan mechanics and implementation-plan quality standards.

## When to Use

Use this skill when the user asks to:

- create, update, execute from, close, archive, or review a multi-step plan for Konstantin;
- work inside `/home/konstantin/docs/plans/`;
- decide where an AI-agent plan should live;
- clean up plan status, root/archive layout, or plan lifecycle;
- reconcile a plan with docs, skills, holographic memory, or session history.

Also use it before any multi-step task that changes durable Hermes state for Konstantin and therefore needs a written plan: docs, memory, skills, cron, config, credentials metadata, or similar operational control surfaces.

Do not use this skill to override an explicit user/project-local instruction. If the user or repository asks for a different plan path, follow that explicit path and clearly label the scope as project-local rather than Konstantin's durable agent plan ledger.

## Mandatory Workflow

Before mutating plan state:

1. Read the canonical policy:
   ```text
   /home/konstantin/docs/plans/README.md
   ```
2. Check whether a relevant active plan already exists in:
   ```text
   /home/konstantin/docs/plans/
   ```
3. For Konstantin's durable agent plans, default to:
   ```text
   /home/konstantin/docs/plans/YYYY-MM-DD-short-topic.md
   ```
4. Keep the root clean:
   - root contains only `README.md` and active `planned`, `in_progress`, or `blocked` plans;
   - closed plans move to `archive/<year>/<done|cancelled|superseded>/`.
5. Keep plan status machine-readable:
   ```markdown
   ## Status
   Current status: in_progress
   ```
6. Before final response, update verification/status and archive closed plans.
   - Treat archive/move as part of completion, not a cosmetic follow-up. Do not mark a plan `Current status: done` while leaving it in root unless the next immediate operation is moving it to `archive/<year>/done/` and verifying root cleanliness.
   - If tool-call/context limits are near, prioritize mechanical closeout (status, archive move, root verification) over extra narrative.
   - If a newly completed plan supersedes an older active/root plan on the same topic, mark the older plan `Current status: superseded`, add a short pointer to the completed/current plan, and move it to `archive/<year>/superseded/`. Do not leave duplicate active plans in root after the work is done.
7. When the user asks to review active plans for possible completion, do an evidence-backed closeout audit, not a status-only read:
   - inventory root active plans and their `Steps` / `Verification` criteria;
   - check live code/config/skills/tests/session history for each criterion;
   - run available targeted tests or smoke commands when they materially reduce uncertainty;
   - mark completed checkboxes, add a dated audit note, set `Current status: done`, and archive plans that are actually complete;
   - leave partially complete plans active with explicit remaining blockers and evidence.
   For a compact recipe and evidence examples, see `references/active-plan-audit-closeout.md`.
8. Promote durable outcomes to the right layer instead of leaving them only in the plan:
   - `../infrastructure.md` for current system facts;
   - `../runbooks.md` for short repeatable procedures;
   - Hermes skills for executable workflows;
   - holographic `fact_store` for short durable facts / retrieval hooks;
   - `session_search` for raw history and temporary progress.

## Boundary Rules

- Do **not** copy the full canonical policy into this skill. If policy changes, update `/home/konstantin/docs/plans/README.md` first.
- Do **not** edit builtin `plan` or `writing-plans` to encode Konstantin-specific policy; builtin skills may be overwritten by Hermes updates.
- Do **not** leave completed plans in root.
- Do **not** store secrets, raw logs, full transcripts, or token-like values in plans.
- Do **not** treat archived plans as current source of truth without checking current docs/config/tools.
- Do **not** turn a troubleshooting plan into an architecture/product decision by implication. If the plan reveals alternative durable fixes (for example dashboard-only mitigation vs runtime lifecycle change), write them as options or `decision required` and get explicit user direction before implementing the architectural/product choice. Operational cleanup and evidence gathering can proceed when authorized; choosing architecture for Konstantin without surfacing trade-offs is a pitfall.

## Common Pitfalls

0. **Overlong plan reviews.** When Konstantin asks to analyze or review a plan, start with a terse verdict and the practical decision: execute as-is / revise first / block. Keep the main response scannable (usually bullets, not a long essay). Put evidence and trade-offs after the verdict, and avoid turning a plan critique into a broad architecture lecture unless explicitly requested. If the user says the review was too long, update the plan directly and show only what changed.

0a. **Architecture notes/backlog living in `plans/` root.** If a root file in `/home/konstantin/docs/plans/` is useful but not shaped as a plan (missing Goal/Non-goals/Steps/Verification/Status), normalize it into an active plan when the user asks, or propose moving durable knowledge to docs/runbooks/skills. Preserve the user's compact priority list as checkboxes under `## Steps`; add `## Status` with `Current status: planned|in_progress|blocked` immediately on the next line (no blank line), then verify the machine-readable status before replying. For a practical root canonicalization recipe, including required sections, archive handling, and verification skeleton, see `references/plan-canonicalization-cleanup.md`.

0b. **Analysis-only requests are not mutation requests.** If Konstantin asks to analyze, rank, review, or "show conclusions" for a plan, read the plan and relevant skills/docs, then answer with conclusions only. Mutate the plan only when he explicitly says to update/normalize/patch it, or when mutation is part of the approved task.

0c. **Priority ranking should separate cheap guardrails from heavy review gates.** When ranking plan items, distinguish high-frequency/low-cost controls from high-latency escalation patterns. A useful pattern can remain lower priority if it is expensive or should be conditional. For an example of evaluating P0/P1/P2/P3 and splitting a P1 item into "cheap observability first" vs "full verification only for high-stakes", see `references/searcharvester-pattern-prioritization.md`.

0d. **Plan review with internet/source freshness.** When Konstantin asks to "подними план, анализируй, ищи в интернете, при необходимости предложи обновления", treat it as analysis-first: read the plan + policy, check local/session context, verify upstream/current internet state if the plan depends on an external project, and propose exact plan updates. Do not mutate until he says to update. If he later approves, apply the patch, fix naming-policy drift if present, and verify required sections plus machine-readable status. For the reusable recipe, see `references/external-source-plan-review.md`.

1. **Falling back to `.hermes/plans/` mechanically.** For Konstantin's durable agent plans, use `/home/konstantin/docs/plans/` unless explicitly told otherwise.
2. **Duplicating the README in this skill.** That creates two policies and future drift. This skill should stay small.
3. **Overriding project-local conventions.** If the user is working inside a repository with its own requested plan location, use the requested project path and label the scope.
4. **Leaving status in prose only.** The first status line must remain machine-readable: `Current status: ...`.
5. **Treating a completed plan as memory.** Plans are control surface and audit trail. Durable knowledge belongs in docs, skills, or holographic memory.
6. **Turning investigation plans into architecture decisions.** A plan may record hypotheses and candidate fixes, but do not start product/architecture changes just because they are listed as possible mitigations. If the task is root-cause investigation and several architecture options exist (dashboard-only mitigation vs runtime lifecycle change vs operational runbook), present the trade-offs and get user direction before committing/deploying the chosen approach unless the user explicitly told you to execute it.

## Verification Checklist

- [ ] Canonical `/home/konstantin/docs/plans/README.md` was read before plan mutation.
- [ ] New/active plans are in `/home/konstantin/docs/plans/`, unless an explicit project-local path was requested.
- [ ] Root contains only `README.md` plus active `planned|in_progress|blocked` plans.
- [ ] Closed plans are archived under `archive/<year>/<status>/`.
- [ ] Superseded duplicate/root plans on the same topic were marked `Current status: superseded`, linked to the replacing plan, and archived under `archive/<year>/superseded/`.
- [ ] For active-plan completion audits, each plan was reconciled against live evidence/tests or left active with explicit blockers.
- [ ] Plan contains `Goal`, `Non-goals`, `Steps`, `Verification`, and machine-readable `Current status:`.
- [ ] Durable outcomes were promoted to the correct layer or explicitly marked as not needed.
- [ ] No secrets or raw logs were introduced.
