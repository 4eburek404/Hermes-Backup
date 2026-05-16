# Narrow Self-Audit Cleanup Pattern

Use this note when a user asks for a scoped cleanup of known `audit_skill.py` self-audit findings such as `SECRET_LIKE_VALUE` or `STALE_PATH`, while explicitly forbidding feature work, detector changes, deep CLI execution, runtime sync, or push.

## Pattern

1. Treat the user's branch, HEAD, clean-tree, and allowed-file list as the contract. Stop before mutation if any provenance gate fails.
2. Inspect the exact finding line and surrounding context before editing. Classify the finding source, for example:
   - `DOC_EXAMPLE_LITERAL` / `COMMAND_EXAMPLE_PATH` — documentation example or command path only.
   - `TEST_FIXTURE_LITERAL` — fixture string needed for regression coverage.
   - `DETECTOR_PATTERN_LITERAL` — scanner/detector source text that trips another scanner.
   - `REAL_SECRET_RISK` / `REAL_PROVENANCE_PATH` — stop and report instead of silently rewriting.
3. Make the smallest neutral rewrite:
   - secret-like docs: use prose such as “credential-shaped example” or “secret-like CLI flag value”.
   - stale paths: use placeholders such as `<repo>`, `<skill_dir>`, `<runtime_skill>`, `<temp_repo>`, or prose such as “the git checkout skill path”.
   - fixtures that need sensitive/stale shape at runtime: construct from safe fragments in tests while preserving assertions.
4. Do not change detector semantics unless the finding is caused only by a source literal or identifier and the runtime behavior is unchanged.
5. Verify with the exact requested lightweight tests, syntax/JSON checks, generated-artifact scan, and a temporary top-level `skills/` repo when the checkout stores skills under `hermes/skills/`.
6. Interpret self-audit results by severity and scope:
   - `audit_skill.py` rc may be nonzero while a declared out-of-scope baseline blocker remains.
   - For the final blocker cleanup step, success means blockers are gone, the report validates, and `cli_contract.execution_performed=false`.
   - Remaining warnings should be reported, not fixed, unless the user asked for them.
7. Stage only the allowed path(s), run an allowlist guard before commit, commit locally, and explicitly confirm no push/runtime sync/deep CLI/CLI-output validation occurred.

## Pitfalls

- Do not let a one-blocker cleanup become a warning cleanup, schema enforcement step, or feature implementation.
- Do not run audited skill CLIs or `--deep-cli` just because the audit skill owns CLI checks; static self-audit is enough unless the user explicitly expands scope.
- Avoid printing raw secret-like diff snippets when reviewing; use metadata-only scan results and neutral summaries.
- A remaining `STALE_PATH` warning is not the same as a `STALE_PATH` blocker; report severity precisely.
