# Python subprocess CWD Leak: Module Resolution Shadow

## Symptom

Inside a script at `/repo/`, `subprocess.run([venv_python, "-c", "import mymod"])`
imports `mymod` from `/repo/mymod.py` (the checkout) instead of from the venv's
`site-packages/mymod.py`. The installed copy in the venv is silently ignored.

## Root Cause

`subprocess.run()` inherits the caller's CWD by default. Python inserts `""`
(current directory) as the **first** entry of `sys.path`. If the CWD contains a
module matching the import target, Python finds it before site-packages.

```
CWD = /repo/checkout
sys.path = ["", "/venv/lib/site-packages", ...]
# "" resolves to CWD → /repo/checkout/mymod.py wins
```

## Verification

```bash
# Broken (CWD = repo checkout):
cd /repo && /venv/bin/python -c "import mymod; print(mymod.__file__)"
# → /repo/mymod.py

# Fixed (CWD = neutral dir):
cd /tmp && /venv/bin/python -c "import mymod; print(mymod.__file__)"
# → /venv/lib/site-packages/mymod.py
```

## Fix

Pass an explicit `cwd` to `subprocess.run()` that is NOT the repo checkout:

```python
# Before (leaks CWD):
subprocess.run([venv_python, "-c", code], capture_output=True, text=True)

# After (neutral CWD):
subprocess.run([venv_python, "-c", code], capture_output=True, text=True, cwd="/tmp")
```

Or use `cwd=str(Path(tmpdir))` for a temp directory if `/tmp` might not exist.

## Aggravating Factor: Venv Chaining

When a venv is created from *another venv's* Python with `--system-site-packages`,
the new venv inherits the parent venv's editable `.pth` finders. If the parent has
an editable install (e.g. `__editable__.pkg-0.13.0.pth` with a custom MetaPathFinder),
the child venv's Python may resolve modules via the parent's editable MAPPING
dictionary, pointing to paths in the *parent's* release directory.

```bash
# Parent venv has editable finder mapping hermes_constants → /releases/hermes-agent-abc/
# Child venv created from that Python inherits the finder via system-site-packages
```

This makes CWD leak even harder to diagnose because module resolution follows two
unexpected paths instead of one.

## Diagnostic Checklist

When a subprocess import resolves to the wrong file:

1. Check `mymod.__file__` — is it in repo checkout or venv site-packages?
2. Check CWD of the subprocess — does it contain a matching module?
3. Check `sys.path[0]` — is it `""` or an explicit path?
4. Check for editable `.pth` finders inherited via `--system-site-packages`:
   ```bash
   find /venv/lib/site-packages -name "__editable__*" -o -name "*.egg-link"
   ```
5. Verify with neutral CWD (`cd /tmp && python -c "import mymod; print(mymod.__file__)"`)

## Session Provenance

Discovered during R14C-2 Hermes release preflight: `get_skills_dir()` returned
the repo checkout path instead of the RC's bundled skills, causing preflight FAIL
on `skills_bundled_source_present`. The preflight script ran `subprocess.run()`
from the repo checkout CWD, and the RC venv Python inherited that CWD as `sys.path[0]`.