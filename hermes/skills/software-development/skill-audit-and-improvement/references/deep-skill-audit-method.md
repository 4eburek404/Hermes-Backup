# Deep skill audit method

Use this reference when a skill audit needs to answer whether the skill changes future agent behavior in real tasks, not merely whether `SKILL.md` is well-formed.

## Trigger

Load this when:

- the user says a skill audit feels superficial;
- the task asks for skill-library quality, roadmap, or semantic improvement;
- a skill passes structural checks but may still fail to prevent the user's recurring mistake;
- external research, expert workflow mapping, or scenario replay is needed before editing.

## Grounded sources and concepts

- Anthropic skill guidance: keep skills concise, use progressive disclosure, metadata-driven discovery, and test with realistic usage.
- Diátaxis: distinguish functional quality (accurate, complete, useful, consistent) from deeper fit to user needs and workflow.
- Cognitive Task Analysis: map expert task goals, decision points, cues, strategies, and failure modes before writing procedure.
- Runbook/checklist practice: a checklist should be usable under pressure and validated through simulation.
- Skills gap analysis: compare current capability with target capability, then choose specific improvements.
- After-action review: convert lessons observed into lessons learned by checking that the updated workflow prevents recurrence.

## Audit questions

1. **Behavior delta:** what will a future agent do differently after loading this skill?
2. **Mistake prevented:** which concrete recurring error, unsafe shortcut, or user correction does this skill prevent?
3. **Task model:** what are the real user triggers, task classes, decision points, evidence requirements, side effects, and fallback paths?
4. **Progressive disclosure:** does `SKILL.md` contain the short operational path while bulky evidence, examples, and research live in `references/`?
5. **Degree of freedom:** does the skill allow judgment where tasks vary, and constrain exact steps where mistakes are costly?
6. **Scenario replay:** can the skill handle at least one simple case, one edge case, one failure case, and one dangerous-side-effect case?
7. **Verification:** what live/tool evidence proves the skill works better than before?
8. **Feedback loop:** is the original session/user correction traceable to a reusable rule, pitfall, template, script, or reference?

## Recommended improvement pattern

1. Keep `SKILL.md` compact: triggers, workflow, pitfalls, verification, and pointers.
2. Put session-specific evidence and research into `references/`.
3. Add templates only for outputs a future agent should copy and modify.
4. Add scripts only for deterministic checks; avoid fake semantic scoring.
5. Patch loaded/current umbrella skills before creating new narrow skills.
6. Report the change as: changed files, behavior delta, mistake prevented, verification, remaining uncertainty.

## Scenario corpus starter

Use or adapt these cases during audit:

- “The audit is too superficial”: require behavior-delta and scenario replay, not only frontmatter/path checks.
- Memory cleanup with user override: execute explicit ID/action scope; do not re-litigate earlier recommendations.
- Oversized skill shrink: move long case detail to `references/`, leave operational pointers in `SKILL.md`.
- Skill-owned CLI test creates `__pycache__`: use `PYTHONDONTWRITEBYTECODE=1` or AST checks and clean generated artifacts.
- Runtime skill differs from source: verify source/runtime layer before claiming a skill is current.
- Secret-policy docs false positive: verify yes/no/redacted; do not print matched secret-like lines or weaken policy.

## Non-goals

- Do not require every skill to have JSON, a CLI, or a scenario corpus.
- Do not introduce LLM-judge gates as deterministic pass/fail without explicit benchmark evidence.
- Do not turn a specific session into a one-off skill; keep the class-level umbrella shape.
