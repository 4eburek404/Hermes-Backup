# Fork-Only Skills Release Policy (R14D-5b2 — generalized)

## Problem

In a forked Hermes Agent repo, some skills exist in our `repo/skills/` but not in the upstream `NousResearch/hermes-agent` repository. These "fork-only" skills are treated as bundled by `check_skills_source_ambiguity()` because they appear in repo/skills, but by provenance they should be runtime-only — they must live in `~/.hermes/skills/` and must NOT be in `release/skills/`.

## Solution (R14D-5b2 — generalized)

The hardcoded `FORK_ONLY_SKILLS` list from R14D-5b has been replaced with dynamic detection using an upstream snapshot file. This ensures new runtime-only skills are automatically allowed and new non-upstream skills in repo/RC are automatically caught.

`check_fork_only_skills_policy()` uses `_load_upstream_skills(repo_path)` to read `ops/upstream-bundled-skills.txt` (one skill ID per line, `category/name` format). It then:

1. Collects skill IDs from repo, RC, and runtime using `_collect_skill_ids(base_dir)`
2. Computes: `repo_fork_only = repo_ids - upstream_ids`, `rc_fork_only = rc_ids - upstream_ids`, `runtime_only = runtime_ids - upstream_ids`
3. Enforces policy:
   - Missing/empty upstream snapshot → FAIL (cannot classify skills)
   - Fork-only skill in repo/skills → FAIL (release-blocking)
   - Fork-only skill in RC/skills → FAIL
   - Fork-only skill missing from runtime → FAIL
   - Runtime-only skill (in ~/.hermes/skills, not upstream) → OK
   - ~/.hermes/skills symlinked to release → FAIL
   - Fork-only skill in .bundled_manifest → WARN (legacy entry)
   - All checks pass → PASS

## Implementation Pattern

```python
UPSTREAM_SKILLS_SNAPSHOT = "ops/upstream-bundled-skills.txt"

def _load_upstream_skills(repo_path: Path) -> set:
    """Load upstream-bundled skill IDs from ops/upstream-bundled-skills.txt."""
    snapshot_path = repo_path / UPSTREAM_SKILLS_SNAPSHOT
    if not snapshot_path.is_file():
        return set()
    try:
        skills = set()
        for line in snapshot_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                skills.add(line)
        return skills
    except Exception:
        return set()

def _collect_skill_ids(base_dir: Path) -> set:
    """Collect skill IDs by scanning for SKILL.md files."""
    ids = set()
    if base_dir.is_dir():
        for skmd in base_dir.rglob("SKILL.md"):
            rel = skmd.relative_to(base_dir)
            skill_id = str(rel.parent)
            ids.add(skill_id)
    return ids

def check_fork_only_skills_policy(repo_path, rc_dir, hermes_home, results, errors):
    # 0. Check ~/.hermes/skills is not symlink to release
    # 1. Load upstream snapshot → upstream_ids
    # 2. Collect repo_ids, rc_ids, runtime_ids via _collect_skill_ids()
    # 3. Compute repo_fork_only, rc_fork_only, runtime_only
    # 4. Check FAIL conditions
    # 5. Check manifest legacy entries → WARN
    # 6. Set results
```

## Metadata Fields

- `fork_only_skills_checked` — whether the check ran
- `upstream_bundled_skills_count` — count of skills in upstream snapshot
- `fork_only_runtime_missing` — list of fork-only skills missing from runtime
- `fork_only_present_in_rc` — list of fork-only skills found in RC/skills/
- `fork_only_manifest_legacy_entries` — fork-only skills with legacy manifest entries
- `repo_fork_only_skill_ids` — skills in repo/skills not found in upstream snapshot
- `rc_fork_only_skill_ids` — skills in RC/skills not found in upstream snapshot
- `runtime_only_skill_ids` — skills in ~/.hermes/skills not found in upstream snapshot
- `fork_only_policy_status` — PASS / WARN / FAIL

## Report Labels (BQ9-BQ17)

- BQ9. fork-only skills checked
- BQ10. upstream bundled count
- BQ11. fork-only runtime missing
- BQ12. fork-only present in RC
- BQ13. fork-only manifest legacy entries
- BQ14. repo fork-only skills
- BQ15. RC fork-only skills
- BQ16. runtime-only skills
- BQ17. fork-only policy status

## Updating The Upstream Snapshot

To regenerate `ops/upstream-bundled-skills.txt`:

```bash
git fetch upstream --prune
UPSTREAM_COMMIT="$(git rev-parse upstream/main)"

git ls-tree -r --name-only upstream/main skills \
  | grep '/SKILL.md$' \
  | sed 's#^skills/##; s#/SKILL.md$##' \
  | sort > /tmp/upstream-bundled-skills.txt

{
  echo "# Generated from upstream/main at ${UPSTREAM_COMMIT}"
  echo "# One skill id per line: category/name"
  cat /tmp/upstream-bundled-skills.txt
} > ops/upstream-bundled-skills.txt
```

Update the snapshot **intentionally** when rebasing or updating upstream skills. Do not regenerate automatically during preflight.

## Snapshot Format

```
# Generated from upstream/main at <commit-hash>
# One skill id per line: category/name
apple/apple-notes
autonomous-ai-agents/codex
autonomous-ai-agents/hermes-agent
...
```

Lines starting with `#` are comments. Empty lines are skipped. Each line is a skill ID in `category/name` format (matching the path relative to `skills/`).

## Expected Preflight Result Before De-bundle

Before fork-only skills are removed from `repo/skills/`, the preflight will **FAIL** with errors like:
```
Fork-only skill <id> found in release/skills. Fork-only skills must be runtime-only, not bundled in RC.
```

This is expected and correct. The FAIL status will resolve after R14D-5c de-bundle.

## Safety

- Does NOT call sync_skills, reset, restore, install_skill
- Does NOT switch production symlink or restart gateway
- Does NOT modify .bundled_manifest or runtime state
- Does NOT use `hermes skills inspect`
- Read-only verification only

## History

- R14D-5b: Initial implementation with hardcoded `FORK_ONLY_SKILLS` list (9 entries)
- R14D-5b2: Generalized to use `ops/upstream-bundled-skills.txt` snapshot, removed hardcoded list, discovered additional fork-only skills (outlines, axolotl, trl-fine-tuning, unsloth, knowledge-architecture), corrected minecraft-modpack-server and huggingface-hub as upstream-bundled (not fork-only)
- R14D-5c (complete): De-bundled all 12 tracked fork-only skills from repo/skills in 4 batches. `software-development/tool-output-summarization` was untracked (not in git index), so no `git rm` needed. After de-bundle, preflight progressed from FAIL to **PASS**. Old hardcoded `FORK_ONLY_SKILLS` list is fully removed.

## Related

- `docs/hermes-skills-release-policy.md` — Full policy document
- `check_skills_source_ambiguity()` — Generalized source-of-truth check (R14D-4c)
- `check_flight_search_source_of_truth()` — Single-skill predecessor (R14D-4b)