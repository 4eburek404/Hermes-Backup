# Post-debug report checklist

Use this after investigation, patching, or a no-fix verification pass.

Include only grounded facts:
- Changed files: list exact paths; say "none" if read-only.
- Verification: exact commands run and pass/fail result.
- Coverage: what was tested, and what was *not* tested.
- Out-of-scope items: explicitly name nearby components left untouched.
- Risk/rollback: whether rollback is needed, and why.
- If no code changed, say so clearly instead of implying a fix.

Preferred shape:
1. Branch / commit context
2. Changed files
3. Tests or checks run
4. Out-of-scope / untouched areas
5. Recommendation: proceed / rollback / needs more investigation

## Read-only audit addendum

Use this when the task is inspection-only or a rollback verification pass:
- State whether the result is read-only / no-op.
- Include the exact live repo snapshot used to judge state.
- If a prior summary conflicts with live status, trust the live status and say so.
- If a file was temporarily deleted and later restored, mention the final live state instead of the transient one.
