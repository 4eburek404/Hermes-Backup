# audit_skill.py v2 — deterministic quality gate plan

## Цель

Превратить `skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py` из structural checker в deterministic, read-only quality gate для Hermes skills.

Gate должен надежно отвечать:

- `pass` — skill безопасен, исполним и не ломает архитектуру библиотеки;
- `blockers` — skill нельзя считать валидным;
- `warnings` — надежность снижена;
- `recommendations` — есть архитектурные улучшения.

Скрипт не принимает продуктовых решений за агента, но дает машинно-читаемую evidence-based диагностику.

## Scope

Target repo:

```bash
/home/konstantin/.hermes/hermes-agent
```

Target skill:

```bash
skills/software-development/skill-audit-and-improvement/
```

Primary files in scope:

```bash
skills/software-development/skill-audit-and-improvement/SKILL.md
skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py
skills/software-development/skill-audit-and-improvement/templates/audit-report.md
skills/software-development/skill-audit-and-improvement/references/case-study-2026-05-07-systemd-skill-improvement.md
skills/software-development/skill-audit-and-improvement/references/audit-protocol-contract.md
skills/software-development/skill-audit-and-improvement/schemas/        # planned, not present yet
```

This plan is now implementation-tracking. Re-check live repo state before any code/skill mutation; do not rely on this snapshot as current after it ages.

## Non-goals

- Do not mutate audited skills from inside `audit_skill.py`.
- Do not run destructive commands.
- Do not run `git add`, `git commit`, `git checkout`, `git reset`, or permission-changing commands from the audit script.
- Do not print secret values.
- Do not create repo-local `__pycache__`, `.pytest_cache`, temp files, logs, build outputs, or generated artifacts.
- Do not replace agent judgment: script reports evidence/findings; agent decides improvement type.

## Required execution order for future implementation

```text
inspect repo → collect evidence → audit → decide improvement type → patch → validate → review → report
```

No patching before evidence manifest exists.

## Live state check — 2026-05-08 04:16 +05

Evidence commands were run against the live filesystem before this update:

```bash
cd /home/konstantin/.hermes/hermes-agent
git branch --show-current
git rev-parse --short=12 HEAD
git status --short --branch --untracked-files=all
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --help
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --skill skill-audit-and-improvement --json
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --changed --json
```

Verified snapshot:

- Branch: `fix/ollama-native-auxiliary-routing`.
- HEAD: `7e93bf155c2e`.
- Repo is dirty before this plan update; relevant target diff before plan edit:
  - modified `skills/software-development/skill-audit-and-improvement/SKILL.md`;
  - untracked `skills/software-development/skill-audit-and-improvement/references/audit-protocol-contract.md`;
  - additional unrelated dirty files exist in `hermes-agent`, `hermes-agent-skill-authoring`, and `subagent-driven-development` areas.
- `audit_skill.py --help` currently exposes `--repo`, `--skill`, `--all`, `--changed`, `--json`; it does **not** expose a separate `--path` option.
- AST syntax check for `scripts/audit_skill.py` passed via `ast.parse`.
- Single-skill audit result for `skill-audit-and-improvement`: `ok: true`, `issues: []`, `warnings: []`, support summary `references: 2`, `templates: 1`, `scripts: 1`, `cli.exists: false`.
- Changed-file audit result: `changed_file_count: 7`, `ok: true`, `issue_count: 0`, `warning_count: 0`.
- Negative smoke current behavior differs from target: invalid repo returns exit code `1`, missing skill returns exit code `1`; target below requires exit code `2` for invalid input/runtime invocation errors.
- Generated artifact exists under the target skill despite the plan's no-artifacts goal:
  - `skills/software-development/skill-audit-and-improvement/scripts/__pycache__/`
  - `skills/software-development/skill-audit-and-improvement/scripts/__pycache__/audit_skill.cpython-311.pyc`
- `/home/konstantin/docs` did not present as a git repo in this check; plan edits are filesystem-backed docs edits, not repo commits.

Interpretation: the current script is a useful structural checker and redacting changed-file scanner, but it is not yet the stable deterministic quality gate described by this plan.

## Current implementation delta

Implemented / partially implemented now:

- `--repo`, `--skill`, `--all`, `--changed`, `--json` modes exist.
- `--skill` accepts frontmatter name, skill directory, or `SKILL.md` path.
- Frontmatter checks exist: start marker, YAML parse, required name/description, description length, body presence, name shape warning.
- Basic required-section checks exist for `Overview`, `When to Use`, `Common Pitfalls`, `Verification Checklist`.
- Related skill unresolved warning exists.
- Stale-source path scan exists for known bad paths.
- Secret-like assignment scan and unsafe `git diff|grep secret` scan exist and avoid printing matched secret values.
- Support summary exists for `references`, `templates`, `scripts`, `assets`; `cli` existence summary exists.
- `--changed` uses read-only git commands and reports changed files, secret-like findings, stale-path warnings, unsafe-scan findings.

Not implemented / still required:

- Repo context is not included in JSON output as a structured `repo` object.
- No explicit `--path` flag; path support is folded into `--skill`.
- No strict inside-`skills/` resolver / path-traversal rejection contract.
- No stable schema version, `tool` object, stable `summary`, unified `findings`, `checks`, `evidence_manifest`, fingerprints, or rule taxonomy.
- No JSON Schema files or report self-validation.
- Exit codes are not normalized to the planned contract: invalid repo and missing skill currently return `1`, not `2`.
- `--changed` does not group changed files by affected skill or audit each affected skill automatically.
- No markdown link/health checker beyond known stale-path literals.
- No generated-artifact detector; `__pycache__` exists right now.
- No AST syntax checks inside the audit script for changed skill Python files.
- No CLI contract/test runner checks beyond passive `cli.exists` metadata.
- No duplicate/ownership heuristic beyond unresolved `related_skills`.
- No self-audit JSON flags (`self_audit`, `self_audit_loop_limited`).
- No baseline/no-regression compare, CI workflow, branch protection, CODEOWNERS, negative fixtures, SARIF, or owning CLI.

## P0 — critical quality-gate requirements

### 1. Repo root and git context manifest

Add deterministic repo context collection:

```bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse --short=12 HEAD
git status --short --branch --untracked-files=all
```

JSON must include:

- repo root;
- branch;
- commit;
- dirty/clean state;
- changed/staged/untracked files where applicable.

### 2. Strict target resolver

Support:

```bash
--skill <skill-name>
--path skills/<category>/<skill>
--changed
```

Rules:

- target skill must exist;
- target path must resolve inside repo `skills/`;
- reject path traversal like `../../`;
- `--skill <name>` must find exactly one skill;
- ambiguity must be explicit blocker/input error;
- `SKILL.md` must exist.

### 3. Frontmatter validation as blocker

Check:

- frontmatter exists;
- YAML parses cleanly;
- required fields exist;
- `name` is non-empty and valid;
- `description` is non-empty and starts with `Use when ...`;
- `name` matches skill identity/directory expectations;
- metadata fields are not conflicting/stale;
- body exists after frontmatter.

Broken frontmatter = blocker.

### 4. Trigger and boundary checks

Detect explicit evidence for:

- `When to Use`;
- `Do not use` / `When not to use`;
- decision criteria;
- boundary with related skills.

Missing triggers = warning; for core skills can be blocker.

### 5. Executability checks

Detect concrete operational content:

- commands;
- paths;
- expected outputs;
- validation steps;
- rollback/cleanup steps when repo/runtime is changed.

Warn on high-level prose with no executable procedure.

### 6. Stale paths and markdown links

Extract and validate references from `SKILL.md` and support files:

- `skills/...`;
- `references/...`;
- `templates/...`;
- `scripts/...`;
- `cli/...`;
- relative markdown links.

Check target existence. Keep intentional stale-path guard text from false-positiveing, but real broken links/paths must be findings.

### 7. Support files integrity

For `references/`, `templates/`, `scripts/`, `assets/`, `cli/`:

- mentioned directories exist;
- files are not empty;
- markdown links are valid;
- scripts are executable or at least syntax-checkable/runnable by documented command;
- templates contain clear placeholders;
- references do not replace the main procedure entirely;
- support files are not orphaned unless justified.

### 8. Secret-like values with redaction

Detect but never print values:

- API keys;
- bearer tokens;
- private keys;
- passwords;
- `.env`-like assignments;
- hardcoded credentials;
- dangerous command examples with tokens.

JSON finding should include only:

- file;
- line;
- detector type;
- redacted preview;
- severity.

### 9. Unsafe shell/git recommendations

Detect unsafe recommendations such as:

```bash
git diff | grep token
cat .env
grep -R SECRET .
rm -rf ...
curl ... | sh
chmod -R 777
```

For secret scans, recommended fix should point to metadata-only redacting scan, e.g. `audit_skill.py --changed --json`.

### 10. Read-only contract for audit script

Audit script must not:

- write in repo;
- change files;
- run destructive commands;
- create `__pycache__`;
- change permissions;
- run `git add/commit/checkout/reset`.

If temporary files are required, use tempdir outside repo and clean up.

## P1 — quality and maintainability requirements

### 11. SKILL.md size and density

Check:

- too long;
- too short;
- large sections better suited for `references/`;
- repeated sections;
- templates embedded in main `SKILL.md` instead of `templates/`.

This supports the architecture rule:

- small lesson → patch `SKILL.md`;
- long case → `references/`;
- reusable format → `templates/`;
- deterministic check → `scripts/`;
- live checks + JSON + redaction → `cli/`.

### 12. Verification section

Skill should describe how to validate the workflow.

Look for:

- `git diff --check`;
- syntax checks;
- script-specific tests;
- `--json doctor`;
- smoke tests;
- review criteria.

Missing verification in a code-changing skill = serious warning.

### 13. Source/runtime cleanup

Detect runtime/generated artifacts:

- `__pycache__/`;
- `.pytest_cache/`;
- temp files;
- generated files;
- build outputs;
- logs;
- downloaded assets.

Check whether cleanup guidance exists.

### 14. Python syntax without repo artifacts

For Python files in `scripts/` or `cli/`, use AST parse by default to avoid bytecode:

```bash
python3 - <<'PY'
from pathlib import Path
import ast
path = Path('<script.py>')
ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('syntax_ok')
PY
```

Syntax error = blocker.

### 15. CLI contract if `cli/` exists

Check:

- entrypoint exists;
- `--help` works;
- `--json` exists if JSON is claimed;
- `doctor` or equivalent self-check exists;
- exit codes are meaningful;
- errors do not disclose secrets;
- JSON output is parseable.

### 16. Tests for scripts/cli

Check:

- test files exist for non-trivial logic;
- tests can run without external side effects;
- basic tests do not require secrets.

### 17. Related skills and ownership

Find possible duplicate/overlap by:

- names;
- descriptions;
- triggers;
- paths;
- key terms.

Output recommendations:

- patch existing skill;
- create reference;
- create template;
- create script;
- create new skill only if no workflow owner exists.

### 18. Architectural form of changes

For `--changed`, classify changed files:

- lesson in `SKILL.md`;
- case study in `references/`;
- reusable artifact in `templates/`;
- deterministic validation in `scripts/`;
- operational tool in `cli/`.

This should normally be recommendation/warning, not blocker.

## P2 — maturity requirements

### 19. Evidence manifest

JSON must list what was actually inspected:

- `SKILL.md`;
- support files;
- related skills;
- git diff metadata;
- scripts;
- cli;
- tests.

Purpose: prevent false claims like “checked” when evidence was not collected.

### 20. Stable machine-readable JSON schema

Target schema shape:

```json
{
  "ok": true,
  "skill": "skill-audit-and-improvement",
  "path": "skills/software-development/skill-audit-and-improvement/SKILL.md",
  "repo": {
    "root": "/home/konstantin/.hermes/hermes-agent",
    "branch": "skills-improvements",
    "commit": "...",
    "dirty": true,
    "changed_files": []
  },
  "summary": {
    "blockers": 0,
    "warnings": 0,
    "recommendations": 0,
    "info": 0
  },
  "evidence": {
    "read_files": [],
    "checked_links": [],
    "checked_scripts": [],
    "checked_cli": [],
    "related_skills": []
  },
  "findings": [
    {
      "severity": "blocker",
      "category": "stale_path",
      "file": "SKILL.md",
      "line": 42,
      "message": "...",
      "suggested_fix": "..."
    }
  ]
}
```

### 21. Severity and exit codes

Severity levels:

- `blocker` — cannot consider skill valid;
- `warning` — reliability degraded;
- `recommendation` — quality improvement;
- `info` — diagnostic fact.

Exit codes:

- `0` — no blockers;
- `1` — blockers found;
- `2` — invalid input / runtime invocation error.

### 22. Improved `--changed`

Use read-only git commands:

```bash
git diff --name-only
git diff --name-only --cached
git ls-files --others --exclude-standard
```

Group changed files by `skills/<category>/<skill>/` and audit affected skills automatically.

### 23. Markdown health

Check:

- broken links;
- empty headings;
- duplicate headings;
- unclosed code fences;
- too-long sections;
- orphan support files.

### 24. Rollback guidance

Agent final reports must include rollback command.

Script can check for rollback guidance such as:

```bash
git checkout -- skills/<category>/<skill>/
git clean -fd -- skills/<category>/<skill>/
```

### 25. Self-audit guard

For target `skill-audit-and-improvement`, JSON should include:

```json
{
  "self_audit": true,
  "self_audit_loop_limited": true
}
```

Rules:

- detect when target is the audit skill itself;
- avoid infinite nested audit;
- limit recursive recommendations;
- keep self-audit bounded to one cycle unless user explicitly asks for another pass.

## Agent procedure additions

### Blocker-only review criteria

Independent review must explicitly check:

- stale paths;
- secret leakage;
- unsafe commands;
- broken frontmatter;
- read-only contract violations;
- invalid Python/CLI;
- duplicate skills or unclear ownership.

### Ownership gate before new skill creation

New skill is allowed only if:

- no existing workflow owner exists;
- related skills were checked;
- distinction is formulated;
- triggers do not dangerously overlap;
- minimal verification path exists.

### Anti-regression check after implementation

Always run:

```bash
git diff --check
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --changed --json
```

If Python changed, run AST syntax check for changed Python files.

### Final report format

Use fixed format:

```text
Changed:
- ...
Why:
- ...
Verified:
- ...
Remaining:
- ...
Rollback:
- ...
```

## Implementation phases

Legend: `[x]` locally implemented/verified enough for the pre-CI gate, `[~]` intentionally partial or future-hardening, `[ ]` out of current scope / not implemented.

### Phase 0 — reconcile current dirty state before coding

- [x] Branch/HEAD/status and target diff checked before implementation.
- [x] Generated `__pycache__` / `.pyc` artifacts removed and verified absent after tests.
- [x] Unrelated dirty work kept separate in reporting; no broad cleanup of other skills was attempted.
- [~] Existing dirty `skill-audit-and-improvement/SKILL.md` and untracked references are now part of the local audit-gate workstream, but remain uncommitted.

### Phase 1 — P0 gate foundation

- [x] Repo manifest added to JSON (`repo.root`, `repo.branch`, `repo.commit`, `repo.dirty`, changed/staged/untracked files).
- [x] Strict resolver added for `--skill`, `--path`, `--all`, `--changed`; traversal/outside-skill targets reject with exit `2`.
- [x] Unified finding model added: `findings`, `checks`, rule IDs, fingerprints, categories, evidence, suggested fixes.
- [x] Frontmatter checks hardened with blocker/warning taxonomy and name/directory checks.
- [x] Trigger/boundary checks added for required sections and when-not-to-use boundaries.
- [x] Markdown link validation added.
- [x] Support-file integrity checks added for empty files, generated artifacts, syntax, support dirs, schemas/baselines.
- [x] Secret/unsafe command detectors hardened with redaction and negative regression tests.
- [x] Read-only contract heuristics added for audit-owned scripts/docs.

### Phase 2 — P1 quality checks

- [~] Size checks exist; deeper density/repetition heuristics remain future-hardening.
- [~] Verification guidance is checked structurally; semantic quality remains review-driven.
- [x] Generated artifact detection implemented and repo-local artifacts verified absent.
- [x] AST syntax checks for skill Python support files implemented.
- [~] CLI contract check remains lightweight (`cli.exists`/shape); no arbitrary CLI execution in local read-only gate.
- [~] Test presence/basic-run is handled by the dedicated focused pytest suite, not by running tests from audit script.
- [x] Ownership/duplication heuristic added.
- [x] Changed-file architecture classification added (`SKILL.md`, `references/`, `templates/`, `scripts/`, `cli/`, `schemas/`, `baselines`).

### Phase 3 — P2 reporting maturity

- [x] Evidence manifest added.
- [x] Stable JSON schema and validator added under the target skill.
- [x] Severity and exit codes normalized: `0=no blockers`, `1=blockers`, `2=invalid input/runtime invocation error`.
- [x] `--changed` grouping improved: affected skills are grouped and audited fully, including deleted support files and nested deleted `SKILL.md`.
- [x] Markdown health checks added.
- [~] Rollback guidance remains primarily a plan/report requirement, not a full semantic rule.
- [x] Self-audit JSON flags added (`self_audit`, `self_audit_loop_limited`).

### Phase 4 — degradation gate / CI maturity

- [x] Local baseline/no-regression compare implemented with stable fingerprints and known-finding suppression.
- [x] Negative fixtures added for invalid frontmatter, stale path, secret-like value, unsafe command, missing triggers, duplicate owner, generated artifact, script syntax error, deleted files, nested deleted `SKILL.md`, deterministic ordering, and multi-token/generic Bearer redaction.
- [ ] GitHub Actions required check is intentionally not implemented in this local/pre-CI pass.
- [ ] CODEOWNERS/blocker-only review policy is intentionally not implemented in this local/pre-CI pass.
- [ ] Branch protection is intentionally not implemented in this local/pre-CI pass.
- [~] SARIF and owning CLI remain deferred until the internal JSON contract is used beyond local automation.

## Validation plan for future implementation

Minimum validation:

```bash
git diff --check
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --skill skill-audit-and-improvement --json
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --changed --json
```

Python syntax:

```bash
python3 - <<'PY'
from pathlib import Path
import ast
path = Path('skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py')
ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('syntax_ok')
PY
```

Smoke cases:

- invalid repo returns exit code `2`;
- missing skill returns exit code `2`;
- malformed YAML returns blocker and exit code `1`;
- unsafe `git diff | grep token` returns finding without leaking token;
- intentional guard text does not false-positive;
- self-audit returns `self_audit: true` and `self_audit_loop_limited: true`;
- no `__pycache__` or `.pyc` appears under the skill directory.

Independent blocker-only review required for script changes.

## Rollback for future implementation

If implementation is local and uncommitted:

```bash
git checkout -- skills/software-development/skill-audit-and-improvement/
git clean -fd -- skills/software-development/skill-audit-and-improvement/
```

If committed:

```bash
git revert <commit>
```

## Status

Current status: in_progress

## Notes

- 2026-05-08 04:16 +05: Plan updated from live repo/tool checks, not memory. Current script is structurally useful but still below target stable quality gate. Highest next priority is Phase 0 cleanup/reconciliation, then Phase 1 repo manifest + resolver/exit-code contract + unified JSON findings.
- 2026-05-08 06:00 +05: Local/pre-CI implementation pass completed for clean scope, tests/fixtures, stable JSON schema, resolver/exit codes, deterministic rule engine, `--changed`, and baseline compare. Verified: focused tests `18 passed`, AST/schema/validator smokes OK, self audit exit `0` with blockers `0`, `--changed` exit `0` with blockers `0`, invalid input smokes exit `2`, `git diff --check` clean, no `__pycache__`/`.pyc`; final independent targeted review returned no blockers/warnings. CI/CODEOWNERS/branch protection intentionally not implemented in this pass.
