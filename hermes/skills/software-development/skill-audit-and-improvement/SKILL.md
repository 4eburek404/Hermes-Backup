---
name: skill-audit-and-improvement
description: "Use when auditing, improving, or creating Hermes skills and skill-owned CLIs after a task, before committing skill changes, or when the user asks for skill-library cleanup. Provides provenance checks, quality rubric, improvement decision tree, validation gates, and a compact report format."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [skills, audit, improvement, verification, hermes-agent, skill-library]
    related_skills: [hermes-agent, hermes-agent-skill-authoring, requesting-code-review, knowledge-architecture]
---

# Skill Audit and Improvement

## Overview

This skill turns ad-hoc skill editing into a reproducible audit workflow. Use it to decide whether to patch an existing skill, add references/templates/scripts, create a new skill, add a read-only owning CLI, or leave a finding as a non-blocking recommendation.

**Acceptance test:** a future agent can load the skill, identify when to use it, run exact checks/commands, avoid the documented pitfall, and verify the result. If not, patch the skill with operational steps; do not add philosophy, manifestos, or session narrative.

**Contract test:** for every high-impact skill, the main behavior must be encoded as a **golden path** plus a **verifiable contract**. Do not rely on requests, preferences, or prose such as “prefer X” when a wrong path can still be reached through a helper, bridge, fallback command, environment variable, cron script, or alternate CLI. Convert the rule into concrete invariants and checks: accepted entrypoints, blocked anti-paths, required evidence before mutation, read-back proof after mutation, and fail-closed behavior for bypass surfaces.

This workflow is intentionally stricter than ordinary documentation review because Hermes skills affect future agent behavior. A good skill has clear triggers, exact actions, explicit safety boundaries, deterministic verification, a named golden path, contract tests for fragile decisions, and a compact final report.

## When to Use

Use this skill when:

- The user says “audit this skill”, “improve this skill”, “revise the skill library”, “create a skill from this session”, or similar.
- A session produced reusable workflow knowledge, tool-use lessons, source/runtime conventions, validation sequences, or repeated corrections.
- You changed `skills/**/SKILL.md`, `skills/**/references/*`, `skills/**/templates/*`, `skills/**/scripts/*`, or a skill-owned `cli/`.
- You need to decide whether a skill needs an owning CLI, a reference file, a template, a script, or just a small patch.
- You are about to report that a skill is “done” or “ready”.

Do **not** use this skill for:

- General code review unrelated to skills; use `requesting-code-review`.
- Debugging a runtime bug before root cause is known; use `systematic-debugging` first.
- Flight search or business travel workflows; use `flight-search`.
- Editing protected context files (`MEMORY.md`, `USER.md`, `SOUL.md`) without explicit user-approved diff.

## Required Companion Skills

Load these when relevant:

- `hermes-agent` — required for Hermes source/runtime layout, config, gateway, and prompt-cache behavior.
- `hermes-agent-skill-authoring` — required for frontmatter, placement, size, and in-repo conventions.
- `requesting-code-review` — required before committing changes with code, scripts, or CLIs.
- `knowledge-architecture` — required when skill changes interact with docs, plans, memory hygiene, or canonical knowledge layout.

Conflict rule for skill-library changes: if a companion review workflow suggests `git diff | grep` secret scans, this skill wins. Use `audit_skill.py --changed --json` or another metadata-only redacting scanner instead, because grep-based scans can print secret values into transcripts.

Stable audit protocol rule: do **not** add JSON reports or CLI contracts to every skill by default. Keep the shared machine contract in this skill's `audit_skill.py`, `schemas/`, CI/baseline gates, and `references/audit-protocol-contract.md`. Step 2C audits schema files and decides whether a schema contract is required/recommended/optional/not applicable, but remains advisory: it does not validate CLI command output against per-skill schemas, does not enforce schema compliance, and does not require JSON Schema for skills without a machine-readable contract surface.

Golden-path contract rule: every skill that can materially steer tools, mutate state, touch credentials/config/external systems, or prevent a recurring user-corrected mistake must state one preferred golden path and the contract that proves it. The contract may be prose-backed for judgment-only skills, but it must still name observable invariants. For executable workflows, prefer deterministic script checks or CLI smoke tests that fail if the wrong path remains reachable.

## Provenance Gate

Before reading conclusions into the skill library, verify the live source layer. Do not rely on memory alone.

```bash
cd /home/konstantin/.hermes/hermes-agent
git branch --show-current
git rev-parse --short=12 HEAD
git status --short --branch --untracked-files=all
```

Then inspect the target path:

```bash
git diff -- skills/<category>/<skill>/
git diff --cached -- skills/<category>/<skill>/
```

Interpretation:

- Clean target path → safe to make a scoped edit.
- Dirty target path → read the diff first; preserve or integrate intentionally.
- Dirty unrelated path → do not overwrite it; mention it if it affects reproducibility.
- Runtime state in `~/.hermes/skills` → do not treat as source in Konstantin's setup.
- If the active `~/.hermes/hermes-agent` symlink resolves to a non-git release directory, do not force git commands or claim source provenance. Verify the release target with `readlink -f`, then decide whether the task is runtime-only (`skill_manage`/read-back) or needs a separate source-checkout/release pipeline.
- If the approved task uses `skill_manage` against runtime skill state and no writable git source is active, verify by read-back: target path, bytes, SHA-256, required substrings, frontmatter, required sections. Report that no commit/push was performed.
- When `audit_skill.py` requires a git repo but the only changed skill state is runtime, create a temporary git worktree for validation: copy a known bundled/baseline skill tree into `/tmp`, `git init` + commit the baseline, overlay the runtime `SKILL.md` or support file, then run `git diff --check`, `audit_skill.py --repo <tmp> --skill <name> --json`, and `audit_skill.py --repo <tmp> --changed --json`. Treat this as validation evidence only, not source provenance.
- Important uncommitted skill changes → not reproducible from GitHub/backup until committed and pushed.

## Audit Inputs

Collect evidence before proposing improvements:

1. `SKILL.md` frontmatter and body.
2. Supporting files under `references/`, `templates/`, `scripts/`, `assets/`.
3. Existing owning `cli/` directory, if any.
4. Related peer skills in the same category.
5. Relevant loaded skills and session lessons.
6. Git diff, branch, HEAD, and status.
7. Upstream comparison only if asked whether a skill is local/custom; fetch and compare by frontmatter `name`.

Useful helper:

```bash
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --skill <skill-name> --json
```

## Quality Rubric

Score the skill on these dimensions. A weak score does not always block a patch, but it should drive the improvement plan.

### 1. Trigger clarity

Good:

- Description starts with “Use when …”.
- `## When to Use` names concrete user phrases, task classes, and counter-triggers.
- The skill says when **not** to use it.

Bad:

- Generic “helps with X”.
- No boundary from neighboring skills.
- Skill only describes one past incident.

### 2. Executability

Good:

- Contains exact commands, paths, checks, and expected outputs.
- Uses deterministic tools before interpretation.
- Has a decision tree for common forks.

Bad:

- High-level advice without commands.
- “Check the repo” without branch/HEAD/status.
- “Verify” without saying how.

### 3. Source/runtime correctness

Good:

- Uses `/home/konstantin/.hermes/hermes-agent/skills/` as the source tree in this setup.
- Treats `~/.hermes/skills` as runtime state, not source.
- Does not recreate stale paths such as `/home/konstantin/code/clis` or `local/skill-clis`.
- Notes prompt-cache/fresh-session boundaries when skill availability changes.

Bad:

- Writes new source skills to runtime state only.
- Claims backup captured dirty dev state.
- Mentions stale CLI layouts without marking them stale.

### 4. Safety and side effects

Good:

- Read-only audit before mutation.
- Explicit permission for external side effects, config, cron, credentials, protected context files, or production systems.
- CLIs default read-only; mutating modes require explicit `--apply`/`--yes`.
- Secrets are placeholders or `[REDACTED]`.

Bad:

- `systemctl restart`, `git reset`, credential edits, or external writes hidden inside a “verification” step.
- Secret-looking example values.
- Commands that mutate without a dry-run path.

### 5. Verification discipline

Good:

- Frontmatter validation.
- Link/reference existence checks.
- Stale-path and secret scans.
- CLI compile/tests/doctor for skill-owned CLIs.
- Independent review for major rewrites or scripts.
- Final report states what was checked and what remains.

Bad:

- “Looks good” based only on reading.
- Tests run from the wrong path.
- All-repo failures reported as new without baseline separation.

### 6. Library architecture

Good:

- Patches existing umbrella skills before creating narrow duplicates.
- Session-specific evidence goes into `references/`.
- Reusable templates go into `templates/`.
- Deterministic probes go into `scripts/`.
- A new class-level umbrella is created only when no existing skill governs the behavior.

Bad:

- One new skill per conversation.
- Multiple skills owning the same rule with inconsistent wording.
- Large `SKILL.md` that should be split into references.

### 7. Behavior delta and mistake prevention

Use `references/skill-quality-model-v2.md` when the audit question is semantic or the user says a skill is superficial. Static quality is not enough: name what the future agent will do differently, which concrete mistake is prevented, and what scenario replay or live evidence would prove it.

Good:

- Maps user triggers, task classes, decision points, evidence cues, side effects, fallback paths, and completion proof before editing.
- Distinguishes functional quality (well-formed and safe), operational quality (better decisions under task pressure), and deep quality (reduces steering and closes recurring feedback loops).
- Uses progressive disclosure: compact main skill, long reasoning/cases in `references/`, reusable worksheets in `templates/`, deterministic checks in `scripts/`.
- Tests at least one realistic scenario for high-impact or user-corrected skills.

Bad:

- Says “audit passed” only because frontmatter/paths/secrets are clean.
- Adds broad philosophy to `SKILL.md` without a behavior change.
- Treats semantic judgment as a fake machine score.

### 8. Golden path and contract enforcement

Use this dimension whenever a skill owns tool selection, state mutation, external systems, credentials/config, safety boundaries, or a user-corrected recurring mistake.

Good:

- The skill names the **golden path**: the first/default route a competent agent should take.
- It names **anti-paths**: plausible but wrong routes that must not be tried first or must be fail-closed.
- It enumerates every executable surface that could bypass the golden path: scripts, CLIs, bridges, wrappers, cron jobs, fallback commands, environment-variable overrides, direct API helpers, and documented examples.
- The rule is backed by a **contract basis**: invariants, exact commands, expected pass/fail outputs, read-back requirements, and negative tests for blocked paths.
- The verification fails if the prose says “use A” but any executable path still silently allows “B”.

Bad:

- “Prefer A” or “do not use B” is only prose and B still works through another helper.
- Only the main CLI is tested while bridges/wrappers/fallback scripts remain unguarded.
- The final report says “audit passed” without naming the golden path, anti-paths, bypass surfaces, and contract evidence.

## Improvement Decision Tree

Default stance: be active. A post-session pass that finds no update is possible, but it is an exception that needs evidence: no user correction, no reusable workflow, no missing/outdated loaded skill, and no transferable technique. If any one signal fired, make at least one small durable skill-library improvement.

Use this order:

1. **Patch an existing loaded skill** if the lesson corrects or extends it. Loaded/consulted skills are the first target because they governed the work in this session.
2. **Patch an existing class-level umbrella skill** if the lesson belongs to a broader workflow. Keep the library shaped around reusable task classes, not one-session artifacts.
3. **Add a support file** when the detail is long, evidence-heavy, session-specific, or a compact knowledge bank. Use `references/` for case detail/domain notes, `templates/` for copy-and-modify starters, and `scripts/` for deterministic probes.
4. **Add a pointer from `SKILL.md`** to any new support file so future agents know it exists.
5. **Add a read-only owning CLI** when the workflow needs live state collection, multiple commands, structured JSON, or deterministic redaction/safety enforcement.
6. **Create a new class-level umbrella skill** only when no existing skill owns the task class. The name must not be a PR number, error string, feature codename, library-alone name, or today's session artifact.

When in doubt, prefer a small patch plus reference over a new narrow skill. If the user explicitly asks for a new skill, still check for overlap and report it. User style/workflow corrections belong in the governing skill body, not only in memory, because skills define how to do that class of task next time.

## Self-Audit Loop

When this skill is itself the target, run a bounded self-audit instead of improvising or recursing forever:

1. Load this skill, its linked files, and the companion skills listed above.
2. Run the provenance gate and the helper against `skill-audit-and-improvement` before editing.
3. Identify one concrete reusable improvement. Prefer improving a deterministic check, conflict rule, validation gate, or reporting template over adding self-referential prose.
4. Apply at most one recursive improvement cycle per user request unless the user explicitly asks for another pass.
5. After changing `scripts/audit_skill.py`, `schemas/audit-report.schema.json`, or stable report-contract fields, run AST syntax, invalid-repo smoke, affected-skill audit, changed-file scan, and `scripts/validate_audit_report.py` against the emitted JSON reports.
6. Run an independent blocker-only review for script changes or safety-rule changes.
7. Report whether the self-audit ended cleanly, and do not claim commit/push until verified.

A self-audit should make the workflow more reliable for future skills. It should not add broad philosophy, session history, or rules that belong in `SOUL.md`, memory, or docs.

## Owning CLI Decision Rules

A skill should get an owning CLI when at least three are true:

- The audit repeatedly gathers the same live facts.
- Multiple shell commands need normalization into one JSON output.
- The workflow has objective pass/fail checks.
- Secret redaction or URL/credential safety needs deterministic enforcement.
- The task is too error-prone for manual copy-paste.
- The CLI can be read-only by default.

Do not add a CLI when:

- The workflow is mostly judgment or writing.
- The task needs one simple command.
- Safe behavior requires project-specific credentials or mutating production state.
- A script under `scripts/` is enough.

## Standard Audit Workflow

### 1. Classify the request

Label it as one or more:

- `post-session learning`
- `existing skill audit`
- `new skill authoring`
- `skill-owned CLI audit`
- `source/runtime cleanup`
- `distribution/custom inventory`

### 2. Gather source evidence

```bash
cd /home/konstantin/.hermes/hermes-agent
git status --short --branch --untracked-files=all
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json
```

For custom-vs-upstream inventory, use the helper in the `hermes-agent` skill:

```bash
python3 skills/autonomous-ai-agents/hermes-agent/scripts/inventory-custom-skills.py --repo /home/konstantin/.hermes/hermes-agent
```

### 3. Read before writing

Read the target `SKILL.md`, support files, and 1-3 peer skills. Identify:

- golden path: the single default route a future agent should take for the core task;
- anti-paths: plausible but wrong routes to block, demote, or require explicit fallback;
- executable surfaces: support scripts, owning CLIs, bridges, wrappers, cron-owned scripts, env-var shortcuts, direct API helpers, and examples that could bypass the skill text;
- missing triggers;
- stale paths;
- ungrounded claims;
- duplicated rules;
- missing verification;
- oversized body;
- security/secret issues;
- CLI need or CLI risk.

For semantic/deep-quality audits, also apply `references/skill-quality-model-v2.md` or fill `templates/deep-skill-audit.md` before patching. Identify the behavior before/after, the mistake prevented, the golden-path contract, and at least one simple/edge/failure/dangerous scenario that should change future agent behavior.

### 4. Write minimal durable changes

- Small text issue → `patch`.
- Missing golden path → add an explicit “Golden Path” or first-move section that says which route is default and which routes are fallback/unsupported.
- Wrong route still executable → change the relevant script/CLI/wrapper to fail closed by default, then add a contract check proving the anti-path is blocked.
- Major rewrite/new file → `write_file`.
- Long case-specific details → `references/<topic>.md`.
- Reusable output form → `templates/<name>.md`.
- Deterministic audit → `scripts/<name>.py`.
- Style corrections → convert into concrete checks, commands, pitfalls, or report requirements; avoid philosophical prose.

### 5. Validate

Minimum validation for any skill edit:

```bash
git diff --check
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json
```

For changed Python scripts/CLIs, use an AST syntax check that does not create `__pycache__` inside the repo:

```bash
python3 - <<'PY'
from pathlib import Path
import ast
path = Path('<script.py>')
ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('syntax_ok')
PY
```

For owning CLIs, disable bytecode/cache creation so audit runs do not introduce generated artifacts under the skill tree:

```bash
cd skills/<category>/<skill>/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m <module> --json doctor
```

For changes to `audit_skill.py`, `schemas/audit-report.schema.json`, or the stable report contract, validate that emitted JSON still matches the schema:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json > /tmp/audit_skill_report.json
PYTHONDONTWRITEBYTECODE=1 python3 skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py /tmp/audit_skill_report.json
```

For skills with a golden path, anti-path, or fail-closed rule, add or run contract checks that prove the behavior from every executable surface. The minimum contract is:

- positive path: the golden path command/helper is documented and smoke-tested where safe;
- negative path: each anti-path returns a recognizable failure status/message before touching credentials, APIs, or external state;
- bypass coverage: bridges, wrappers, fallback commands, cron-owned helpers, and env-var shortcuts are included;
- read-back: mutations have duplicate/search/read-back proof, not only a successful exit code.

Example shape:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/<category>/<skill>/scripts/validate_contract.py --json
PYTHONDONTWRITEBYTECODE=1 python3 skills/<category>/<skill>/scripts/validate_contract.py --live --json  # only when live access is in scope
```

For broad skill-library changes:

```bash
python3 - <<'PY'
from pathlib import Path
import re, sys
errors=[]
for path in Path('skills').glob('**/SKILL.md'):
    text=path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        errors.append((str(path),'missing frontmatter start'))
    if len(text)>100000:
        errors.append((str(path),'too large'))
    if not re.search(r'\n---\s*\n', text[3:]):
        errors.append((str(path),'missing frontmatter end'))
print({'skill_count': len(list(Path('skills').glob('**/SKILL.md'))), 'errors': errors})
sys.exit(1 if errors else 0)
PY
```

### 6. Review independently

For major rewrites, scripts, or CLIs, run an independent review with only the diff and static scan results. Fail closed on security or logic issues.

### 7. Commit and push when in scope

```bash
git add skills/<category>/<skill>/
git commit -m "feat: add <skill-name> skill"
git push
```

If push is not in scope, report the exact branch, commit status, and remaining dirty state.

## Stale Path and Secret Scan

Run this before committing skill-library changes:

```bash
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill <skill-name> --json
```

Scan changed, staged, and untracked files without printing secret values:

```bash
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --changed --json
```

Any true secret value must be removed or replaced with `[REDACTED]`. A placeholder such as `TOKEN_ENV` is acceptable when clearly documented as an environment variable name.

The changed-file scan also fails on newly introduced single-line or simple multiline grep-based secret scan commands such as `git diff | grep token`, because those commands can print the matched secret value. Use the helper's metadata-only findings instead of copying raw matching lines into the transcript.

## Report Format

Use the template at `templates/audit-report.md`. Keep Telegram summaries compact:

- **Changed:** files/skills.
- **Why:** concrete cause/lesson.
- **Golden path:** default route now encoded.
- **Contract basis:** positive checks, negative anti-path checks, bypass surfaces, read-back proof.
- **Verified:** commands and pass/fail.
- **Remaining:** baseline issues or follow-ups.
- **Rollback:** exact command or file path.

For deep audits, add behavior-delta fields from the template: behavior before/after, mistake prevented, evidence source, scenario replay result, remaining uncertainty, and next check.

## References

- `references/audit-protocol-contract.md` — stable audit protocol contract, session lessons (provenance, dirty worktree, audit script hardening, master plan synthesis, systemd skill improvement case study), and design rationale.
- `references/static-cli-schema-inventory-step1.md` — case note for static-only CLI/schema inventory enforcement: report fields, non-execution boundary, old-report compatibility guardrail, and validation pattern.
- `references/advisory-cli-execution-step2a.md` — case note for advisory safe executable CLI checks: high-confidence-only execution, mutation blocking, evidence redaction, and validation pattern.
- `references/doctor-envelope-step2b.md` — case note for advisory doctor JSON envelope validation, evidence normalization, redaction regressions, and acceptance sweep pattern.
- `references/audit-protocol-contract.md` — includes Step 2C advisory schema-file audit and schema-decision gate: parse/inspect discovered schemas, classify contract need, warn on missing/invalid/unreferenced schemas, and defer per-skill output validation/enforcement to future phases.
- `references/schema-decision-noise-check-step2c5a.md` — case note for read-only Step 2C schema-decision noise checks: temporary repo copies, static-only report validation, required-vs-recommended calibration evidence, and no-CLI negative controls.
- `references/schema-output-mapping-step2d-a0.md` — case note for static Step 2D schema-output mapping detection: high-confidence docs/tests/code/report-contract patterns, absent-schema handling, and no runtime output validation.
- `references/schema-output-mapping-diagnostic-step2d-a1b2.md` — read-only diagnostic pattern for separating acceptance-summary extraction artifacts from report-shape regressions, and for catching schema-output false positives such as `agent_report.v1` being linked to a final-answer builder.
- `references/schema-output-mapping-step2d-a1b-2f.md` — case note for the detector fix that requires exact schema identity for `code_explicit`, ranks docs CLI-output evidence above consumer-code candidates, and preserves user-answer final-answer mappings.
- `references/deep-skill-audit-method.md` — semantic skill-quality method: behavior delta, mistake prevention, cognitive task analysis, progressive disclosure, scenario replay, and feedback-loop closure.
- `references/skill-quality-model-v2.md` — functional/operational/deep quality model, cognitive task analysis workflow, progressive disclosure rules, degree-of-freedom rule, gap analysis, scenario replay, and feedback-loop closure.
- `references/deep-audit-scenarios.md` — compact scenario corpus for replaying recurring skill-audit failure modes.
- `templates/audit-report.md` — human-facing report template; must stay aligned with `## Report Format` and contract fields.
- `templates/deep-skill-audit.md` — worksheet for scenario-based semantic skill audits.
- `scripts/audit_skill.py` — read-only machine audit report generator.
- `scripts/validate_audit_report.py` and `schemas/audit-report.schema.json` — schema validation for `audit_skill.py --json` outputs.
- `schemas/cli-doctor-envelope.v1.schema.json` — central advisory Step 2B doctor JSON envelope contract; not per-skill schema enforcement.

## Common Pitfalls

1. **Creating a new skill when a patch is enough.** Audit the library shape first; avoid narrow one-session skills.
2. **Trusting memory over live repo state.** Always verify branch, HEAD, status, and target diff.
3. **Writing to runtime skill state as source.** In Konstantin's setup, source is `~/.hermes/hermes-agent/skills/`.
4. **Leaving important skill changes dirty.** Backup stores refs, not dirty development files.
5. **Letting tool-call/iteration limits blur the state.** If a session ends before commit/push or verification, report the exact last verified state, dirty files, completed checks, and remaining commands. Do not say “done”, “pushed”, or “ready” unless that final action was actually executed and verified.
6. **Forgetting prompt-cache boundaries.** New or edited skills may require a fresh session or `/reset` before they are loaded automatically.
7. **Overloading `SKILL.md`.** Long evidence, command cookbooks, and incident notes belong in `references/`.
8. **Letting verification create generated artifacts.** Skill-owned CLI tests, compile checks, and smoke runs can create `__pycache__/` and `.pyc` files that the audit helper later reports as `GENERATED_ARTIFACT` blockers. Prefer `PYTHONDONTWRITEBYTECODE=1` plus `ast.parse` syntax checks, or remove generated caches before the final `audit_skill.py` run.
9. **Using overbroad generated-artifact cleanup patterns.** Cleanup sweeps should target actual generated locations and suffixes (`__pycache__/`, `*.pyc`, temp/acceptance output dirs), not every filename containing words like `report`. Legitimate source files such as `schemas/audit-report.schema.json` and `templates/audit-report.md` are contract/template sources, not generated artifacts. When a broad scan flags a source contract file, narrow the predicate before deleting or reporting cleanup failure.
10. **Putting scanner-trigger literals directly into test fixtures.** Tests often need stale paths or secret-shaped strings to verify redaction, but literal obsolete source paths or token-assignment examples can become `STALE_PATH`/`SECRET_LIKE_VALUE` blockers in `audit_skill.py`. Preserve the regression by constructing those fixture strings from safe fragments, and keep assertions against the constructed variable so the output still proves no raw value leaked.
11. **Letting generic schema words, vendored files, or consumer builders become detector evidence.** Static schema-output mapping heuristics must not treat generic basename tokens such as `json`, `schema`, `contract`, `doctor`, `report`, or `output` as explicit evidence. If a schema named `output.v1.schema.json` is present, a generic sentence like “the tool emits output” must not create a high-confidence mapping; add a regression with the generic basename, not only a harmless `example.v1.schema.json` fixture. Static detectors must also ignore generated and vendored directories (`__pycache__/`, build caches, `node_modules/`, `vendor/`, virtualenvs); third-party fixtures under a skill must not create mappings or contract findings for owned behavior. When a builder consumes an object named like another schema surface, do not infer ownership of that consumed schema: for example, `build_user_answer_contract(agent_report)` is evidence for `flight_search_user_answer.v1`, not for `agent_report.v1`. Before calling a mapping regression, inspect the actual report path (`$.cli.exists`, `$.checks.schema_contract.schema_output_mappings[]`) rather than only an acceptance summary; summary nulls can be extraction artifacts.
12. **Skipping independent review for your own script/CLI.** Self-review misses edge cases. If blocker-only review finds a blocker and you patch it, do not report PASS until the fix is wired into the production path and the blocker reproduction plus the full relevant suite have been rerun after the patch. A helper function added but not connected is still an open blocker.
13. **Letting advisory execution broaden beyond the stated confidence boundary.** If a roadmap says executable checks are limited to high-confidence entrypoints, do not let medium-confidence inventory hints leak into subprocess execution. Static inventory may record weaker candidates, but the runner must filter to the explicit executable confidence tier and have a regression test proving lower tiers are not executed.
14. **Testing only the primary entrypoint while leaving bypass surfaces open.** When a skill encodes an anti-path or fail-closed rule, enumerate every executable path that can reach that behavior: helper scripts, CLIs, bridges, wrappers, environment-variable shortcuts, cron-owned scripts, and documented fallback commands. Add contract checks for each bypass surface, not only the main CLI. Example pattern: if `setup.py` and `google_api.py` block a wrong OAuth path, also test any `gws_bridge.py` or direct wrapper that could still invoke it.
15. **Serializing raw command argv or output previews in evidence.** Command evidence is output too: redact secret-bearing argv tokens, next-token secret values, CLI flag forms (`--api-key VALUE`, `--token=VALUE`), and stdout/stderr preview lines before storing or printing them. Keep raw-output hashes for provenance, but bound previews and add regression tests for token/password/api-key/authorization examples so safety evidence cannot leak the very data it is supposed to protect.
16. **Treating doctor `ok=false` as schema invalid.** In Step 2B the baseline doctor envelope validates shape only. `ok=false` is a doctor result signal: record it and warn when paired with issues/error, but do not make it a schema violation or blocker by itself.
17. **Confusing baseline doctor envelope validation with per-skill schema enforcement.** `schemas/cli-doctor-envelope.v1.schema.json` is only a central advisory envelope contract. Step 2C may audit schema files and decide that a schema is required or recommended, but missing/invalid/unreferenced schemas are still advisory warnings. Do not validate per-skill CLI command outputs against discovered schemas, enforce JSON Schema contracts, add `--strict`, or add `--enforce-cli` until a later roadmap step explicitly asks for it.
18. **Turning an audit CLI into a mutator.** Default read-only; mutations require explicit flags and user permission.
19. **Reporting all-repo baseline issues as regressions.** Separate existing baseline problems from issues introduced by your diff.
20. **Assuming dirty means the current task is unfinished.** After a scoped commit or push, re-check live Git status and map each dirty path to active plans, recent commits, and changed-skill audit findings. Dirty files may be older plan leftovers, completed-but-unarchived documentation, or unrelated work. Do not stage, revert, or summarize them as part of the just-finished task until that provenance is verified.
21. **Committing secrets in examples.** Use env var names and `[REDACTED]`, never real tokens/passwords.
22. **Putting project architecture into USER.md.** JSON/CLI audit-contract rules are skills architecture, not user profile. Before writing `USER.md`, `MEMORY.md`, or `SOUL.md`, show the proposed diff and decide the correct layer. In this case, the canonical layer is `skill-audit-and-improvement` plus `references/audit-protocol-contract.md`, with only a compact `fact_store` pointer if retrieval needs it.
23. **Over-standardizing every skill.** Machine-auditable does not mean every skill needs its own JSON schema or CLI. Centralize shared audit output in `audit_skill.py`; add per-skill JSON/CLI only for real machine consumers and repeated executable workflows.
24. **Producing phase lists without benefits when synthesizing plans.** When the user asks to decompose/analyze/synthesize a skill-audit roadmap, include the practical profit for each phase and save the durable master plan under `/home/konstantin/docs/plans/` with machine-readable status.
25. **Redacting only the first token after a sensitive key.** YAML/frontmatter parser errors can echo the rest of a malformed line; redact the whole sensitive assignment segment, and also redact generic multi-token `Bearer ...` segments even when the YAML key is not in the sensitive-key allowlist. Include both sensitive-key and generic-bearer regression tests.
26. **Assuming two-level skill paths in `--changed`.** Deleted `SKILL.md` files must map to `deleted_path.parent`, including nested layouts such as `skills/mlops/training/<skill>/SKILL.md`.
27. **Treating pre-CI local readiness as CI work.** Keep local gates, fixtures, schema, resolver, `--changed`, and baseline compare separate from GitHub Actions/CODEOWNERS/branch protection unless explicitly requested.
28. **Fixing one structural warning can reveal the next one.** `MISSING_SECTION` findings are emitted per required heading; after adding `## Overview`, re-run the audit before declaring the section work done, because the next missing required heading (for example `## When to Use`) may become the remaining actionable warning. When proposing structural fixes, check the full required-section set (`Overview`, `When to Use`, `Common Pitfalls`, `Verification Checklist`) and present the complete minimal patch set instead of only the first visible warning.
29. **Treating template placeholders as broken support links.** Backticked examples such as `references/<topic>.md`, `templates/<name>.md`, and `scripts/<name>.py` describe allowed target shapes; they are not real support files and should not be reported as broken links. Support-link checks must distinguish concrete paths from placeholder patterns containing `<...>` before escalating a finding.
30. **Leaving non-blocker review feedback unincorporated when it cheaply removes ambiguity.** If an independent review returns PASS but flags a wording ambiguity, path ambiguity, or checklist phrasing that could confuse future agents, apply a small clarity patch and rerun the minimal read-back/static validation before the final report. Do not over-escalate it as a blocker, but do close cheap ambiguity while the context is hot.
31. **Ignoring loaded peer-skill findings discovered during a target-skill audit.** If validation of one skill exposes a concrete wrong command, stale section, or structural warning in a loaded related skill, patch the related skill too when the fix is small and class-level. Example: a Google Workspace audit that proves Himalaya account selection uses subcommand-level `-a` should update `himalaya`, not only the Google skill.
32. **Replacing enforceable contracts with requests or preferences.** “Prefer the good path” is not enough when the wrong path remains executable. For high-impact skills, write the golden path, list anti-paths, identify every bypass surface, and add contract checks that fail if a bypass still works.
33. **Claiming a golden path without a proof surface.** A golden path is operational only if a future agent can verify it: positive smoke/read-back for the right route, negative tests for the wrong routes, and clear fallback/override conditions.
34. **Updating report requirements without updating the report template.** If `## Report Format` requires a field such as golden path, contract basis, anti-paths, or bypass coverage, `templates/audit-report.md` must contain the same field. A blocker-only review should fail when the prose requires evidence that the official template still lets agents omit.

35. **Changing the audit JSON contract without schema validation.** When `audit_skill.py`, `schemas/audit-report.schema.json`, or report-contract fields change, run `validate_audit_report.py` against emitted `--json` outputs. A syntactically valid JSON report is not enough if it drifts from the schema future CI/reviewers rely on.

36. **Answering skill-capability questions from prose only.** When the user asks whether this audit skill analyzes a feature such as a skill-owned CLI or JSON Schema contract, do not stop at “yes, the skill says so.” Distinguish three layers: (1) normative procedure in `SKILL.md`/references, (2) actual machine enforcement in `audit_skill.py`, schemas, tests, and support files, and (3) manual deep-audit steps still required. Use live read-back/search of the relevant files and, when useful, authoritative docs/web/Context7 evidence before answering. Report gaps explicitly, for example: “the workflow requires CLI contract audit, but the script currently only collects CLI metadata and static checks; doctor/tests/schema validation remain separate evidence.”

37. **Breaking old audit reports while adding new contract fields.** When extending `audit_skill.py`, `validate_audit_report.py`, or `schemas/audit-report.schema.json`, add an old-report compatibility fixture before finalizing. New CLI/schema sections should be optional/additive in the current `schema_version`; do not make previously valid finding fields newly required. See `references/static-cli-schema-inventory-step1.md` for the Step 1 static inventory case.

## Verification Checklist

- [ ] Correct companion skills loaded.
- [ ] Branch, HEAD, status, and target diff checked.
- [ ] Existing overlap checked before creating a new skill.
- [ ] `SKILL.md` frontmatter validates: name, description, size, body.
- [ ] Trigger, non-trigger, workflow, pitfalls, and verification sections exist.
- [ ] Supporting files are under allowed dirs: `references/`, `templates/`, `scripts/`, `assets/`.
- [ ] Related skills exist in the repo or are explicitly justified.
- [ ] Stale path scan completed.
- [ ] Secret scan completed.
- [ ] Unsafe grep-based secret-scan recommendations checked.
- [ ] Scripts/CLIs compile or tests run where applicable, without leaving generated artifacts (`PYTHONDONTWRITEBYTECODE=1`, `ast.parse`, or post-test cleanup).
- [ ] Anti-path/fail-closed claims have contract tests for every executable bypass surface, including bridges/wrappers/fallback commands and env-var override paths.
- [ ] `audit_skill.py --json` outputs validate with `scripts/validate_audit_report.py` when audit report contract/schema/script fields changed.
- [ ] Report-format prose and `templates/audit-report.md` contain the same required golden-path, contract-basis, anti-path, bypass, and read-back fields.
- [ ] Verification discipline includes static checks plus scenario replay where the audit made semantic behavior claims.
- [ ] Independent review done for major changes.
- [ ] Any blocker found by independent review was fixed in the actual execution path and revalidated with a blocker reproduction plus the relevant full suite before reporting PASS.
- [ ] Non-blocker independent-review ambiguity was either patched and revalidated, or explicitly left as a justified non-change.
- [ ] Commit/push state reported precisely.
- [ ] If a tool-call/iteration limit or other interruption occurred, final response separates completed actions from remaining commands and avoids overclaiming.
