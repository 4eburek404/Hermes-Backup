# R11D — Release Preparation Helper/Checklist

## Context

After R11C release-dir deploy plan was documented, R11D implements an executable
helper/checklist script that validates production readiness without mutation.

## Script: `scripts/prepare_hermes_compaction_release.py`

### Modes

- **default / `--check`**: read-only pre-flight checks. Emits JSON summary:
  - repo clean (git status, deleted tracked files)
  - production gateway active
  - production install path
  - production not mixed (no compaction runtime symbols from fork)
  - compaction disabled in production config
  - Docker sandbox files present in repo
  - No destructive actions.

- **`--print-plan`**: prints the step-by-step release-dir deploy plan. No side effects.

- **`--create-release-dir PATH`**: creates release candidate directory at PATH.
  PATH must be under `/home/konstantin/.hermes/releases/`.
  PATH must NOT be under `/tmp`, `/var/tmp`, `/run/tmp`, `/dev/shm`.
  Does NOT: switch gateway, change config, change systemd, restart anything.

### Safety Properties

- Default mode is fully read-only: no file creation, no production mutation.
- `_redact_secrets()` strips API keys, passwords, bearer tokens, database URLs
  from any config data before emitting JSON.
- `/tmp` paths are explicitly rejected for release directories.
- Gateway switch remains a separate explicit manual operation.

### Key Pitfall: YAML Config Parsing with `line.strip()`

The helper's config parser for `tool_output_compaction.enabled` uses a minimal
YAML-like approach that reads the production config line by line. A critical bug
was found and fixed: the original code did `line.strip()` then checked if the
stripped line starts with space/tab. Since `strip()` removes all leading
whitespace, the stripped line never starts with space, so the parser would
always exit the section immediately after finding `tool_output_compaction:`.

**Fix**: check the original (unstripped) line for indentation, not the stripped one:
```python
if not line[0:1].isspace():  # original line, not stripped
    in_section = False
```

### Key Pitfall: Path Validation Under `/tmp`

`tmp_path` in pytest creates directories under `/tmp`. The `validate_release_dir_path()`
function rejects paths under `FORBIDDEN_PREFIXES` (which includes `/tmp`). Tests that
use `tmp_path` must patch `FORBIDDEN_PREFIXES` to remove `/tmp` for the test, or
use real release root paths in assertion setup.

### Key Pitfall: Regex Redaction Replaces Entire Match Including Key Name

`_redact_secrets()` regex patterns match `KEY=VALUE` patterns, so the entire
match including the key name gets replaced with `[REDACTED]`. Tests should NOT
assert that the key name (e.g., `OPENAI_API_KEY`) remains in the output — it
won't. Only assert that the secret value is absent and `[REDACTED]` is present.

## Tests

`tests/test_prepare_hermes_compaction_release.py` — 32 tests covering:

- `_redact_secrets()`: API key, password, bearer, database URL, clean text,
  multiple secrets
- `validate_release_dir_path()`: `/tmp` rejected, `/var/tmp` rejected, prefix
  mismatch rejected, existing path rejected, valid prefix accepted
- `check_docker_sandbox_files()`: all present, missing file, no directory
- `check_production_not_mixed()`: clean production, mixed production with
  compaction symbols
- `check_production_compaction_disabled()`: disabled explicit, enabled fails,
  section absent means disabled, config missing means disabled, secrets redacted
- `run_check()`: default mode is read-only, no file creation/deletion
- `run_create_release_dir()`: `/tmp` rejected, wrong prefix rejected, valid creation
- `run_print_plan()`: contains key sections, no side effects, no real tokens
- CLI: default check no-crash, print-plan returns zero, `/tmp` rejected