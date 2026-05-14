# Check-attribution AUTHOR_MAP failures

Use when a PR's `check-attribution` workflow fails with `New contributor email(s) not in AUTHOR_MAP`.

## Signal

GitHub Actions log shows a failing step similar to:

```text
New contributor email(s) not in AUTHOR_MAP:
  user@example.com (github-login)
Please add mappings to scripts/release.py AUTHOR_MAP:
    "user@example.com": "<github-username>",
```

## Fix pattern

1. Read the failed log first:

```bash
gh run view <RUN_ID> --repo <owner/repo> --log-failed
```

2. Add the exact mapping requested by CI to `scripts/release.py` inside `AUTHOR_MAP`:

```python
"user@example.com": "github-login",
```

3. Verify locally before commit:

```bash
python3 -m py_compile scripts/release.py
MERGE_BASE=$(git merge-base origin/main HEAD)
NEW_EMAILS=$(git log ${MERGE_BASE}..HEAD --format='%ae' --no-merges | sort -u)
while IFS= read -r email; do
  [ -z "$email" ] && continue
  case "$email" in
    *teknium*|*noreply@github.com*|*dependabot*|*github-actions*|*anthropic.com*|*cursor.com*) continue ;;
  esac
  if echo "$email" | grep -qP '\+.*@users\.noreply\.github\.com'; then continue; fi
  grep -qF "\"${email}\"" scripts/release.py || { echo "missing $email"; exit 1; }
done <<< "$NEW_EMAILS"
```

4. Stage only `scripts/release.py`, run `git diff --cached --check` and a staged secret scan, commit, push, then re-check PR checks.

## Pitfalls

- Do not treat this as a test-suite failure; the root cause is contributor metadata required by release tooling.
- In a dirty worktree, stage only `scripts/release.py`; do not include unrelated local skill/doc edits.
- Do not print credential material from `gh auth status`; redact tokens if logging auth diagnostics.
