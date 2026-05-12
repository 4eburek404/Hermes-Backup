# Hermes Agent v0.13.0 sync — conflict and policy analysis

Date: 2026-05-10
Scope: preparation-only analysis for merging official `v2026.5.7` / Hermes Agent `0.13.0` into fork `origin/main`.

## Verified state

- Primary checkout: `/home/konstantin/.hermes/hermes-agent`
- Primary branch: `main`
- Primary HEAD / `origin/main`: `2cdb54d2236b`
- Target tag: `v2026.5.7` / `e19fc91cb82c`
- Isolated worktree: `/tmp/hermes-013-sync-analysis-20260510`
- Analysis branch: `sync/hermes-013-v2026-5-7-20260510-analysis`
- Merge command shape: `git merge --no-commit --no-ff v2026.5.7`
- Merge result: expected content conflicts in 3 files; no commit, push, active checkout update, or gateway restart.
- Primary dirty state at recheck: `skills/github/github-pr-workflow/SKILL.md`, `skills/productivity/flight-search/references/cli-maintenance.md`
- Dirty-state patch exported: `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-pre-update-dirty.patch`

Note: `git tag -v v2026.5.7` returns rc=1 because local Git has no `gpg.ssh.allowedSignersFile` configured for SSH signature verification. This is a local verification-config gap, not a content-merge conflict. Tag object and release text are readable.

## Conflict 1 — `agent/curator.py`

### What our fork changed

Local/fork commit: `90186c04f dev: make repo skills the runtime source`.

Purpose:

- Preserve Konstantin's source/runtime split:
  - authored skill source lives in the Hermes Agent checkout, e.g. `~/.hermes/hermes-agent/skills`;
  - `~/.hermes/skills` is runtime state (`.usage.json`, `.archive`, manifests, hub lock), not the canonical source tree.
- Fix curator wording that implied authored skill data lives under `~/.hermes/skills`.
- Point curator consolidation operations at checkout skills rather than the runtime state tree.

Caveat found during analysis:

- The local auto-merged prompt line currently hardcodes `/home/konstantin/.hermes/hermes-agent/skills/...`.
- That preserves the intended source tree, but it is not profile-safe or checkout-safe source code. Final resolution should replace it with dynamic/check-out-safe wording or rely on `skill_manage(action=write_file)` instead of a literal local path.

### What upstream `v2026.5.7` changed

Upstream made major curator changes in the same file:

- dry-run mode and dry-run banner;
- first-run deferral/seed behavior so curator does not run immediately after update;
- `last_activity_at` / `activity_count` based lifecycle logic;
- richer run reports (`run.json`, `REPORT.md`, structured YAML parsing, consolidated/pruned tracking);
- `absorbed_into` declarations for archive/delete operations and cron skill-reference migration;
- review runtime binding via `auxiliary.curator.{provider,model,api_key,base_url}`;
- defensive creation of `~/.hermes/logs/curator` via `_reports_root()`.

### Did upstream fix the same thing?

Partly, but not the fork-specific issue.

- Upstream fixed report-dir reliability/profile-safe log directory creation. Keep that code.
- Upstream did not fix Konstantin's fork source/runtime layout. It still contains upstream assumptions and prompt text around `~/.hermes/skills` as skill source.

### Recommended resolution

- Keep upstream functional code in `_reports_root()` including `mkdir(parents=True, exist_ok=True)` and debug logging.
- Keep local truth in docs/prompt: checkout skills are source; `~/.hermes/skills` is runtime state/archive.
- Remove or rewrite the hardcoded `/home/konstantin/...` prompt path before committing.
- After resolving, compile `agent/curator.py` and run curator-focused tests.

## Conflict 2 — `scripts/release.py`

### What our fork changed

Local/fork commit: `f49e1b8d1 ci: map contributor for release attribution`.

Purpose:

- Add a fork-specific contributor attribution mapping for `4eburek404` so release/check-attribution tooling can map the local contributor identity correctly.
- The exact email is intentionally not reproduced in this report; it is present in the conflicted source stage.

### What upstream `v2026.5.7` changed

- Upstream heavily expanded `AUTHOR_MAP` with many contributor mappings and corrected at least two existing mappings.
- The release script logic outside `AUTHOR_MAP` is effectively not the conflict surface here.

### Did upstream fix the same thing?

Same class of problem, different entries.

- Upstream fixed many release-attribution gaps.
- Upstream did not include the fork-specific `4eburek404` mapping.

### Recommended resolution

- Take upstream `AUTHOR_MAP` as base.
- Add the local `4eburek404` mapping as a union, without dropping upstream entries.
- Verify with `python3 -m py_compile scripts/release.py`; run the release attribution check only after inspecting `scripts/release.py --help`/command shape.

## Conflict 3 — `tools/skill_usage.py`

### What our fork changed

Local/fork commit: `90186c04f dev: make repo skills the runtime source`.

Purpose:

- Preserve single canonical source directory via `get_skills_dir()` → active Hermes Agent checkout.
- Preserve runtime-only state directory via `get_skills_state_dir()` → `~/.hermes/skills`.
- Keep `.usage.json`, `.archive`, `.bundled_manifest`, and hub lock state out of the source checkout.
- Prevent resurrecting obsolete mirrors or making runtime loading depend on `skills.external_dirs`.

### What upstream `v2026.5.7` changed

Upstream added valuable curator/provenance logic:

- file lock for `.usage.json` read-modify-write operations;
- `latest_activity_at()` and `activity_count()`;
- explicit curator-managed provenance (`created_by`, `mark_agent_created()`, `_is_curator_managed_record()`);
- `list_archived_skill_names()` and recursive restore of nested archive layouts;
- hub skill off-limits detection through `install_path` and frontmatter `name:`, not just hub lock keys.

### Did upstream fix the same thing?

No. It fixed a neighboring class of bugs.

- Upstream fixed curator/hub provenance, concurrency, and archive restore correctness.
- Upstream did not preserve the fork's source/runtime split; upstream's natural model still treats `~/.hermes/skills` as skill source.

### Recommended resolution

Use upstream `v2026.5.7` logic as the base, but keep fork path invariants:

- import and use both `get_skills_dir` and `get_skills_state_dir`;
- `_skills_dir()` returns checkout source;
- `_state_dir()` returns runtime state;
- `_usage_file()` and `_archive_dir()` are under `_state_dir()`;
- `_read_bundled_manifest_names()` reads the runtime manifest under `_state_dir()`;
- `_read_hub_installed_names()` should union both sides:
  - read hub locks from runtime state and checkout if present;
  - keep lock keys;
  - also add upstream's frontmatter names via `install_path`;
  - resolve relative `install_path` against `_skills_dir()`, not `~/.hermes/skills`;
  - accumulate across all locks, not early-return after the first lock.

## Non-conflict but important policy drift to handle before a real update branch

These were discovered while checking upstream changes around the conflict area:

1. New upstream tests assume `skills.external_dirs` is active:
   - `tests/agent/test_external_skills.py`
   - `tests/tools/test_skill_manager_tool.py::TestExternalSkillMutations`

   In this fork, `agent.skill_utils.get_external_skills_dirs()` intentionally returns `[]`. These tests are expected to fail unless we either change the fork policy or patch/skip/adapt these upstream tests to the fork invariant.

2. Some user-facing/help text is stale for this fork:
   - `/reload-skills` descriptions still mention `~/.hermes/skills` and `skills.external_dirs`;
   - `hermes_cli/tips.py` includes external-dir/hub paths that may be misleading under the fork source/runtime split.

   The runtime code paths checked so far mostly still use `get_skills_dir()` / `get_skills_state_dir()`, but docs/help text should be corrected before declaring the sync clean.

3. Curator prompt still needs source-safe wording:
   - local hardcoded `/home/konstantin/...` should not be committed as source;
   - upstream `~/.hermes/skills/...` wording should not be restored as canonical source path.

## Next safe gate

Do not update active runtime yet.

Recommended next step:

1. Apply candidate conflict resolutions in the isolated worktree only.
2. Remove conflict markers.
3. Run:
   - `python3 -m py_compile agent/curator.py scripts/release.py tools/skill_usage.py`
   - focused tests for curator, skill usage, skills source/runtime policy, release attribution, and update flow.
4. Patch policy-drift help/tests if the fork keeps ignoring `skills.external_dirs`.
5. Only then commit/push the sync branch for PR review.
