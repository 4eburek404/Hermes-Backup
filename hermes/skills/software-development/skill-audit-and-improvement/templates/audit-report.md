# Skill Audit Report Template

## Summary

- **Skill(s):** `<name>`
- **Request class:** `post-session learning | existing skill audit | new skill authoring | skill-owned CLI audit | source/runtime cleanup | distribution/custom inventory`
- **Branch/HEAD:** `<branch>` @ `<short-sha>`
- **Outcome:** `no change | patched | new reference | new template | new script | new CLI | new skill`

## Evidence Checked

- `git status --short --branch --untracked-files=all`: `<result>`
- Target diff before edit: `<clean | dirty, summarized>`
- Peer skills read: `<list>`
- Related skills loaded: `<list>`
- Runtime/source assumptions verified: `<yes/no + notes>`

## Findings

1. **Trigger clarity:** `<finding>`
2. **Executability:** `<finding>`
3. **Source/runtime correctness:** `<finding>`
4. **Safety/side effects:** `<finding>`
5. **Verification discipline:** `<finding>`
6. **Library architecture:** `<finding>`

## Changes Made

- `<path>` — `<why>`
- `<path>` — `<why>`

## Verification

Commands run:

```bash
<command>
```

Results:

- `<check>`: `<pass/fail>`
- `<check>`: `<pass/fail>`
- `secret/stale/unsafe-scan check`: `<pass/fail; findings redacted>`

## Remaining / Baseline Issues

- `<issue>` — `<why not fixed in this scope>`

## Commit / Rollback

Commit:

```bash
<sha> <message>
```

Rollback:

```bash
git revert <sha>
```
