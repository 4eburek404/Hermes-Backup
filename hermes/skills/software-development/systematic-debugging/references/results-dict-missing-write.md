# Results Dict Missing Write: Local Variable Never Stored

## Symptom

A metadata or results dictionary field returns `None` via `results.get(key)` even though the code clearly sets the corresponding local variable to `True` or `False` in the success branch. The value exists in local scope but was never stored in the dict.

## Root Cause

Code sets a local variable inside a conditional (success path) but only writes it to the results dict in a different branch (failure/else path). The success branch writes *other* keys to results but skips this one. At read time, `results.get(key)` returns `None` (default) because the key was never inserted.

### Example (from hermes_release_preflight.py)

```python
# Success branch (inside `if ok:` block)
skills_bundled_source_resolves_to_rc = False
for d in skills_dirs:
    if d == rc_skills_str or Path(d).resolve() == rc_skills_resolved:
        skills_bundled_source_present = True
        skills_bundled_source_resolves_to_rc = True
        break
results["skills_bundled_source_present"] = skills_bundled_source_present
# ↑ present is written, but resolves_to_rc is NOT written here!

# Failure branch (else block)
results["skills_bundled_source_resolves_to_rc"] = False  # ← only written in else
```

Later:
```python
metadata["skills_bundled_source_resolves_to_rc"] = results.get("skills_bundled_source_resolves_to_rc")
# ↑ None when success path was taken
```

## Fix

Add the missing write immediately after the matching one:

```python
results["skills_bundled_source_present"] = skills_bundled_source_present
results["skills_bundled_source_resolves_to_rc"] = skills_bundled_source_resolves_to_rc
```

## Detection Pattern

When auditing code with results/metadata dicts:

1. Grep for all local variable assignments inside conditional blocks: `var_name = True/False`
2. For each, verify a matching `results["var_name"] = var_name` exists in the **same** branch
3. Diff success and failure branches — every variable set in one must be written in both
4. Pay special attention when the failure branch has a full set of `results[key] = value` lines: it's common to write all keys in the "error/reporting" path but miss one in the "silent success" path

## Why This Is Hard to Catch in Tests

- The success path *works* for everything except the missing metadata field
- If no test checks for `None` vs `False` in metadata, the bug passes silently
- The `results.get()` pattern hides the absence (returns `None` instead of `KeyError`)

## Verification

```bash
# Check that dict gets all expected keys in every branch
grep -n 'results\["' script.py | sort > /tmp/dict_writes.txt
grep -n 'some_var = ' script.py | sort > /tmp/var_assigns.txt
# Cross-reference: every var_assign should have a matching dict_write in the same scope
```

## Session Provenance

Discovered during R14C-3 recovery of Hermes release preflight. The field `skills_bundled_source_resolves_to_rc` was `None` in `release_metadata.json`. Root cause: line 362 set the local variable to `True` inside the success loop, but line 365 only wrote `skills_bundled_source_present` to results. The else branch (line 385) wrote both. Fix: one-line addition at line 365.

Commit: `abcbf1df0` on `context-input-baseline` in `hermes-agent.pre_r12a_messagingfix_20260512051431`.