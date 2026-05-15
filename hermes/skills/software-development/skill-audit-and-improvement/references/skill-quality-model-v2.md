# Skill quality model v2

Use this reference when a skill audit must go deeper than static structure and answer whether the skill will improve future agent behavior in real work.

## Quality layers

### 1. Functional quality

The skill is structurally usable and safe.

Check that it has:

- discoverable trigger language in frontmatter and `## When to Use`;
- correct paths, commands, tool names, and companion skills;
- explicit safety boundaries, approvals, non-goals, and side effects;
- verification steps with expected evidence;
- valid support files under `references/`, `templates/`, `scripts/`, or `assets/`;
- no stale runtime/source claims, generated artifacts, raw transcripts, or secret values.

Functional quality answers: **can a careful agent follow this without breaking the environment?**

### 2. Operational quality

The skill changes what the agent does under realistic task pressure.

Check that it encodes:

- decision points and branch criteria;
- evidence required before action;
- fallback paths when tools fail or evidence is incomplete;
- stop conditions and escalation/clarification points;
- rollback or recovery path for mutations;
- concise final-report requirements.

Operational quality answers: **will a future agent make better decisions because this skill was loaded?**

A high-impact operational skill must also expose a **golden-path contract**: the default route, the blocked anti-paths, the executable surfaces that could bypass the default, and checks that prove both the positive and negative behavior. If the skill only asks the agent to prefer the right path while the wrong path remains executable, operational quality is not met.

### 3. Deep quality

The skill fits the human/agent workflow, reduces steering, and prevents recurrence of known mistakes.

Check that it:

- anticipates likely user intent and recurring corrections;
- avoids overloading the main prompt with case detail better stored in references;
- gives the agent enough freedom for judgment tasks and enough constraint for fragile operations;
- makes the desired behavior delta falsifiable through scenario replay;
- closes the feedback loop from lesson observed to lesson learned.

Deep quality answers: **what specific future mistake will this skill prevent, and how will we know?**

## Cognitive task analysis workflow

For each audited skill, map the task before editing the text:

1. **User triggers.** List concrete phrases and situations that should load the skill.
2. **Task classes.** Group the real work into 2-5 classes, not one-off sessions.
3. **Expert goal.** State what a competent human/operator would optimize for.
4. **Decision points.** Identify choices that materially change the tool calls, mutation scope, or final answer.
5. **Evidence cues.** Name the files, commands, docs, API state, or user approvals needed before each decision.
6. **Dangerous side effects.** Mark operations that need explicit approval or should default to read-only.
7. **Novice-agent mistakes.** List the likely wrong shortcuts: guessing current state, editing the wrong layer, printing sensitive output, over-creating skills, skipping verification.
8. **Fallback paths.** Define what to do when a tool, source tree, API, or credential is unavailable.
9. **Completion proof.** Define the smallest evidence that proves the task is done.
10. **Layer target.** Decide what belongs in `SKILL.md`, `references/`, `templates/`, `scripts/`, docs, fact_store, memory, or no durable layer.

## Progressive disclosure rules

- Metadata and description should route the agent to the skill.
- `SKILL.md` should contain the operational path: triggers, commands, decision tree, pitfalls, verification, and pointers.
- `references/` should hold theory, case detail, research, long examples, and scenario corpora.
- `templates/` should hold copy-and-modify reports or worksheets.
- `scripts/` should hold deterministic probes, redaction, normalization, or objective pass/fail checks.

If `SKILL.md` grows because it is carrying research notes, incident history, or scenario matrices, move that material into a reference and leave a short pointer.

## Degree-of-freedom rule

Use the right amount of constraint:

- **Exact commands** for fragile operations: git state, deployments, migrations, credentials metadata, cron/config changes, protected context, and secret-safe scans.
- **Decision heuristics** for judgment tasks: what to inspect, how to classify, when to ask, how to prioritize.
- **Templates** for recurring report shapes and scenario walkthroughs.
- **Scripts** where repeatability, redaction, path normalization, or machine-readable JSON matters.
- **No machine scoring** for semantic quality unless a benchmark and failure model exist.

## Gap analysis

Compare current capability with required capability:

- Required behavior: `<what future agent must do>`
- Current skill support: `<where it is already encoded>`
- Gap: `<missing trigger / evidence / decision / fallback / verification / layer>`
- Risk if unfixed: `<mistake or harm>`
- Minimal improvement: `<patch/reference/template/script/no-change>`
- Verification: `<static gate + scenario replay evidence + contract checks for positive/golden path and negative/anti-path bypasses>`

Prefer the smallest change that closes the real behavior gap. Do not create a new artifact because the plan named one if an existing reference already covers it; update the existing reference and explain the consolidation.

## Scenario replay standard

A deep audit should test at least these cases when the skill is high-impact or user-corrected:

1. **Simple path:** the ordinary user request.
2. **Edge path:** ambiguous, cross-layer, or source/runtime split.
3. **Failure path:** a prerequisite tool/source/API is missing or returns partial evidence.
4. **Dangerous-side-effect path:** mutation, external system, protected context, secrets, deployment, cron, or credential metadata.

For each scenario, record:

- expected skill activation and companion skills;
- expected evidence gathering;
- what the agent should ask vs default;
- mutation boundary;
- verification evidence;
- final report fields;
- whether the current skill passes, needs patch, needs support file, needs script, or should remain unchanged.

## Feedback-loop closure

A lesson is closed only when:

1. The original observed mistake or user correction is named.
2. The skill/reference/template/script change is mapped to that mistake.
3. A scenario replay shows the updated workflow would have changed the agent's behavior.
4. The final report states remaining uncertainty and the next check.

If the lesson is too session-specific, keep it in session history or a plan note. If it is reusable but long, place it in a reference. If it is an atomic retrieval hook, store it in fact_store. If it changes how to do the task, patch the governing skill.
