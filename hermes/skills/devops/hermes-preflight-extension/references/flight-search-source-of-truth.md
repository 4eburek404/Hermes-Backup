# flight-search Source of Truth (R14D-4b)

## Problem

`productivity/flight-search` is a **runtime/user skill** — installed in `~/.hermes/skills/`, not shipped in `repo/skills/`. But it was present in `repo/skills/productivity/flight-search/`, which meant:

1. `git archive` copies it into every release candidate
2. The release becomes an unwanted second source of truth for the skill
3. Runtime skills must only live in `~/.hermes/skills/`

## Solution

### De-bundle from repo

```bash
git rm -r skills/productivity/flight-search
git add scripts/hermes_release_preflight.py docs/ tests/
git commit -m "Treat flight-search as runtime skill source of truth"
git push
# THEN run preflight — commit BEFORE preflight so git archive excludes it
```

### Preflight check: `check_flight_search_source_of_truth()`

Verifies 4 conditions:
1. **Runtime exists**: `~/.hermes/skills/productivity/flight-search/SKILL.md` must be present → missing = FAIL
2. **Repo bundled absent**: `<repo>/skills/productivity/flight-search/SKILL.md` must NOT exist → present = FAIL
3. **RC bundled absent**: `<RC>/skills/productivity/flight-search/SKILL.md` must NOT exist → present = FAIL
4. **Skills dir not symlinked to release**: `~/.hermes/skills` must NOT be a symlink pointing into `releases/`

Metadata: `flight_search_source_of_truth` = `"hermes_home_runtime"` | `"ambiguous"`

### Key pitfalls

- **Variable naming**: Use `skills_dir_points_to_release`, NOT `skills_is_symlink_to_release` — existing tests ban `"symlink_to"` in source to prevent `Path.symlink_to()` calls.
- **Commit order**: `git rm` must be committed BEFORE running preflight. With `--allow-dirty`, `git archive` still uses the committed tree, so uncommitted deletions don't affect the RC build.
- **Backup before de-bundle**: Copy runtime skill to `~/.hermes/skill-backups/flight-search-before-debundle-<timestamp>/` before any repo changes.

### Documentation

- `docs/hermes-skills-source-of-truth.md` — official model: `~/.hermes/skills/` is primary source of truth
- `docs/hermes-release-preflight.md` — added check #14 (flight-search source of truth)

### Tests (14 new: #123–136)

- 123: function exists
- 124–128: metadata fields present
- 129–132: error triggers (repo bundled, RC bundled, missing runtime, symlink to release)
- 133: `hermes skills inspect` NOT used for validation
- 134: no `sync_skills`/`reset`/`restore`/`install` calls
- 135: no production symlink switch
- 136: report labels present