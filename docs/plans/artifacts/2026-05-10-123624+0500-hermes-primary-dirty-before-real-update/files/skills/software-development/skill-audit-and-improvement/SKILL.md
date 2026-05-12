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

**Core principle:** a skill is not a diary entry. It is an executable behavior source. If a future agent cannot load it, follow it, verify it, and avoid the same mistake, the skill update is incomplete.

This workflow is intentionally stricter than ordinary documentation review because Hermes skills affect future agent behavior. A good skill has clear triggers, exact actions, explicit safety boundaries, deterministic verification, and a compact final report.

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

Stable audit protocol rule: do **not** add JSON reports or CLI contracts to every skill by default. Keep the shared machine contract in this skill's `audit_skill.py`, future `schemas/`, CI/baseline gates, and `references/audit-protocol-contract.md`. Add JSON/CLI contracts to individual skills only when there is a real machine consumer, repeated executable logic, live checks, redaction, CI integration, or a mature tool contract.

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
5. After changing `scripts/audit_skill.py`, run AST syntax, invalid-repo smoke, affected-skill audit, and changed-file scan.
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

- missing triggers;
- stale paths;
- ungrounded claims;
- duplicated rules;
- missing verification;
- oversized body;
- security/secret issues;
- CLI need or CLI risk.

### 4. Write minimal durable changes

- Small text issue → `patch`.
- Major rewrite/new file → `write_file`.
- Long case-specific details → `references/<topic>.md`.
- Reusable output form → `templates/<name>.md`.
- Deterministic audit → `scripts/<name>.py`.

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
- **Verified:** commands and pass/fail.
- **Remaining:** baseline issues or follow-ups.
- **Rollback:** exact command or file path.

## References

- `references/audit-protocol-contract.md` — stable audit protocol contract, session lessons (provenance, dirty worktree, audit script hardening, master plan synthesis, systemd skill improvement case study), and design rationale.

## Common Pitfalls

1. **Creating a new skill when a patch is enough.** Audit the library shape first; avoid narrow one-session skills.
2. **Trusting memory over live repo state.** Always verify branch, HEAD, status, and target diff.
3. **Writing to runtime skill state as source.** In Konstantin's setup, source is `~/.hermes/hermes-agent/skills/`.
4. **Leaving important skill changes dirty.** Backup stores refs, not dirty development files.
5. **Letting tool-call/iteration limits blur the state.** If a session ends before commit/push or verification, report the exact last verified state, dirty files, completed checks, and remaining commands. Do not say “done”, “pushed”, or “ready” unless that final action was actually executed and verified.
6. **Forgetting prompt-cache boundaries.** New or edited skills may require a fresh session or `/reset` before they are loaded automatically.
7. **Overloading `SKILL.md`.** Long evidence, command cookbooks, and incident notes belong in `references/`.
8. **Letting verification create generated artifacts.** Skill-owned CLI tests, compile checks, and smoke runs can create `__pycache__/` and `.pyc` files that the audit helper later reports as `GENERATED_ARTIFACT` blockers. Prefer `PYTHONDONTWRITEBYTECODE=1` plus `ast.parse` syntax checks, or remove generated caches before the final `audit_skill.py` run.
9. **Putting scanner-trigger literals directly into test fixtures.** Tests often need stale paths or secret-shaped strings to verify redaction, but literal obsolete source paths or token-assignment examples can become `STALE_PATH`/`SECRET_LIKE_VALUE` blockers in `audit_skill.py`. Preserve the regression by constructing those fixture strings from safe fragments, and keep assertions against the constructed variable so the output still proves no raw value leaked.
10. **Skipping independent review for your own script/CLI.** Self-review misses edge cases.
11. **Turning an audit CLI into a mutator.** Default read-only; mutations require explicit flags and user permission.
12. **Reporting all-repo baseline issues as regressions.** Separate existing baseline problems from issues introduced by your diff.
13. **Assuming dirty means the current task is unfinished.** After a scoped commit or push, re-check live Git status and map each dirty path to active plans, recent commits, and changed-skill audit findings. Dirty files may be older plan leftovers, completed-but-unarchived documentation, or unrelated work. Do not stage, revert, or summarize them as part of the just-finished task until that provenance is verified.
14. **Committing secrets in examples.** Use env var names and `[REDACTED]`, never real tokens/passwords.
15. **Putting project architecture into USER.md.** JSON/CLI audit-contract rules are skills architecture, not user profile. Before writing `USER.md`, `MEMORY.md`, or `SOUL.md`, show the proposed diff and decide the correct layer. In this case, the canonical layer is `skill-audit-and-improvement` plus `references/audit-protocol-contract.md`, with only a compact `fact_store` pointer if retrieval needs it.
16. **Over-standardizing every skill.** Machine-auditable does not mean every skill needs its own JSON schema or CLI. Centralize shared audit output in `audit_skill.py`; add per-skill JSON/CLI only for real machine consumers and repeated executable workflows.
17. **Producing phase lists without benefits when synthesizing plans.** When the user asks to decompose/analyze/synthesize a skill-audit roadmap, include the practical profit for each phase and save the durable master plan under `/home/konstantin/docs/plans/` with machine-readable status.
18. **Redacting only the first token after a sensitive key.** YAML/frontmatter parser errors can echo the rest of a malformed line; redact the whole sensitive assignment segment, and also redact generic multi-token `Bearer ...` segments even when the YAML key is not in the sensitive-key allowlist. Include both sensitive-key and generic-bearer regression tests.
19. **Assuming two-level skill paths in `--changed`.** Deleted `SKILL.md` files must map to `deleted_path.parent`, including nested layouts such as `skills/mlops/training/<skill>/SKILL.md`.
20. **Treating pre-CI local readiness as CI work.** Keep local gates, fixtures, schema, resolver, `--changed`, and baseline compare separate from GitHub Actions/CODEOWNERS/branch protection unless explicitly requested.
21. **Fixing one structural warning can reveal the next one.** `MISSING_SECTION` findings are emitted per required heading; after adding `## Overview`, re-run the audit before declaring the section work done, because the next missing required heading (for example `## When to Use`) may become the remaining actionable warning. When proposing structural fixes, check the full required-section set (`Overview`, `When to Use`, `Common Pitfalls`, `Verification Checklist`) and present the complete minimal patch set instead of only the first visible warning.

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
- [ ] Independent review done for major changes.
- [ ] Commit/push state reported precisely.
- [ ] If a tool-call/iteration limit or other interruption occurred, final response separates completed actions from remaining commands and avoids overclaiming.
