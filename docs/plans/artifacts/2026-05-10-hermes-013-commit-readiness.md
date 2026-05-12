# Hermes 0.13 isolated branch commit-readiness gate

Timestamp: 2026-05-10 12:03 +05

Scope: read-only assessment of isolated merge worktree after conflict, external_dirs, and selected broader verification gates. No commit, push, active checkout update, gateway restart, reset, or stash-pop was performed.

## Worktree provenance

```text
worktree=/tmp/hermes-013-sync-analysis-20260510
branch=sync/hermes-013-v2026-5-7-20260510-analysis
HEAD=2cdb54d2236b
MERGE_HEAD=e19fc91cb82c
merge_target=v2026.5.7 / Hermes Agent 0.13.0
```

## Status summary

```text
status_counts={'A ': 404, 'D ': 1, 'M ': 678}
staged=1083
unstaged=0
untracked=0
unmerged=0
```

Interpretation: the merge index is mechanically resolved and clean of unstaged/untracked work, but it contains the full upstream release merge, not only the locally resolved/adapted files.

## Diff shape

Staged diff relative to fork HEAD:

```text
files=1083
statuses={'M': 678, 'A': 404, 'D': 1}
topdirs=tests:357, website:211, plugins:90, ui-tui:71, hermes_cli:45, optional-skills:44, skills:42, tools:41, gateway:40, web:40, agent:32, root:20
numstat=166503 additions, 10022 deletions, 18 binary/uncomputed
```

Final merge result relative to upstream release tag (`MERGE_HEAD`) still differs in fork-specific areas:

```text
files=262
statuses={'M': 42, 'A': 218, 'D': 2}
topdirs=skills:208, tests:24, tools:10, agent:7, root:4, hermes_cli:4, plugins:4, scripts:1
```

Interpretation: expected for syncing a fork with local skill/source-runtime policy, but this is why the branch is not deploy-ready until staged diff review is accepted.

## Checks

Selected broader test gate was already recorded separately:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-selected-broader-tests.md
selected_broader_pytest=240 passed in 108.35s
```

Commit-readiness checks in this gate:

```text
scoped_cached_check_for_15_policy_files=pass
scoped_conflict_marker_scan_for_15_policy_files=0
exact_conflict_marker_scan_across_staged_ACMR_files=0
```

All-repo cached check is not clean:

```text
git diff --cached --check exit=2
```

Observed classes:

- upstream/release trailing whitespace and blank-line-at-EOF noise in optional skills, gateway tests, website docs, UI tests, and tool docs;
- `tests/tools/test_mcp_oauth_metadata.py:10` reported by Git as `leftover conflict marker`, but the file content is a docstring reStructuredText heading:

```text
Context
=======
```

The exact marker scan found no `<<<<<<<` or `>>>>>>>` markers. Therefore this is a Git check false positive for the heading, not an unresolved merge marker. If the project requires all-repo `git diff --check` to pass before push, this needs a separate upstream-noise cleanup decision; it was not fixed in this gate to avoid broad, unrelated edits.

## Policy-sensitive review result

Reviewed diff excerpts for:

- `agent/curator.py`
- `agent/skill_commands.py`
- `agent/skill_utils.py`
- `hermes_cli/commands.py`
- `hermes_cli/config.py`
- `hermes_cli/tips.py`
- `scripts/release.py`
- `tools/skill_manager_tool.py`
- `tools/skill_usage.py`
- `tests/agent/test_external_skills.py`
- `tests/hermes_cli/test_update_autostash.py`
- `tests/tools/test_skill_manager_tool.py`
- `tests/tools/test_skill_usage.py`

Assessment:

- source/runtime split is preserved: authored skills stay in the Hermes Agent checkout `skills/`; runtime state stays under `~/.hermes/skills`;
- `skills.external_dirs` remains intentionally ignored by this fork;
- `/reload-skills`, Discord/gateway command surfaces, config comments, and tips are aligned to the fork policy;
- `tools/skill_usage.py` uses source helpers for authored skills and state helpers for usage/archive/manifest/hub state;
- `scripts/release.py` keeps the fork `4eburek404` contributor mapping while incorporating upstream `AUTHOR_MAP` expansion;
- update-autostash tests now match the current non-`--quiet` install command shape.

Caveat: this is a targeted policy/diff readiness review, not a full line-by-line review of the entire 1083-file release merge.

## Primary checkout blocker

Active primary checkout remains dirty and must be reconciled separately before any active `hermes update`, checkout replacement, gateway restart, or Telegram smoke.

Fresh primary status at this gate:

```text
repo=/home/konstantin/.hermes/hermes-agent
branch=main
HEAD=2cdb54d2236b
status:
 M skills/autonomous-ai-agents/hermes-agent/SKILL.md
 M skills/github/github-pr-workflow/SKILL.md
 M skills/productivity/flight-search/references/cli-maintenance.md
?? skills/autonomous-ai-agents/hermes-agent/references/fork-release-sync-conflicts.md
```

## Readiness decision

Commit/push readiness: conditionally ready for a human commit/push decision, not automatically ready to commit/push/deploy.

Green gates:

- merge conflicts resolved;
- unmerged entries: 0;
- no unstaged/untracked files in isolated worktree;
- focused conflict gate passed;
- external_dirs policy gate passed;
- selected broader gate passed (`240 passed`);
- scoped policy files pass cached whitespace and exact marker scans;
- exact staged conflict marker scan found 0 unresolved `<<<<<<<`/`>>>>>>>` markers.

Remaining decisions before commit/push:

1. Accept that the merge commit includes the full upstream release staged diff (`1083` files) plus retained fork-specific deltas (`262` files vs upstream tag).
2. Decide whether to run the full Python suite before committing, or accept the focused + selected broader gates.
3. Decide whether to leave upstream `git diff --check` noise untouched, or do a separate cleanup pass.
4. Reconcile dirty primary checkout before applying this branch to the active Hermes source/runtime.

Recommended next safe gate: run a final staged-diff review artifact/summary and, if approved, commit only in the isolated branch. Do not push or update active checkout until primary dirty state is reconciled.
