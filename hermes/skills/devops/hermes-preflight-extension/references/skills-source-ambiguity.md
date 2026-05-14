# Skills Source Ambiguity (R14D-4c)

## Problem

After de-bundling `flight-search` in R14D-4b, the same ambiguity risk exists for **any** runtime-only skill. A runtime-only skill that also appears in `repo/skills/` or `RC/skills/` creates a duplicate active source of truth. The official model:

- `~/.hermes/skills/` = runtime source of truth for installed skills
- `release/skills` = bundled seed/update source only, NOT a second active runtime source

## Solution: `check_skills_source_ambiguity()`

Generalized check that replaces the flight-search-specific pattern for all skills.

### Helper functions

**`_collect_skill_ids(root: Path) -> set[str]`**
- Walks `root` with `SKILL.md` files via glob
- Converts relative paths to `category/name` IDs
- E.g., `productivity/flight-search/SKILL.md` → `productivity/flight-search`

**`_parse_bundled_manifest(manifest_path: Path) -> dict[str, str]`**
- Reads `.bundled_manifest` key=value format
- Maps flat keys (e.g., `flight-search`) to `category/name` format
- Only maps keys where the value or key structure disambiguates the category

### Main check logic

1. **Runtime dir exists**: `~/.hermes/skills/` must exist → missing = WARN (no custom skills)
2. **Runtime not symlinked to release**: `~/.hermes/skills` must NOT resolve into `releases/` → FAIL if symlink
3. **Collect skill IDs**: from runtime, repo, and RC directories
4. **Compute runtime-only**: `runtime_ids - repo_ids - rc_ids`
5. **Check runtime-only not in repo or RC**: → FAIL if duplicate active source found
6. **Check .bundled_manifest for legacy entries**: runtime-only skill in manifest → WARN (not FAIL, legacy cleanup is separate)
7. **Set metadata**: `skills_ambiguity_status` = PASS/FAIL, `skills_ambiguity_found` = bool

### Metadata fields

| Field | Type |
|---|---|
| `skills_ambiguity_runtime_exists` | bool |
| `skills_ambiguity_runtime_symlink_points_at_release` | bool |
| `skills_ambiguity_runtime_skills_count` | int |
| `skills_ambiguity_repo_bundled_skills_count` | int |
| `skills_ambiguity_rc_bundled_skills_count` | int |
| `skills_ambiguity_runtime_only_skills` | str (comma-separated) |
| `skills_ambiguity_found` | bool |
| `skills_ambiguity_manifest_legacy_entries` | str (comma-separated) |
| `skills_ambiguity_status` | PASS/FAIL |

### Report labels

BQ0–BQ8: runtime exists, symlink points at release, runtime count, repo count, RC count, runtime-only list, found flag, manifest legacy entries, status.

### Policy

- Duplicate active source → **FAIL**
- Manifest legacy entry → **WARN** (requires separate safe cleanup task)
- No duplicates → **PASS**

## Fork-local vs upstream bundled distinction

`check_skills_source_ambiguity()` compares runtime skills against `repo/skills/` and `RC/skills/`. In a fork, skills present in our fork's `repo/skills/` but absent from upstream pass as "bundled" — even though they're fork-local additions that should be runtime-only by provenance.

**Method to identify fork-only skills:**

1. Enumerate upstream skills via GitHub API:
   ```bash
   curl -sL "https://api.github.com/repos/NousResearch/hermes-agent/contents/skills" \
     | python3 -c "import json,sys; [print(d['name']) for d in json.load(sys.stdin) if d['type']=='dir']"
   ```
2. Drill into `mlops/` subcategories (evaluation, inference, models, research, training, vector-databases) separately.
3. Build full upstream set as `category/name` IDs.
4. Diff against fork repo skill IDs: `fork_skills - upstream_skills = fork-only`.

**Known fork-only skills (May 2026):**

| Skill | Category | Note |
|---|---|---|
| `devops/hermes-runtime-health-check` | devops | Fork-local runtime check |
| `devops/systemd-web-service-deployment` | devops | Fork-local ops skill |
| `gaming/minecraft-modpack-server` | gaming | Fork-local |
| `mlops/huggingface-hub` | mlops | Flat structure (upstream uses subcats) |
| `mlops/ollama` | mlops | Flat structure (upstream uses subcats) |
| `productivity/hh-ru` | productivity | Localized RU-market skill |
| `research/web-content-acquisition` | research | Fork-local research skill |
| `software-development/skill-audit-and-improvement` | dev | Fork-local meta-skill |
| `software-development/tool-output-summarization` | dev | Untracked SKILL.md in repo |

**Missing from fork (in upstream, not in our repo):** `apple/macos-computer-use`, `productivity/teams-meeting-pipeline`, and 7 mlops subcategorized skills (`mlops/evaluation/*`, `mlops/inference/*`, `mlops/models/*`, `mlops/research/*`).

**Now addressed by `check_fork_only_skills_policy()` (R14D-5b):** This function hardcodes the fork-only skills list and enforces that they must not appear in RC/skills and must exist in runtime. It complements `check_skills_source_ambiguity()` which only checks runtime-only (= runtime − repo − RC) skills. See `references/fork-only-skills-policy.md` for details.

## Key pitfalls

- **Variable naming**: Use `skills_ambiguity_runtime_symlink_points_at_release`, NOT `skills_ambiguity_runtime_is_symlink_to_release`. Existing safety tests ban `"symlink_to"` substring in source because `Path.symlink_to()` creates production symlinks. A field name containing `symlink_to` triggers false positives.
- **Results dict key naming must match report labels**: The `report()` function uses `results.get(key, "?")` — if you set `results["runtime_skills_count"]` but the label references `"skills_ambiguity_runtime_skills_count"`, the report prints `?`. **Always use the same `skills_ambiguity_*` prefixed key name in both `results[]` assignments and report labels.** Don't use a short internal name in `results[]` and a long metadata name in `labels[]` — the `report()` function reads directly from `results`, not from the `metadata` dict.
- **Docstring-extraction in tests**: Tests that scan function bodies for forbidden patterns must skip docstrings. The phrase "must not call sync/reset/restore" in a docstring triggers false positives for `"reset"` or `"restore"`. Extract body after `func_src.find('"""', func_src.find('"""') + 3) + 3`.
- **`.bundled_manifest` flat keys**: The manifest uses flat names like `flight-search` while runtime uses `productivity/flight-search`. `_parse_bundled_manifest()` maps short names to category/name format. Unmappable keys should not be force-matched.
- **Generalized check supersedes flight-search check**: `check_skills_source_ambiguity()` covers all runtime-only skills. `check_flight_search_source_of_truth()` is kept for backward compatibility but does not need duplication.

## Audit report

Created at `docs/hermes-skills-ambiguity-audit.md` with:
- Runtime/repo/RC skill counts
- Runtime-only skills list
- Conflicts (runtime-only in repo/RC, manifest legacy entries)
- Per-skill status for flight-search, hermes-preflight-extension, holographic-memory-hygiene
- Untracked skill-related files summary
- Required cleanup decisions
- Fork-local skills classification

## Tests (13 new: #137–149)

- 137: runtime-only skill absent from repo/RC passes
- 138: runtime-only skill present in repo fails
- 139: runtime-only skill present in RC fails
- 140: `~/.hermes/skills` symlink to release fails
- 141: bundled skill in repo and RC is allowed
- 142: bundled skill installed in runtime is allowed
- 143: runtime-only in `.bundled_manifest` creates warning
- 144: duplicate role creates fail
- 145: `hermes skills inspect` NOT used
- 146: no `sync_skills`/`reset`/`restore`/`install_skill`
- 147: no production symlink switch
- 148: metadata fields present
- 149: report labels present