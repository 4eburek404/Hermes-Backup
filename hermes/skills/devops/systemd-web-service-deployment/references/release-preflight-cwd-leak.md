# Release Preflight CWD Leak with --system-site-packages

## Problem

When a release preflight script creates a venv with `--system-site-packages` and
runs Python subprocesses without setting `cwd`, the calling script's CWD leaks
into `sys.path[0]`. Modules are then imported from the repo checkout directory
instead of the venv's installed package, breaking path-resolution functions.

## Reproduction

```bash
# Running from repo checkout CWD:
cd /home/konstantin/.hermes/hermes-agent.pre_r12a_messagingfix_20260512051431
/home/konstantin/.hermes/releases/hermes-agent-ABC/venv/bin/python -c \
  "import hermes_constants; print(hermes_constants.__file__)"

# Output (WRONG — imports from repo checkout):
# /home/konstantin/.hermes/hermes-agent.pre_r12a_messagingfix_20260512051431/hermes_constants.py

# Running from neutral CWD:
cd /tmp
/home/konstantin/.hermes/releases/hermes-agent-ABC/venv/bin/python -c \
  "import hermes_constants; print(hermes_constants.__file__)"

# Output (CORRECT — imports from venv site-packages):
# /home/konstantin/.hermes/releases/hermes-agent-ABC/venv/lib/python3.11/site-packages/hermes_constants.py
```

Python adds `''` (CWD) to `sys.path[0]`. When the CWD is the repo checkout,
`hermes_constants.py` in the repo root shadows the installed package copy.
With `--system-site-packages`, the production venv's editable `.pth` finder may
also inject the repo checkout into the module search path.

## Impact

- `get_skills_dir()` → `Path(__file__).resolve().parent / "skills"` returns
  `repo_checkout/skills` instead of `rc_dir/skills` or `site-packages/skills`
- `get_all_skills_dirs()` returns `[state_dir, repo_checkout/skills]` instead
  of `[state_dir, rc_dir/skills]`
- Preflight FAIL: "bundled source does not resolve to RC/skills"

## Fix

Pass `cwd=rc_dir` to all subprocess calls that invoke the RC venv's Python:

```python
rc_cwd = str(rc_dir)  # simulate production WorkingDirectory

# Import checks
run_okfail([str(python), "-c", code], cwd=rc_cwd)

# Skills architecture checks
run_okfail([str(python), "-c", "from agent.skill_utils import get_all_skills_dirs\n..."], cwd=rc_cwd)
run_okfail([str(python), "-c", "from tools.skills_sync import sync_skills\n..."], cwd=rc_cwd)

# CLI checks
run_okfail([str(hermes), "skills", "list"], cwd=rc_cwd)
run_okfail([str(hermes), "--help"], cwd=rc_cwd)
```

## Import Provenance Check

Add an explicit check that `hermes_constants.__file__` resolves under the RC
path, not from the repo checkout or another release:

```python
ok_prov, out_prov = run_okfail([
    str(python), "-c",
    "import hermes_constants\n"
    "from pathlib import Path\n"
    "print(Path(hermes_constants.__file__).resolve())\n",
], cwd=rc_cwd)

hermes_constants_file = out_prov.strip().splitlines()[-1].strip()
try:
    Path(hermes_constants_file).relative_to(rc_dir.resolve())
    hermes_constants_under_rc = True
except ValueError:
    hermes_constants_under_rc = False

if not hermes_constants_under_rc:
    errors.append(f"hermes_constants imported from outside RC: {hermes_constants_file}")
```

## Why Not cwd="/tmp"?

Using `cwd="/tmp"` avoids the CWD leak but does not simulate the production
runtime environment where `WorkingDirectory` is the release directory (via
symlink). Using `cwd=rc_dir` is correct because:

1. It matches what `systemd` sets as `WorkingDirectory` in production
2. It verifies that the RC's installed packages resolve correctly when CWD
   is the release directory (not just from a neutral location)
3. It catches the exact scenario: "after switching the production symlink to
   this release, will imports resolve from the right location?"

A `/tmp`-based site-packages-only mode is a separate future
packaging-hardening task that verifies import isolation regardless of CWD,
but that's a stricter check than the production deployment requires.

## Session Provenance

R14C-2 (2026-05-12): Discovered when `get_all_skills_dirs()` returned
`[~/.hermes/skills, repo_checkout/skills]` instead of
`[~/.hermes/skills, rc_dir/skills]`. The `--system-site-packages` venv
inherited an editable `.pth` finder from the production venv, which mapped
`hermes_constants` to the repo checkout path. The CWD leak compounded this
because Python adds `""` to `sys.path[0]`.

Fix: added `cwd=rc_dir` to all RC subprocess calls plus import provenance
check. Preflight PASS confirmed with `hermes_constants_under_rc: true`
and `skills_bundled_source_present: true`.