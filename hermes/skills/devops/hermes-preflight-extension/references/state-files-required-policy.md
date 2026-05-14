# State Files Required Policy (R14D-1b)

## What changed

MEMORY.md, USER.md, and SOUL.md were previously treated as optional (missing = warning).
As of R14D-1b, they are **required persistent state files** — missing any of them is a
release-critical FAIL.

## Why

These files contain agent personality, user profile, and behavioral constitution.
Shipping a release without them means the agent runs with blank identity and no guardrails,
which is worse than refusing to release.

## Implementation pattern

In `check_state_files()`:
- Missing → `errors.append(f"{fname} missing — required state file")` (not `warnings.append`)
- No local `warnings` list in the function body (the `state_files_warnings` accumulator in
  results dict is still used by other checks)
- `state_files_status` metadata field: `"PASS"` if `state_files_ok` is True, `"FAIL"` otherwise
- Report label changed from `"AS. State files OK"` to `"AS. State files status"`

## Full changes required (WARN → FAIL promotion checklist)

1. **Script**: Change `warnings.append("…missing (warning)")` → `errors.append("…missing — required state file")`
2. **Script**: Remove `warnings = []` from function body; remove `results["state_files_warnings"] = warnings` (but keep the results accumulator used by other checks)
3. **Script**: Add `state_files_status` field: `"PASS"` / `"FAIL"`
4. **Script**: Update docstring: "required persistent state files, missing is FAIL"
5. **Script**: Update report label: from boolean yes/no to status string
6. **Script**: Update notes section: remove "missing files are OK" wording
7. **Docs**: Update "What it does" section for the check
8. **Docs**: Update metadata fields section
9. **Docs**: Update "What it does NOT do" with "but FAILs if missing"
10. **Docs**: Add/expand troubleshooting entry for the new FAIL condition
11. **Docs**: Add to Safety guarantees: "read-only — never create, edit, or delete"
12. **Tests**: Rename `_is_warning` → `_fails`
13. **Tests**: Change assertions from warning strings to FAIL strings
14. **Tests**: Add metadata field presence test for `_status`
15. **Tests**: Add source-level test: `errors.append` + `required state file` in function body
16. **Tests**: Do NOT use functional `_run_preflight()` for overall FAIL when state files are missing — minimal hermes_home exits with code 1 (fatal), not code 2 (FAIL)

## Test pattern

Source-level tests are preferred over functional tests for policy assertions:

```python
def test_missing_memory_md_fails():
    src = SCRIPT.read_text()
    assert "required state file" in src

def test_missing_state_files_produce_errors_not_warnings():
    src = SCRIPT.read_text()
    idx = src.find("def check_state_files")
    end_idx = src.find("\ndef ", idx + 1)
    func_src = src[idx:end_idx]
    assert "errors.append" in func_src
    assert "required state file" in func_src
    assert "warnings = []" not in func_src
```

## Recovery

Preflight does NOT create placeholder files. Recovery of missing state files is a
separate manual task — typically restoring from backup or re-initializing via the
agent's built-in file generation.

## Session pitfalls encountered (R14D-1b / R14E-0)

1. **`git checkout HEAD -- <file>` discards working-tree patches**: After full preflight
   run, the test file disappeared. `git checkout HEAD -- tests/test_hermes_release_preflight.py`
   restored it to HEAD version — wiping all patches applied in the working tree.
   Safe pattern: checkout HEAD first, THEN apply patches, THEN verify with grep.
   Re-applying 5 patches to a restored file cost a full extra cycle.

2. **`git restore` vs `git submodule update --init`**: A tracked file → `git restore`.
   A git submodule (mode 160000 like `tinker-atropos`) → `git submodule update --init`.
   Always `git ls-tree HEAD <path>` first: mode `160000` = submodule.

3. **Disk space**: Old RCs in `~/.hermes/releases/` consume ~300MB each (venv + cache).
   Before running `--replace-rc`, check `df -h /` and remove non-production RCs.
   Production target: `readlink ~/.hermes/hermes-agent`.