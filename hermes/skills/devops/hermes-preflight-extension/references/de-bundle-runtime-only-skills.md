# De-bundle Runtime-Only Skills from Repo (R14D-5c)

## Problem

Fork-only skills (not in upstream Hermes) that were placed in `repo/skills/` get synced into the RC during preflight, causing `check_fork_only_skills_policy()` to FAIL. These skills must be removed from `repo/skills/` while preserving their runtime copies in `~/.hermes/skills/`.

## Procedure

For each batch of fork-only skills to de-bundle:

### 1. Verify runtime copies exist

```bash
for skill_id in "category/name" "category/name2"; do
  test -f ~/.hermes/skills/$skill_id/SKILL.md && echo "OK: $skill_id" || echo "MISSING: $skill_id"
done
```

If ANY runtime copy is missing → **STOP**. Do not remove from repo.

### 2. Backup runtime copies

```bash
backup_root="$HOME/.hermes/skill-backups/r14d-5c-N-$(date +%Y%m%d%H%M%S)"
mkdir -p "$backup_root"
cp -a ~/.hermes/skills/<skill-name> "$backup_root/"
# Verify backup contains SKILL.md for each skill
```

### 3. Remove from repo with git rm

```bash
cd <repo>
git rm -r skills/<category>/<skill-name>
```

For **untracked** skills: check with `git ls-files skills/<category>/<skill-name>`. If empty output, the skill is untracked — no `git rm` needed, just note it in the commit message. Do NOT touch `~/.hermes/skills/`.

### 4. Verify tests still pass

```bash
pytest tests/test_hermes_release_preflight.py -q
pytest tests/tools/test_skills_sync_release_dir.py -q
pytest tests/test_hermes_release_cleanup.py -q
```

### 5. Commit and push

```bash
git commit -m "De-bundle runtime-only skills batch N"
git push origin <branch>
```

Note: After `git rm -r`, files are already staged. `git add -u <path>` will fail with "pathspec did not match any files" — just `git commit` directly.

### 6. Run full preflight (expect FAIL while other fork-only skills remain)

```bash
python scripts/hermes_release_preflight.py \
  --repo <repo-path> --hermes-home ~/.hermes \
  --extras messaging --replace-rc --allow-dirty \
  --logs-since-minutes 30
```

The preflight will still FAIL if other fork-only skills remain in repo/RC. This is expected.

### 7. Clean up old RCs if disk space is low

```bash
# Check disk
df -h /

# Dry-run
python scripts/hermes_release_cleanup.py --hermes-home ~/.hermes --keep-latest 2

# Execute
python scripts/hermes_release_cleanup.py --hermes-home ~/.hermes --keep-latest 2 --execute
```

RC builds need ~300MB venv each. Near-full disks cause silent build failures.

### 8. Verify final preflight PASS

After all fork-only skills are de-bundled and RC is rebuilt from the latest commit:
- `BQ14 repo fork-only skills` should show only untracked skills (or none)
- `BQ15 RC fork-only skills` should be **none**
- `BQ17 fork-only policy status` should be **PASS**

## Pitfalls

- **Disk space**: Before running full preflight with `--replace-rc`, check `df -h /`. Old RCs consume ~300MB venv each. Remove non-production RCs first using `hermes_release_cleanup.py`.
- **Untracked files after git rm**: After `git rm -r`, untracked files in `skills/<name>/references/` may remain in the working tree. These are NOT in the git index and won't be committed. Use `git status` to verify.
- **Untracked skills can't be git-rm'd**: If `git ls-files skills/<path>` returns nothing, the skill is untracked and cannot be removed with `git rm`. Note it in the commit message as "untracked, not git-rm'd".
- **Test file disappears after RC build**: `tests/test_hermes_release_preflight.py` can disappear from the working tree. Always `git restore tests/test_hermes_release_preflight.py` before editing.
- **RC from old commit contains de-bundled skills**: After de-bundling, the RC built by `--replace-rc` uses the current commit, so de-bundled skills won't appear. But if you run preflight before committing, the old commit's RC will still contain them. Always commit first, then run preflight.
- **`git add -u <path>` after `git rm`**: After `git rm -r`, the deletion is already staged. Running `git add -u <path>` produces "pathspec did not match any files" because the path is no longer in the working tree. Just `git commit` directly.
- **Multiple backup dirs from typos**: If `cp -a` fails mid-command (e.g., typo in path), multiple backup dirs may be created. Merge them manually: `cp -a <first-backup>/<skill> <final-backup>/`.

## History

- R14D-5c-1: Removed `software-development/skill-audit-and-improvement`, `devops/hermes-runtime-health-check`, `devops/systemd-web-service-deployment`. Backup at `~/.hermes/skill-backups/r14d-5c-1-20260513094834/`.
- R14D-5c-2: Removed `mlops/ollama`, `mlops/inference/outlines`, `mlops/training/axolotl`. Backup at `~/.hermes/skill-backups/r14d-5c-2-20260513102144/`.
- R14D-5c-3: Removed `mlops/training/trl-fine-tuning`, `mlops/training/unsloth`, `note-taking/knowledge-architecture`. Backup at `~/.hermes/skill-backups/r14d-5c-3-20260513102548/`.
- R14D-5c-4: Removed `productivity/hh-ru`, `research/web-content-acquisition`. `software-development/tool-output-summarization` was untracked (not in git), so no `git rm` needed. Backup at `~/.hermes/skill-backups/r14d-5c-4-20260513103058/`. This batch completed the de-bundle: preflight went from FAIL to **PASS**.