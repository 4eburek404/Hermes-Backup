# Hermes 0.13 sync — external_dirs fork-policy gate

Recorded: 2026-05-10 11:42 +05

Scope: isolated analysis worktree only.

```text
worktree=/tmp/hermes-013-sync-analysis-20260510
branch=sync/hermes-013-v2026-5-7-20260510-analysis
primary_checkout=/home/konstantin/.hermes/hermes-agent
```

No commit, push, active checkout update, `hermes update`, gateway restart, reset, or stash-pop was performed.

## Finding

Upstream `v2026.5.7` introduced/expanded `skills.external_dirs` behavior and tests. That conflicts with Konstantin's fork invariant:

- authored/source skills: Hermes Agent checkout `skills/` tree;
- runtime/user state: `~/.hermes/skills`;
- `skills.external_dirs`: ignored in this setup to avoid hidden dependencies on compatibility paths, mirrors, or symlinks.

`agent/skill_utils.py` already had the fork policy (`get_external_skills_dirs() -> []`, `get_all_skills_dirs() -> [get_skills_dir()]`), but non-conflict upstream files/tests still expected external directories to be visible or mutable.

## Files adapted for the policy gate

```text
agent/skill_utils.py
agent/skill_commands.py
hermes_cli/commands.py
hermes_cli/config.py
hermes_cli/tips.py
tools/skill_manager_tool.py
tests/agent/test_external_skills.py
tests/hermes_cli/test_commands.py
tests/tools/test_skill_manager_tool.py
```

## Adaptation decisions

- `agent/skill_utils.py`: clarified docstring that external skill directories accepted by this fork are none.
- `agent/skill_commands.py`: `/reload-skills` docstring now says it rescans the canonical checkout `skills/` tree and ignores `skills.external_dirs`.
- `hermes_cli/commands.py`: gateway/Discord skill command collection now filters only under canonical `SKILLS_DIR`; external-dir widening was removed.
- `hermes_cli/config.py`: kept `skills.external_dirs` as an upstream-compatibility key but marked it ignored in this fork.
- `hermes_cli/tips.py`: replaced the external-dirs tip with source-checkout wording.
- `tests/agent/test_external_skills.py`: rewritten to assert configured external dirs are ignored and canonical source remains visible.
- `tests/tools/test_skill_manager_tool.py`: replaced upstream in-place external mutation tests with fork-policy tests: external skills are not found/mutated; create still writes to canonical source.
- `tests/hermes_cli/test_commands.py`: external-dir gateway command tests now assert exclusion, not inclusion.

## Verification

Commands run from `/tmp/hermes-013-sync-analysis-20260510`:

```bash
python3 -m py_compile \
  agent/curator.py scripts/release.py tools/skill_usage.py \
  agent/skill_utils.py agent/skill_commands.py hermes_cli/commands.py hermes_cli/config.py hermes_cli/tips.py \
  tools/skill_manager_tool.py \
  tests/agent/test_curator.py tests/tools/test_skill_usage.py tests/agent/test_external_skills.py tests/tools/test_skill_manager_tool.py tests/hermes_cli/test_commands.py

python3 -m pytest \
  tests/agent/test_curator.py \
  tests/agent/test_curator_activity.py \
  tests/agent/test_curator_reports.py \
  tests/tools/test_skill_usage.py \
  tests/agent/test_external_skills.py \
  tests/tools/test_skill_manager_tool.py::TestConfiguredExternalSkillMutationsIgnored \
  tests/hermes_cli/test_commands.py \
  -k 'not integration and (external_dir or external_dirs or external_skill or curator or skill_usage or ConfiguredExternalSkillMutationsIgnored)' \
  -q -o 'addopts='

git diff --cached --check -- <14 scoped files>
precise marker scan over <14 scoped files>
```

Observed results:

```text
py_compile=pass
combined_focused_pytest=118 passed, 140 deselected in 2.79s
unmerged_entries=0
scoped_cached_check=pass
scoped_conflict_marker_hits=0
```

Focused pytest log:

```text
/tmp/hermes-013-combined-focused-after.log
```

## Remaining risks / next gate

- Still not a full release validation; this gate covers conflict files, curator/skill_usage, external_dirs policy, skill manager external mutation policy, and gateway external-dir command filters.
- Need inspect/update any website/docs generated text if the fork will publish docs from this branch; runtime code/help is aligned, but broad docs may still describe upstream external_dirs behavior.
- Need selected broader tests before commit/push/update/restart, likely around skills CLI/help, skill commands reload, gateway slash commands, and update path.
- Active checkout and gateway remain untouched.
