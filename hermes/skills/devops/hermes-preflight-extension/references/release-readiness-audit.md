# Release Readiness Audit Pattern (R14D-4a)

## When to run

Before creating a switch script for a new release (R14E or later), perform a
readiness audit to confirm nothing is forgotten.

## Audit steps

1. **Runtime vs bundled skills**: Compare `~/.hermes/skills/` (runtime) against
   the repo's `skills/` (bundled). Custom/non-bundled skills exist only at
   runtime — they don't need to be in the repo, but they must be present at
   `~/.hermes/skills/`.

   ```bash
   find ~/.hermes/skills -maxdepth 5 -type f -name 'SKILL.md' -printf '%P\n' | sort > /tmp/runtime.txt
   find ~/path/to/repo/skills -maxdepth 5 -type f -name 'SKILL.md' -printf '%P\n' | sort > /tmp/bundled.txt
   comm -23 /tmp/runtime.txt /tmp/bundled.txt  # non-bundled = custom runtime-only
   ```

2. **Fork-local vs upstream bundled**: Skills in our fork's `repo/skills/` but absent from upstream `NousResearch/hermes-agent` main branch are fork-local additions. They pass `check_skills_source_ambiguity()` as "bundled" but should be treated as runtime-only by provenance. To identify them:

   ```bash
   # Enumerate upstream skills via GitHub API
   curl -sL "https://api.github.com/repos/NousResearch/hermes-agent/contents/skills" \
     | python3 -c "import json,sys; [print(d['name']) for d in json.load(sys.stdin) if d['type']=='dir']"
   # Then drill into each category (especially mlops/ subcategories)
   # Build full upstream set as category/name IDs
   # Diff: fork_skills - upstream_skills = fork-only
   ```

   Known fork-only skills (May 2026): `devops/hermes-runtime-health-check`, `devops/systemd-web-service-deployment`, `gaming/minecraft-modpack-server`, `mlops/huggingface-hub`, `mlops/ollama`, `productivity/hh-ru`, `research/web-content-acquisition`, `software-development/skill-audit-and-improvement`, `software-development/tool-output-summarization`.

3. **Key runtime skill verification**: For each important custom skill (e.g.,
   `productivity/flight-search`), verify:
   - SKILL.md exists at `~/.hermes/skills/<category>/<name>/SKILL.md`
   - Key assets (references/, scripts/, templates/, cli/) exist
   - Visible in `hermes skills list` (but don't rely on `hermes skills inspect`
     as proof — it's a hub/remote diagnostic, not runtime validation)

4. **Untracked file classification**: Run `git ls-files --others --exclude-standard`
   to enumerate untracked files. Classify each:
   - **A. Must track before release** — files the RC build needs but are only
     in the working tree (typically: updated SKILL.md that differs from bundled)
   - **B. Documentation/reference only** — reference docs that enrich agent
     context but aren't needed for RC build (most untracked `references/*.md`)
   - **C. Needs user decision** — unclear whether to track

5. **RC build verification**: After `--replace-rc`, verify:
   - Untracked files do NOT appear in the RC path (git archive only includes
     tracked files)
   - State files (MEMORY.md, USER.md, SOUL.md) are NOT in the RC
   - config.yaml, .env, memory_store.db are NOT in the RC

6. **Readiness checklist**: Before switch script:
   - [ ] Full preflight PASS on HEAD
   - [ ] State files required check works (FAIL on missing)
   - [ ] Custom runtime skills available at runtime
   - [ ] Fork-local skills identified and classified
   - [ ] No release-blocking untracked files missing from git
   - [ ] No state/config files leak into RC
   - [ ] Production symlink untouched

## Key insight: `sync_skills()` is runtime-first

The `sync_skills()` function in Hermes uses a "state-first" strategy: it reads
skills from `~/.hermes/skills/` (runtime, writable) before falling back to
bundled skills in the RC. This means:
- Bundled skills get synced from the RC into `~/.hermes/skills/` on first run
- Custom (non-bundled) skills must already exist in `~/.hermes/skills/`
- Untracked reference files in the repo's `skills/` directory are **not**
  synced — they're repo-local context, not runtime artifacts

## untracked SKILL.md edge case

If a bundled skill has an untracked SKILL.md in the working tree (e.g.,
`skills/software-development/tool-output-summarization/SKILL.md`), this is a
local override. The RC will contain the **tracked** (bundled) version. The
untracked version only matters if it should replace the bundled one — that
requires a user decision to `git add` the updated file.