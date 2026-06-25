# Skill Quality Model

## Purpose

This model is for semantic skill audits: not just “is the markdown valid?”, but “will loading this skill make a future agent choose the right actions, avoid known mistakes, and verify completion?”

## Quality layers

1. **Functional quality** — frontmatter parses, required sections exist, links point to real support files, scripts compile, and templates are usable.
2. **Operational quality** — the skill gives a clear default path, stop conditions, verification gates, and layer routing for `SKILL.md` vs support files.
3. **Deep quality** — the skill changes behavior in difficult scenarios: ambiguity, stale context, failures, bypass paths, protected state, and user-corrected mistakes.

A good audit names which layer is being evaluated. Do not demand deep-audit machinery for every small typo, and do not accept syntactic validity as proof of behavioral quality.

## Core concepts

- **Behavior delta:** what a future agent will do differently after the change.
- **Mistake prevented:** the concrete recurring failure, unsafe shortcut, or user correction encoded by the skill.
- **Golden path:** the default route the skill should make easiest and first.
- **Anti-path:** a tempting but wrong route the skill must block or force into explicit fallback.
- **Progressive disclosure:** keep always-needed actions in `SKILL.md`; move long rubrics, cases, and history to references/templates/scripts.
- **Degree-of-freedom rule:** constrain decisions that caused errors; leave harmless style choices unconstrained.

## Deep audit questions

Ask these when the task is high-impact, user-corrected, safety-sensitive, or about recurring agent behavior:

1. What future prompt should trigger this skill?
2. What exact mistake should become less likely?
3. What evidence must be gathered before action?
4. What is the golden path and why is it first?
5. What anti-paths or bypass surfaces must fail closed?
6. What context belongs in `SKILL.md` and what belongs in a support file?
7. What command, test, read-back, or scenario proves the behavior?
8. What should the final report say so the user can verify the result?

## Scenario replay standard

Use four scenario classes for semantic review:

| Scenario | Purpose | Evidence |
|---|---|---|
| Simple path | Confirms the normal trigger and default action. | Prompt, expected files/tools, success proof. |
| Edge path | Checks ambiguity, source/runtime split, or competing skills. | Decision point, chosen fallback, why. |
| Failure path | Exercises missing tools, partial evidence, or invalid inputs. | Error handling and honest uncertainty. |
| Dangerous side effect | Protects credentials, providers, cron, services, production, or external writes. | Approval boundary and read-back proof. |

One replay can cover several findings. Avoid one-test-per-sentence bloat.

## Cognitive walkthrough

For complex skills, describe:

1. Expert goal.
2. Evidence the agent should gather before acting.
3. Decision points and alternatives.
4. Novice-agent mistakes.
5. Stop conditions.
6. Completion proof.

Patch the smallest layer that changes the weak decision point. If the agent already has the needed behavior, report “no durable change” rather than adding sediment.

## Layering guidance

- `SKILL.md`: compact operational runbook, trigger, stop conditions, verification checklist.
- `references/`: methodology, calibration examples, long scenario matrices, durable lessons.
- `templates/`: copy-and-fill worksheets or final report forms.
- `scripts/`: deterministic checks, redaction, schema validation, inventory.
- `schemas/`: stable machine-readable contracts.

## Non-goals

- Do not require every skill to own a CLI, schema, JSON output, or scenario corpus.
- Do not invent fake LLM scoring or subjective numeric grades.
- Do not create one-off skills for session-specific facts.
- Do not keep adding rules without removing the old wording they replace.

## Completion checklist

- [ ] Behavior delta is named or no-change is justified.
- [ ] Golden path and at least one relevant anti-path were considered.
- [ ] Long context was routed out of `SKILL.md`.
- [ ] Verification evidence matches the claimed behavior.
- [ ] The final report separates verified facts from remaining uncertainty.
