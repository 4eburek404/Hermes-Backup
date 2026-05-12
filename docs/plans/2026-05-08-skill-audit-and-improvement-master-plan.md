# Plan: skill-audit-and-improvement master plan

## Goal

Довести `skill-audit-and-improvement` до зрелого состояния: не просто `audit_skill.py` как structural checker, а deterministic, read-only quality gate для Hermes skills с машинным JSON-контрактом, baseline/no-regression политикой, CI required check и review/branch-protection контуром.

Ключевой результат: деградация skills блокируется репозиторием/CI, а не зависит от того, вспомнил ли агент правило.

## Context

Проверенная live-база на момент создания плана: `2026-05-08 04:45 +05`.

Target repo:

```bash
/home/konstantin/.hermes/hermes-agent
```

Target skill:

```bash
skills/software-development/skill-audit-and-improvement/
```

Observed branch / HEAD:

```text
fix/ollama-native-auxiliary-routing
7e93bf155c2e
```

Observed current state:

- repo dirty: 9 changed/untracked files;
- target skill dirty:
  - modified `skills/software-development/skill-audit-and-improvement/SKILL.md`;
  - untracked `skills/software-development/skill-audit-and-improvement/references/audit-protocol-contract.md`;
- generated artifact exists:
  - `skills/software-development/skill-audit-and-improvement/scripts/__pycache__/audit_skill.cpython-311.pyc`;
- current `audit_skill.py` has 487 lines and flags:
  - `--repo`;
  - `--skill`;
  - `--all`;
  - `--changed`;
  - `--json`;
- missing today:
  - `--path`;
  - `--output`;
  - stable schema validation;
  - baseline/no-regression compare;
  - CI quality gate;
  - affected-skill grouping in `--changed`;
  - stable `repo` / `target` / `findings` / `checks` / `evidence_manifest` JSON contract;
  - normalized input-error exit code `2`.

Related existing plans / sources:

```text
/home/konstantin/docs/plans/2026-05-07-audit-skill-quality-gate-v2.md
/home/konstantin/docs/plans/2026-05-07-skill-audit-stable-json-contract-and-degradation-gate.md
/home/konstantin/docs/plans/2026-05-07-skill-audit-and-improvement-skill.md
```

This master plan is the synthesized execution map. It does not archive or close the existing companion plans by itself; that requires an explicit lifecycle decision.

## Architecture decision

Use one stable audit protocol owned by `skill-audit-and-improvement` and implemented through `scripts/audit_skill.py`.

Do **not** add JSON schemas or CLIs to every skill by default. Every skill should be machine-auditable, but ordinary instructional skills do not need their own JSON artifact or CLI unless there is a real machine consumer, live checks, redaction, CI integration, or mature executable workflow.

Target enforcement loop:

```text
schema → audit_skill.py → baseline/no-regression compare → CI required check → branch protection → blocker-only review
```

## Non-goals

- Do not mutate audited skills from inside `audit_skill.py`.
- Do not run destructive commands from the audit script.
- Do not run `git add`, `git commit`, `git checkout`, `git reset`, `chmod -R`, `rm -rf`, or external side-effect commands from the audit script.
- Do not print secret values; findings must use redaction and metadata only.
- Do not create repo-local `__pycache__`, `.pytest_cache`, temp files, logs, build outputs, or generated artifacts.
- Do not implement SARIF, owning CLI, OPA/Conftest, or per-skill JSON contracts before the internal JSON contract is stable.
- Do not treat this plan snapshot as current without re-checking live repo state before implementation.

## Steps

### Phase 0 — stabilize the starting state

- [ ] Re-check live branch, HEAD, and dirty state before code changes.
- [ ] Separate audit-gate changes from unrelated dirty work in `hermes-agent`, `knowledge-architecture`, `hermes-agent-skill-authoring`, and `subagent-driven-development` areas.
- [ ] Decide whether current dirty `skill-audit-and-improvement/SKILL.md` should be committed, amended, or revised.
- [ ] Decide whether untracked `references/audit-protocol-contract.md` is canonical and should be kept.
- [ ] Remove generated artifact `scripts/__pycache__/audit_skill.cpython-311.pyc` or explicitly block it via audit rules.
- [ ] Verify target skill tree contains no generated/runtime artifacts before claiming clean state.

Profit:

- Prevents building the quality gate on top of mixed unrelated changes.
- Makes later diff/review attributable: audit-gate changes are not confused with other work.
- Removes current contradiction: the plan says no repo artifacts, but `__pycache__` exists.
- Reduces rollback risk because the target scope is isolated.

### Phase 1 — add tests and negative fixtures before rewriting logic

- [ ] Create `tests/skills/test_audit_skill.py`.
- [ ] Add fixtures for invalid frontmatter, stale path, secret-like value, unsafe command, missing triggers, duplicate owner, generated artifact, and script syntax error.
- [ ] Cover JSON parse smoke, self-audit smoke, invalid repo, missing skill, malformed YAML, secret redaction, unsafe `git diff | grep token`, broken link, generated artifact, and Python syntax error.
- [ ] Run tests without bytecode/cache artifacts.

Expected command:

```bash
cd /home/konstantin/.hermes/hermes-agent
PYTHONDONTWRITEBYTECODE=1 HERMES_TEST_WORKERS=1 scripts/run_tests.sh tests/skills/test_audit_skill.py -q -p no:cacheprovider
```

Profit:

- Creates safety net before modifying `audit_skill.py`.
- Prevents regression in redaction, read-only behavior, and exit-code behavior.
- Makes future refactoring cheaper because behavior is specified by fixtures.
- Catches negative cases, not just happy path.

### Phase 2 — define stable JSON contract v1

- [ ] Create `skills/software-development/skill-audit-and-improvement/schemas/audit-report.schema.json`.
- [ ] Create `skills/software-development/skill-audit-and-improvement/references/finding-taxonomy.md`.
- [ ] Create `skills/software-development/skill-audit-and-improvement/references/degradation-policy.md`.
- [ ] Add optional validator script: `skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py`.
- [ ] Make every JSON report include:
  - `schema_version`;
  - `tool`;
  - `repo`;
  - `target`;
  - `summary`;
  - `findings`;
  - `checks`;
  - `evidence_manifest`.
- [ ] Use one finding model with stable `rule_id`, `severity`, `category`, `location`, `evidence`, `suggested_fix`, and `fingerprint`.
- [ ] Keep machine JSON in stdout and human errors in stderr.

Profit:

- Turns JSON from ad-hoc output into a public machine contract.
- Enables CI, baseline compare, schema validation, and automated review.
- Makes findings comparable across runs via stable fingerprints.
- Prevents contract drift when future agents patch the script.

### Phase 3 — harden resolver and exit-code contract

- [ ] Add explicit `--path skills/<category>/<skill>` mode.
- [ ] Keep `--skill <frontmatter-name>` but require exactly one match.
- [ ] Reject path traversal, absolute paths outside repo, and targets outside `repo/skills`.
- [ ] Require target `SKILL.md` to exist.
- [ ] Add optional `--output /tmp/report.json`, allowing writes only outside repo.
- [ ] Normalize exit codes:
  - `0` = no blockers;
  - `1` = blockers found;
  - `2` = invalid input / runtime invocation error.

Profit:

- Makes the tool safe for CI and shell automation.
- Removes ambiguity between skill names and paths.
- Prevents accidental auditing of files outside the skill tree.
- Allows agents/CI to distinguish “bad skill” from “bad invocation”.

### Phase 4 — implement deterministic rule engine

- [ ] P0 blockers:
  - missing `SKILL.md`;
  - invalid frontmatter;
  - missing required `name` / `description`;
  - description not starting with `Use when ...`;
  - broken executable path;
  - stale source/runtime path in executable instruction;
  - secret-like value without redaction;
  - unsafe command that can print secrets;
  - Python syntax error in `scripts/*.py` / `cli/*.py`;
  - invalid claimed CLI JSON;
  - audit script write/read-only contract violation;
  - generated artifacts in skill tree;
  - self-audit recursion risk.
- [ ] P1 warnings:
  - weak triggers;
  - missing `When not to use`;
  - missing boundary with related skills;
  - missing verification guidance;
  - missing rollback guidance after mutation workflow;
  - oversized `SKILL.md`;
  - template embedded in `SKILL.md` instead of `templates/`;
  - orphan or empty support file;
  - unresolved related skill;
  - duplicate or unclear ownership.
- [ ] P2 recommendations:
  - move long case to `references/`;
  - move reusable format to `templates/`;
  - add deterministic script;
  - add CLI only if there is repeated live workflow / JSON consumer / CI integration;
  - add SARIF only after stable JSON.

Profit:

- Converts subjective “looks good” review into repeatable evidence-based checks.
- Blocks security, source/runtime, and executable breakages early.
- Keeps warnings separate from blockers so old noise does not disable the gate.
- Encourages correct library architecture: SKILL.md vs references/templates/scripts/cli.

### Phase 5 — make `--changed` the practical quality-gate mode

- [ ] Collect changed files read-only:

```bash
git diff --name-only
git diff --name-only --cached
git ls-files --others --exclude-standard
```

- [ ] Group changes by `skills/<category>/<skill>/`.
- [ ] Audit each affected skill fully, not only the changed lines.
- [ ] Classify change type:
  - `SKILL.md` = procedure/trigger/body change;
  - `references/` = case/design/context;
  - `templates/` = reusable output format;
  - `scripts/` = deterministic validation/tooling;
  - `cli/` = operational tool contract;
  - `schemas/` = machine contract.
- [ ] Report `changed_files`, `affected_skills`, `affected_non_skill_files`, `summary`, and `findings`.

Profit:

- Makes the common PR/local workflow fast and relevant.
- Prevents a small changed line from hiding a broken whole skill.
- Gives CI enough context to block affected skills without auditing the world every time.
- Supports architectural review of where a change belongs.

### Phase 6 — add baseline / no-regression policy

- [ ] Create baseline file after first full audit, likely `.skills-audit-baseline.json` or a skill-owned baseline path if repo policy prefers that.
- [ ] Store known finding fingerprints, severity, source metadata, and temporary exception metadata.
- [ ] Block:
  - new blocker;
  - new secret-like finding;
  - new stale path;
  - schema invalid;
  - audit failed;
  - audit script read-only violation.
- [ ] Warn or require review for new recommendations/warnings depending on budget.
- [ ] Allow known old warnings temporarily, with explicit owner/expiry if needed.

Profit:

- Avoids the “first audit is too noisy, so gate gets disabled” failure mode.
- Separates legacy debt from new regressions.
- Lets the repo improve incrementally without accepting new damage.
- Provides measurable progress: fixed, unchanged, new, and changed findings.

### Phase 7 — enforce via GitHub Actions required check

- [ ] Create `.github/workflows/skills-quality-gate.yml`.
- [ ] Ensure the job runs always and is not conditionally skipped.
- [ ] Minimum CI steps:
  - `git diff --check`;
  - `audit_skill.py --changed --json --output /tmp/skills-audit-report.json`;
  - validate report schema;
  - compare baseline.
- [ ] Keep check name stable, e.g. `audit-skills` or `skills-quality-gate`.
- [ ] Ensure logs do not expose secret values.

Profit:

- Moves protection from agent habit to repository enforcement.
- Catches degradation before merge.
- Gives consistent feedback to humans and agents.
- Avoids the GitHub skipped-job trap where a required skipped job can appear successful.

### Phase 8 — protect the gate with CODEOWNERS and branch protection

- [ ] Add or update `.github/CODEOWNERS` for:

```text
skills/software-development/skill-audit-and-improvement/**
skills/**/scripts/**
skills/**/cli/**
.skills-audit-baseline.json
.github/workflows/skills-quality-gate.yml
```

- [ ] Enable branch protection after CI is stable:
  - require PR before merging;
  - require status check;
  - require up-to-date branch;
  - require CODEOWNERS review;
  - dismiss stale approvals;
  - no bypass;
  - no force pushes;
  - no deletions.
- [ ] Use blocker-only review criteria:
  - stale paths;
  - secrets;
  - unsafe commands;
  - invalid frontmatter;
  - broken CLI JSON;
  - missing verification;
  - duplicate skill ownership;
  - audit bypass;
  - read-only contract violation.

Profit:

- Prevents silent weakening of the audit gate itself.
- Ensures scripts/CLIs that can affect future agent behavior get owner review.
- Makes governance enforceable, not advisory.
- Reduces risk of bypass through workflow edits or baseline edits.

### Phase 9 — update the skill as the procedural source of truth

- [ ] Update `SKILL.md` after implementation reflects reality, not aspiration.
- [ ] Keep `references/audit-protocol-contract.md` as canonical design rationale.
- [ ] Update `templates/audit-report.md` to fixed report format:

```text
Changed:
Why:
Verified:
Remaining:
Rollback:
```

- [ ] Add self-audit JSON fields for target `skill-audit-and-improvement`:

```json
{
  "self_audit": true,
  "self_audit_loop_limited": true
}
```

Profit:

- Keeps future agent behavior aligned with the implemented gate.
- Prevents drift between plan, script, and skill instructions.
- Makes self-audit bounded so the skill does not recurse forever.
- Improves handoff quality: every future audit report has the same structure.

### Phase 10 — mature extensions only after core gate is stable

- [ ] Add SARIF only after internal JSON is stable.
- [ ] Add owning CLI only if there is a real consumer and stable command interface need.
- [ ] Consider policy-as-code only if Python checks become governance-heavy.
- [ ] Do not spread JSON/CLI contracts to every skill by default.

Potential future CLI shape:

```bash
skills-audit audit --changed --json
skills-audit audit --skill <name> --json
skills-audit doctor --json
skills-audit schema validate /tmp/report.json
skills-audit baseline compare --current /tmp/report.json
```

Profit:

- Avoids premature complexity and maintenance burden.
- Keeps the core contract stable before adding adapters.
- Ensures SARIF/CLI are projections of the same findings model, not separate systems.
- Preserves the architecture principle: ordinary skills stay machine-auditable without own CLI/JSON.

## Verification

Before starting implementation from this plan:

```bash
cd /home/konstantin/.hermes/hermes-agent
git branch --show-current
git rev-parse --short=12 HEAD
git status --short --branch --untracked-files=all
```

Minimum local verification after script changes:

```bash
cd /home/konstantin/.hermes/hermes-agent
git diff --check
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
import ast
path = Path('skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py')
ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('syntax_ok')
PY
PYTHONDONTWRITEBYTECODE=1 HERMES_TEST_WORKERS=1 scripts/run_tests.sh tests/skills/test_audit_skill.py -q -p no:cacheprovider
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --skill skill-audit-and-improvement --json
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --changed --json
```

Smoke acceptance:

- invalid repo returns exit `2`;
- missing skill returns exit `2`;
- malformed YAML returns blocker and exit `1`;
- unsafe `git diff | grep token` returns finding without leaking token;
- secret-like value returns redacted finding only;
- self-audit returns `self_audit: true` and `self_audit_loop_limited: true`;
- no `__pycache__`, `.pyc`, `.pytest_cache`, temp/log/build artifacts appear under the skill directory.

## Definition of Done

- `audit_skill.py` is read-only by design and by tests.
- `audit_skill.py` does not create repo-local generated artifacts.
- `--json` is valid against `schemas/audit-report.schema.json`.
- JSON includes `repo`, `target`, `summary`, `findings`, `checks`, and `evidence_manifest`.
- Findings have stable `rule_id` and `fingerprint`.
- Secret values are never printed.
- Exit codes are stable: `0`, `1`, `2`.
- `--changed` groups affected skills and audits them fully.
- Negative fixtures cover main degradation classes.
- Baseline/no-regression separates old noise from new damage.
- GitHub Actions required check blocks regressions.
- CODEOWNERS protects audit gate, scripts, CLIs, baseline, and workflow files.
- Branch protection is enabled after CI stability.
- `SKILL.md`, references, templates, scripts, schema, tests, CI, and review policy tell one consistent story.

## Risks / pitfalls

- Dirty repo state can hide which change introduced a finding.
- Baseline without stable fingerprints is not useful.
- CI without baseline can be too noisy and get disabled.
- Required GitHub job can be skipped and still appear successful if configured incorrectly.
- Secret scanners can leak values if they print matching lines instead of metadata.
- Path/link checks can false-positive on intentional stale-path guard text.
- Running Python compile/tests without `PYTHONDONTWRITEBYTECODE=1` can recreate artifacts.
- Premature SARIF/CLI/per-skill JSON can increase maintenance surface before core contract stabilizes.

## Status
Current status: in_progress

## Notes

- Created as synthesized master plan after live inspection and review of existing audit-skill plans.
- Existing companion plans remain active until an explicit lifecycle decision archives or supersedes them.
- Re-check live repo state before implementation; this plan records a snapshot, not a permanent fact.
- 2026-05-08 06:00 +05: Local/pre-CI subset is implemented and verified: phases 0-6 core outcomes are present in `audit_skill.py`, schema/validator/tests/fixtures; focused tests `18 passed`; final targeted independent review returned no blockers/warnings. Phase 7+ CI/CODEOWNERS/branch protection remain future work and were intentionally not executed.
