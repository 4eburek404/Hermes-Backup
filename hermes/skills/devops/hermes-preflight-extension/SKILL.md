---
name: hermes-preflight-extension
version: 1.0.0
description: Extending the Hermes release preflight script with new check categories, metadata fields, report sections, and tests.
triggers:
  - adding a new check to hermes_release_preflight.py
  - extending release_metadata.json fields
  - adding preflight report sections
  - fixing or extending existing preflight checks
  - updating ops/upstream-bundled-skills.txt
  - checking fork-only vs upstream-bundled skill classification
---

# Hermes Release Preflight Extension

Extending the Hermes release preflight script (`scripts/hermes_release_preflight.py`) with new check categories.

## Extension Recipe

Each new check category follows this exact sequence. Do them **in order** — skipping causes cascading failures.

### Special case: dependency checks that prevent silent runtime degradation

For dependencies whose absence does not crash imports but silently changes behavior, preflight must verify the **behavioral path**, not just `pip show` or `import`. Example: holographic fact_store HRR algebra silently falls back to FTS when `numpy` is unavailable. The durable pattern is documented in `references/hrr-algebra-numpy-preflight.md`: make the dependency core, assert the module's availability flag (e.g. `_HAS_NUMPY`), execute a small real operation (e.g. `hrr.encode_text(..., 32)`), record metadata/report fields, and add structural tests. If the active gateway imported the module before installing the dependency, restart/fresh process is required because availability flags may be cached at import time.

### 1. Implement check function

Location: `scripts/hermes_release_preflight.py`, after the previous check section.

```python
# ---------------------------------------------------------------------------
# <Check name> (R##X-#) — read-only
# ---------------------------------------------------------------------------

def check_<name>(hermes_home: Path, results: dict, errors: list,
                 <extra_params>):
    """<Docstring: what it checks, what it never modifies>."""
    warnings: list[str] = []
    # Initialize ALL result fields to defaults
    results["field_name"] = default_value
    # ... check logic ...
    # Append to errors for FAIL conditions
    # Append to warnings for WARN conditions
    # Merge warnings into state_files_warnings
    if warnings:
        results["state_files_warnings"] = results.get("state_files_warnings", []) + warnings
```

Key rules:
- **Never** modify, create, delete, restart, or signal anything
- **Never** print secrets or full file contents
- Initialize ALL result fields with defaults before branching
- Classify results as PASS / WARN / FAIL explicitly
- Append to `errors` only for release-critical failures
- Append to `warnings` for non-blocking issues

**Time-bounded checks (for log scanning)**: If the check scans logs or time-series data, add a `since_minutes` parameter (default 30), expose it as `--logs-since-minutes` in `parse_args()`, and thread it through `main()` → `check()` → `check_<name>()`. Parse timestamps to classify lines as **fresh** (within window, can cause FAIL), **historical** (outside window, counted but non-blocking), or **unparsed** (no recognizable timestamp, non-blocking). Thread the parameter explicitly — don't use `getattr(args, ...)` hacks.

### 2. Call in `check()`

Add after the previous check call:

```python
    # --- R##X-#: <Check name> (read-only) ---
    check_<name>(hermes_home, results, errors)
```

### 3. Add metadata fields

In the `metadata = { ... }` dict inside `check()`, add:

```python
        # R##X-# fields: <Check name>
        "field_name": results.get("field_name"),
```

### 4. Add report labels

In the `labels` list inside `report()`:

```python
        ("XX. <Label>", lambda r: <format expression>),
```

Use `lambda r:` for computed display values; plain string keys for direct fields.

### 5. Add report notes section

After existing notes sections, add a block for printing additional detail:

```python
    # R##X-#: Print <check> notes
    <check>_notes = results.get("<check>_notes", [])
    if <check>_notes:
        print(f"\n  <CHECK> NOTES:")
        for note in <check>_notes:
            print(f"    - {note}")
```

### 6. Update docstring

Add a line to the module docstring summarizing the new check category.

### 7. Update docs

Edit `docs/hermes-release-preflight.md`:
- Add numbered item in "What it does" section
- Add fields in `release_metadata.json` section
- Add troubleshooting entries for common failures
- Add to "What it does NOT do" and "Safety guarantees" if relevant

### 8. Add/extend tests

Edit `tests/test_hermes_release_preflight.py`:
- Update the module docstring to include the new test range
- Add structural tests (function exists, patterns exist, read-only verification)
- Add safety tests (no mutation, no systemctl, no symlink switch)
- Add metadata field presence tests
- Add classification logic tests (FAIL vs WARN vs PASS)
- If checking logs: test tail/limit behavior, missing-file-is-warning, sanitized output

### 9. Validate

```bash
pytest tests/test_hermes_release_preflight.py -q
pytest tests/tools/test_skills_sync_release_dir.py -q
python scripts/hermes_release_preflight.py \
  --repo <repo-path> --hermes-home /home/konstantin/.hermes \
  --extras messaging --replace-rc --allow-dirty
```

### 10. Commit and push

```bash
git add scripts/hermes_release_preflight.py docs/hermes-release-preflight.md tests/test_hermes_release_preflight.py
git commit -m "Add Hermes <check name> preflight checks (R##X-#)"
git push origin <branch>
```

## Changing Existing Check Policy (WARN → FAIL)

When promoting an existing check from WARN to FAIL (e.g., "missing file was a warning, now it's release-critical"):

1. **Change the append target**: `warnings.append("…missing (warning)")` → `errors.append("…missing — required state file")`. Update the message to be unambiguous about severity.
2. **Update the docstring**: Change "Missing files ⇒ warning" to "Missing ⇒ FAIL (release-critical)" and add a recovery note ("recovery/initialization is a separate manual task").
3. **Add a `_status` metadata field**: If the check only had a boolean `_ok` field, add a `_status` string field (PASS/FAIL) for human-readable reports. Set it alongside the boolean: `results["state_files_status"] = "PASS" if results["state_files_ok"] else "FAIL"`.
4. **Remove local warnings list only if the function is the sole contributor**: If other checks append to the same warnings accumulator (e.g., `state_files_warnings`), keep the accumulator as a results dict field but stop populating it from the promoted check. Removing it breaks downstream report printing.
5. **Update labels**: Change report labels from `yes/no` lambdas to `_status`-based ones when you add a status field. E.g., `"AS. State files OK", lambda r: "yes" if r.get("state_files_ok") else "no"` → `"AS. State files status", lambda r: r.get("state_files_status", "FAIL")`.
6. **Update notes section**: Remove any "missing files are OK" or "warnings, not errors" wording from the report notes print block.
7. **Update docs**: Change "Missing ⇒ warning" to "Missing ⇒ FAIL (release-critical)". Add troubleshooting entry for the new FAIL condition. Update metadata fields, "What it does NOT do", and Safety guarantees.
8. **Update tests**: Rename test functions from `_is_warning` to `_fails`. Change assertions from warning-pattern strings to FAIL-pattern strings (e.g., `"required state file" in src`). Add a `state_files_status` metadata field presence test. Add source-level tests verifying `errors.append` is used — NOT functional tests that run `_run_preflight` with a minimal hermes_home (those fail with exit code 1 from other unrelated checks, not exit code 2).

## Pitfalls

- **Dependency presence is not enough for silent degradation paths**: If a missing dependency causes fallback behavior rather than an import crash, add a behavioral assertion. For HRR/fact_store, `numpy` absence makes `probe`/`reason`/`related` fall back to FTS. Preflight should check `import numpy`, `pip show numpy`, `hrr._HAS_NUMPY`, and `hrr.encode_text(..., 32)`. Runtime verification can distinguish HRR from fallback because fallback `search()` results include `fts_rank`, while HRR-only `probe`/`related`/`reason` results do not. See `references/hrr-algebra-numpy-preflight.md`.
- **Gateway restart after installing dependency into active venv**: Modules may cache availability flags at import time. For HRR, installing numpy into the venv does not guarantee the already-running gateway sees it; restart/fresh process after install before declaring live `fact_store` fixed.
- **Vector rebuild is operational, not preflight**: After enabling numpy in active runtime, rebuild `memory_store.db` HRR vectors if some facts lack `hrr_vector`. Keep release preflight read-only: it may check integrity/counts/imports but must not mutate or repair the DB.
- **Deleted test file**: After RC builds or git operations, `tests/test_hermes_release_preflight.py` can disappear from the working tree (`git status` shows `D`). **Always** restore with `git checkout HEAD -- tests/test_hermes_release_preflight.py` before editing.
- **Dirty repo**: Untracked files (skill references, etc.) and the `tinker-atropos` deletion make the repo persistently dirty. Use `--allow-dirty` for preflight runs; only clean-tree commits pass without it.
- **Disk space**: RC builds need ~300MB venv + ~100MB cache. With multiple old RCs, disk fills fast. Before running full preflight, check `df -h /` and remove old non-production RCs.
- **Test assertions about source**: Old tests asserting `"config.yaml" not in src` break when new read-only checks reference those strings. Replace with read-only verification (no `write_text`, no `open(`, no `INSERT/UPDATE/DELETE`).
- **Function boundary extraction in tests**: Use `src.find("\ndef ", idx + 1)` (literal newline + `def`) to extract function bodies for scope-limited assertions. This avoids false positives from other functions.
- **Passive log checks scanning historical errors**: Use time-bounded parsing (`--logs-since-minutes`, default 30). Only **fresh** lines (within the window) cause FAIL; historical lines are counted in `agent_log_historical_critical_ignored_count` but never block release. Lines without parseable timestamps are also non-blocking. This prevents stale errors from months-old logs from failing the preflight.
- **Test false-positive: `" start "` matching comments/docstrings**: When testing that the script doesn't contain mutating systemctl commands, use `"systemctl start"` not `" start "` — the bare `" start "` matches `"at the start of the line"` and `"preflight start"` in comments. Always scope forbidden-pattern tests to the actual command context.
- **Test false-positive: `truncate`/`write_text` matching docstrings**: When scanning function bodies for forbidden operations like `truncate` or `write_text`, strip docstrings first (`re.sub(r'""".*?"""', '', func, flags=re.DOTALL)`) — the word "truncate" appears in docstrings like "never modifies, restarts, or truncates logs".
- **Test reference to `DOCS` constant**: The test file does NOT define a `DOCS` constant. Use `SCRIPT.parent.parent / "docs" / "hermes-release-preflight.md"` (same pattern as other doc tests in the file).
- **CLI arg threading**: When adding a new CLI argument that a check function needs, thread it through `parse_args()` → `main()` → `check(<existing_params>, new_param=default)` → `check_<name>(<params>, new_param)`. Don't use `getattr(args, ...)` hacks — add the parameter to `check()` explicitly.
- **`git checkout HEAD -- tests/` before edits**: The test file frequently disappears from the working tree after RC builds. Run `git checkout HEAD -- tests/test_hermes_release_preflight.py` as the FIRST step before any test edits.
- **`git checkout HEAD -- <file>` discards uncommitted patches**: After running full preflight (which triggers `git archive` / venv builds), the test file often disappears from the working tree. `git checkout HEAD -- <file>` restores it to the HEAD version — which **wipes any uncommitted patches you applied**. If you patched the test file in the working tree, you must re-apply those patches AFTER the checkout. The safe pattern is: (1) checkout HEAD, (2) re-apply all patches, (3) verify with `grep`, (4) then `git add`.
- **`git restore` vs `git submodule update` for deletions**: Adeleted tracked file like `tests/…` is restored with `git restore <file>` or `git checkout HEAD -- <file>`. But a deleted **submodule** (git mode 160000 like `tinker-atropos`) requires `git submodule update --init <path>` — `git restore` only restores the pointer, not the content. Always check `git ls-tree HEAD <path>`: mode `160000` means submodule.
- **Submodule `tinker-atropos` disappears from working tree**: After `git checkout`, `git pull`, or RC build operations, the `tinker-atropos` submodule directory vanishes (shows as `D` in `git status`). `git restore` alone does NOT fix submodules (mode 160000). Always run `git submodule update --init` after checkout to restore it. Without this the repo stays dirty and `--allow-dirty` masks the real problem.
- **Old RC cleanup before preflight runs**: Before running full preflight (`--replace-rc`), check `df -h /` and `du -sh` existing RCs. Identify the production target: `readlink ~/.hermes/hermes-agent`. Then remove old non-production RCs: `rm -rf ~/.hermes/releases/hermes-agent-<old-hash>`. Each RC needs ~300MB venv + ~100MB cache. Near-full disks (< 500MB free) will cause venv creation to fail silently or incompletely.
- **Patch tool f-string escaping**: When using the `patch` tool on Python code containing f-strings with curly braces (e.g., `f"contains {bad}"`), the tool can double-escape quotes and produce invalid Python (`f\"contains {bad}\"`). Always verify the patched file compiles — either check the linter output from the patch result, or run `python -c "import ast; ast.parse(open('file').read())"` immediately after patching Python files. If the linter reports a SyntaxError, re-read the affected lines and apply a corrective patch.
- **Functional vs source-level tests for FAIL conditions**: When a preflight check is promoted to FAIL and you want to test that overall preflight fails, a functional test using `_run_preflight()` with a minimal hermes_home will likely exit with code 1 (fatal config error from missing config.yaml, .env, etc.) rather than code 2 (preflight FAIL). Source-level tests (asserting `errors.append` pattern, metadata fields, `_status` values) are more reliable for policy assertions. Only use functional FAIL tests with a **fully populated** hermes_home that passes all other checks.
- **Appending test content via `cat >>` heredoc**: When appending test functions to the test file, avoid using `cat >> file << 'EOF'` with Python code that contains triple-quoted docstrings or `re.sub(r'"""..."""')`  — the heredoc delimiter collides with Python string syntax. Instead, use `write_file` to write the new tests to a temp file, then `terminal("cat /tmp/tests_append.py >> target_file")` — this avoids quoting issues entirely. After appending, verify with `wc -l` that the line count changed as expected.
- **Release readiness audit before switch script**: Before creating a switch script (R14E+), run a structured audit: (1) compare runtime vs bundled skill counts, (2) verify key custom skills exist at runtime, (3) classify all untracked files as must-track / reference-only / needs-decision, (4) verify untracked files don't appear in RC, (5) verify state files don't leak into RC. See `references/release-readiness-audit.md` for the full pattern.
- **`sync_skills()` is runtime-first**: The `sync_skills()` function reads from `~/.hermes/skills/` first (runtime, writable), then falls back to bundled skills in the RC. This means custom (non-bundled) skills like `hermes-preflight-extension` and `holographic-memory-hygiene` must already exist at runtime — they won't be synced from the repo. Untracked reference files in `skills/*/references/` are repo-local context only; they don't appear in the RC and aren't synced.
- **Variable-name false-positive with `symlink_to`**: Existing safety tests use `"symlink_to" not in src` to catch `Path.symlink_to()` calls that would switch the production symlink. But variable names containing `symlink_to` (e.g., `skills_is_symlink_to_release`) trigger these tests as false positives. **Always use naming like `skills_dir_points_to_release`** or `skills_symlink_points_at_release` for boolean variables that detect symlinks, never `is_symlink_to_*`.
- **Results dict key naming must match report labels**: The `report()` function reads from `results` dict via `results.get(key, "?")`. If you set `results["runtime_skills_count"]` in your check but the report label references `"skills_ambiguity_runtime_skills_count"`, the report prints `?`. **Use the same prefixed key name in both `results[]` assignments and report labels.** Don't split into short internal names (`runtime_skills_count`) and long metadata names (`skills_ambiguity_runtime_skills_count`) — `report()` reads from `results`, not from `metadata`.
- **Docstring false-positives in source-level tests**: When tests scan function source for forbidden patterns (e.g., `"reset"`, `"sync_skills"`, `"skills inspect"`), prohibition notes inside docstrings trigger false positives. Always extract the function body *after* the closing triple-quote of the docstring before scanning: `ds_end = func_src.find('"""', func_src.find('"""') + 3); body = func_src[ds_end + 3:]`. This is critical for `check_skills_source_ambiguity()` and any check whose docstring mentions what it must NOT do.
- **Commit deletions before `--allow-dirty` preflight**: When removing a bundled skill from repo with `git rm -r skills/<path>`, you MUST commit before running preflight with `--allow-dirty`. Otherwise `git archive` in the RC build still picks up the old tracked files, and your new check (e.g., "RC must not contain flight-search") will FAIL on the freshly-built RC. Pattern: (1) `git rm`, (2) `git add + commit`, (3) `git push`, (4) then run preflight.
- **Source-of-truth checks for custom skills**: For a single skill, use `check_<skill>_source_of_truth()` (flight-search pattern). For all skills at once, use the generalized `check_skills_source_ambiguity()` (R14D-4c pattern). Both verify: (a) runtime skill exists at `~/.hermes/skills/<category>/<name>/SKILL.md`, (b) repo bundled copy does NOT exist, (c) RC copy does NOT exist. The generalized version also checks `.bundled_manifest` for legacy entries (WARN, not FAIL) and detects `~/.hermes/skills` symlinked to release. See `references/skills-source-ambiguity.md` for full details.
- **Fork-only skills detected via upstream snapshot (R14D-5b2)**: `check_fork_only_skills_policy()` uses `ops/upstream-bundled-skills.txt` (generated from `upstream/main`) as the canonical list of upstream-bundled skill IDs. Skills in repo/RC but NOT in this snapshot are fork-only → FAIL. Skills in `~/.hermes/skills/` but not in snapshot are runtime-only → OK. The hardcoded `FORK_ONLY_SKILLS` list was removed in R14D-5b2. To update the snapshot: `git fetch upstream && git ls-tree -r --name-only upstream/main skills | grep '/SKILL.md$' | sed 's#^skills/##; s#/SKILL.md$##' | sort > ops/upstream-bundled-skills.txt`. Update the snapshot intentionally only when rebasing/updating upstream skills.
- **Missing/empty upstream snapshot causes FAIL**: If `ops/upstream-bundled-skills.txt` is missing or empty, `check_fork_only_skills_policy()` FAILS because it cannot determine which skills are upstream-bundled vs fork-only. This prevents silent misclassification when the snapshot is accidentally deleted.
- **Fork-only preflight FAIL is expected before de-bundle**: After adding `check_fork_only_skills_policy()`, the full preflight will FAIL because fork-only skills are still in `repo/skills/` and get synced into the RC. This is the correct result — the FAIL status will resolve after R14D-5c de-bundle removes them from `repo/skills/`. Do NOT weaken the check to WARN to avoid the FAIL.
- **Testing standalone scripts with `importlib`**: When writing tests for standalone Python scripts (like `hermes_release_cleanup.py`), don't try `from hermes_release_cleanup import ...` — the script isn't on `sys.path`. Use `importlib.util.spec_from_file_location("module_name", str(SCRIPT))`, then `importlib.util.module_from_spec(spec)` and `spec.loader.exec_module(mod)`. This lets you call functions directly (`mod.run_cleanup(...)`) without subprocess overhead. Still add CLI-level tests using `subprocess.run([sys.executable, str(SCRIPT), ...])` for integration coverage.
- **Argparse assertion quoting**: When asserting `argparse` patterns exist in source code, match the exact quoting convention used in the script. Hermes scripts use double-quoted argparse arguments: `action="store_true"`, `default=False`. Test assertions must use the same quoting: `assert 'action="store_true"' in src`, NOT `assert "action='store_true'" in src` (which fails because Python scripts use double quotes).
- **De-bundle procedure for runtime-only skills**: When removing fork-only skills from `repo/skills/`, always (1) verify runtime copies exist in `~/.hermes/skills/`, (2) backup to `~/.hermes/skill-backups/`, (3) `git rm -r skills/<category>/<name>`, (4) commit and push BEFORE running preflight (so RC is built from the new commit), (5) run full preflight — expect FAIL while other fork-only skills remain. See `references/de-bundle-runtime-only-skills.md`.
- **`git add -u <path>` after `git rm` fails**: After `git rm -r`, the deletion is already staged. `git add -u <path>` produces "pathspec did not match any files" because the path no longer exists in the working tree. Just `git commit` directly — the staged deletion is already in the index.
- **Untracked skills can't be git-rm'd**: If `git ls-files skills/<path>` returns empty output, the skill directory exists only as untracked working-tree files. It cannot be removed with `git rm` and won't appear in `git diff --cached`. It also won't appear in the RC (since `git archive` only includes tracked files). Note it in the commit message as "untracked, not git-rm'd". The preflight check for repo fork-only uses `git ls-tree` (tracked files only), so untracked fork-only skills appear in BQ14 but not in BQ15 (RC).
- **Multiple backup dirs from typos**: When running `cp -a` with shell variable expansion, a typo (e.g., `/home/konstatin/` instead of `/home/konstantin/`) silently creates a partial backup in a different directory. Always verify all backup SKILL.md files after the `cp -a` command. Merge partial backups with `cp -a <partial-backup>/<skill> <final-backup>/`.
- **Test file `D` status in git**: After RC builds or git operations, `tests/test_hermes_release_preflight.py` frequently shows as `D` (deleted) in `git status`. This is not a real deletion — `git restore` recovers it. Always verify with `git status --short` before starting work.
- **`import re` missing for module-level `re.compile` constants**: When adding regex constants at module level (e.g., `_CLEANUP_COMMAND_INDICATORS = re.compile(...)`), the constant is evaluated at import time. If `import re` is only inside a function or missing entirely, you get `NameError: name 're' is not defined` at import time — **every** test that runs the script via subprocess fails, not just the new test. Always verify top-level imports after adding module-level regex constants. Run `python -c "import <module>"` or the full test suite immediately after patching.
- **Cleanup command false positives in passive logs**: Journald and agent.log lines that are shell command echoes (`sudo rm -rf /tmp/hermes-tool-output...`, `/bin/bash -c ...`, `grep -Ei ...`, `journalctl ... grep ...`, `(command continued)`) match critical patterns as text arguments, not runtime errors. Add `_is_cleanup_command_line()` classifier and filter lines BEFORE `_scan_lines_for_patterns()`. See `references/cleanup-command-false-positive-classifier.md` for full implementation pattern, metadata fields, and test patterns.

## References

- `references/time-bounded-log-parsing.md` — Log timestamp formats, fresh/historical/unparsed classification, and test pitfalls
- `references/state-files-required-policy.md` — R14D-1b policy change: state files are required (WARN→FAIL), implementation pattern, test pattern, recovery
- `references/release-readiness-audit.md` — R14D-4a release readiness audit pattern: runtime vs bundled skills, untracked file classification, RC verification, switch script checklist
- `references/flight-search-source-of-truth.md` — R14D-4b de-bundling pattern: removing a runtime skill from repo, source-of-truth check implementation, commit-before-preflight ordering, variable naming pitfall
- `references/skills-source-ambiguity.md` — R14D-4c generalized skills source ambiguity: `check_skills_source_ambiguity()` implementation, helper functions, metadata fields, policy, test patterns, docstring-extraction pitfall
- `references/fork-only-skills-policy.md` — R14D-5b2 fork-only skills release policy: `check_fork_only_skills_policy()` implementation, upstream snapshot detection, metadata fields, expected FAIL before de-bundle
- `references/de-bundle-runtime-only-skills.md` — R14D-5c de-bundle procedure: removing fork-only skills from repo while preserving runtime copies, backup pattern, commit-before-preflight ordering
- `references/cleanup-command-false-positive-classifier.md` — R14D-5e: cleanup command false positive classifier in passive logs, `_is_cleanup_command_line()` pattern, metadata fields, `import re` pitfall, test patterns
- `references/rc-cleanup.md` — R14-RC-CLEAN-1 release candidate cleanup: safe RC deletion script, safety guarantees, importlib test pattern, disk-space workflow

## Safety Guardrails

These are **never** to be violated in preflight code:

- No `systemctl start/stop/restart/enable/disable`
- No symlink creation/switching (`os.symlink`, `Path.symlink_to`)
- No file modification (`write_text`, `write_bytes`, `.write(`, `os.remove`, `shutil.rmtree`)
- No DB modification (`INSERT`, `UPDATE`, `DELETE`, `VACUUM`)
- No printing of secrets (API keys, tokens, passwords)
- No log truncation, rotation, or gateway restart