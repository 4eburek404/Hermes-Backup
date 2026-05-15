# Step 2A Advisory CLI Execution Case Note

Use this note when extending `audit_skill.py` from static inventory toward executable checks.

## Boundary

Step 2A is advisory-only executable CLI evidence behind `--deep-cli`:

- default audit remains static and non-executing;
- `--no-exec` wins over `--deep-cli`;
- CLI failures, timeouts, invalid doctor JSON, and test failures create warnings/evidence, not blocker errors;
- schema enforcement, strict mode, and `--enforce-cli` are explicitly out of scope.

## Safe-execution invariants

- Use `subprocess.run()` with argv list and `shell=False`.
- Use `capture_output=True`, `text=True`, `timeout=...`, `check=False`.
- Run from audited skill `cli/` when appropriate.
- Use a minimal sanitized environment; set `PYTHONDONTWRITEBYTECODE=1`, isolate `HOME`, preserve only minimal locale/path values, and never print env values.
- Hash full stdout/stderr before truncating previews.
- Redact command argv before serializing evidence; include next-token redaction for sensitive flags.

## Entrypoint safety lesson

Executable help checks must run only high-confidence local entrypoints. Static inventory may contain medium-confidence docs/filesystem hints, but Step 2A must not execute them. Independent review caught this exact blocker when `high_confidence_entrypoints()` allowed both `high` and `medium`; the fix was to filter strictly to `confidence == "high"` and add a regression test.

## Mutating candidate lesson

Block before subprocess execution when argv contains mutation risk, including `--delete=true`-style assignment flags. Regression tests should cover both standalone flags and `--flag=value` forms, plus mutating verbs (`deploy`, `install`, `remove`, `unlink`) and forbidden executables (`rm`, `mv`, `systemctl`, unsafe `cp`, `git push`).

## Verification pattern

After changes to advisory CLI execution:

1. Add/verify stdlib unittest fixtures for:
   - static mode without `--deep-cli`;
   - no-CLI skill;
   - help success;
   - doctor JSON success;
   - invalid doctor JSON advisory warning;
   - blocked mutating candidate;
   - `--no-exec` override;
   - `--run-cli-tests` explicitness;
   - report schema validation;
   - high-confidence-only execution.
2. Run the blocker reproduction first, then full suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_deep_cli_advisory.DeepCliAdvisoryTests.test_high_confidence_entrypoints_excludes_medium_confidence -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

3. Run AST syntax checks and `validate_audit_report.py` on emitted JSON reports.
4. Run at least one fixture with `cli/`, one fixture without `cli/`, one real runtime CLI skill if a high-confidence safe entrypoint exists, and one real no-CLI skill.
5. Remove generated `__pycache__/` and `.pyc` before final self-audit; otherwise `audit_skill.py` can correctly report `GENERATED_ARTIFACT` blockers.
6. For script/safety changes, run independent blocker-only review and fix any blocker in the actual execution path before claiming PASS.
