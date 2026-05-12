# Local audit gate hardening case — 2026-05-08

Reusable lessons from hardening `scripts/audit_skill.py` into a deterministic local quality gate before CI.

## Scope boundary

- Keep CI, CODEOWNERS, branch protection, and deploy enforcement separate from local pre-CI readiness unless the user explicitly asks for them.
- Local readiness means: clean scope, focused tests/fixtures, stable JSON schema, resolver/exit codes, deterministic rule engine, `--changed`, and baseline/no-regression compare.
- Do not claim ready after a final patch unless the post-patch verification bundle has run.

## Deterministic/read-only contract

`audit_skill.py` should remain read-only:

- no `git add`, `git commit`, `git checkout`, `git reset`;
- no destructive shell commands;
- no permission-changing commands;
- no mutation of audited skills;
- reject report outputs inside the repo (`OUTPUT_INSIDE_REPO`);
- avoid repo-local caches/artifacts during tests (`PYTHONDONTWRITEBYTECODE=1`, pytest `-p no:cacheprovider`).

## Redaction pitfall: parser errors can leak multi-token values

YAML/frontmatter parser errors may echo the offending line. Redacting only the first non-space token after a sensitive key is insufficient. A malformed line such as a sensitive-key assignment followed by a multi-token value can leak the remaining tokens through the parse error.

Rule:

- redact the entire rest of line/segment after sensitive assignment keys (`authorization`, `token`, `api_key`, `secret`, `password`, etc.);
- add a second pass for bearer-style values that redacts the full same-line `Bearer ...` segment, not just the first token;
- do not limit bearer redaction to recognized sensitive keys: malformed YAML can echo `Bearer ...` under generic keys such as `auth_header`, so regression tests must cover both sensitive-key and generic-key cases;
- run redaction on every report surface: finding message, evidence, line excerpt, check output, CLI error payload, and parser exception text;
- add regression tests using synthetic placeholder values only and assert the raw placeholders do not appear anywhere in JSON stdout or `--output` report files.

## `--changed` pitfall: deleted nested `SKILL.md`

Deleted files no longer exist, so resolver logic cannot rely only on filesystem ascent. For a deleted path ending in `SKILL.md`, the affected skill directory is the deleted path's parent, even when nested deeper than two levels, e.g.:

```text
skills/mlops/training/nested-skill/SKILL.md
```

Rule:

- if a changed/deleted path basename is `SKILL.md`, derive affected skill dir from `path.parent` first;
- avoid category-depth assumptions such as `skills/<category>/<skill>/SKILL.md`;
- include `exists: false` and `change_kind: deleted` in evidence;
- regression-test nested deleted `SKILL.md`, not only shallow deleted skills.

## Verification bundle after audit script changes

Run after every change to `scripts/audit_skill.py`, its schema, or validator:

```bash
cd /home/konstantin/.hermes/hermes-agent
PYTHONDONTWRITEBYTECODE=1 HERMES_TEST_WORKERS=1 scripts/run_tests.sh tests/skills/test_audit_skill.py -q -p no:cacheprovider
git diff --check -- skills/software-development/skill-audit-and-improvement tests/skills/test_audit_skill.py tests/fixtures/skills
```

Also verify:

- AST parse for `audit_skill.py` and `validate_audit_report.py`;
- schema JSON parse;
- self-audit report validates;
- `--changed` report validates;
- resolver errors return exit 2 for invalid repo, missing skill, traversal, and output-inside-repo;
- targeted redaction smokes prove both sensitive-key and generic-key multi-token `Bearer ...` parser-error values are absent from JSON stdout and `--output` report files;
- no repo `__pycache__`, `*.pyc`, or `.pytest_cache` remains;
- independent blocker-only review passes;
- if plans were updated, validate plan fences/status/secrets and run `knowledge --json plans audit` so the docs control surface reflects the implementation state.
