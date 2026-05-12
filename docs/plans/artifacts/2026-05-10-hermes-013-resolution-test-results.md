# Hermes 0.13 sync — conflict resolution and focused verification

Recorded: 2026-05-10 11:21 +05

Scope: isolated analysis worktree only.

```text
worktree=/tmp/hermes-013-sync-analysis-20260510
branch=sync/hermes-013-v2026-5-7-20260510-analysis
merge_head=e19fc91cb
primary_checkout=/home/konstantin/.hermes/hermes-agent
```

No commit, push, active checkout update, `hermes update`, gateway restart, reset, or stash-pop was performed.

## Files intentionally staged in the isolated worktree

```text
agent/curator.py
scripts/release.py
tools/skill_usage.py
tests/agent/test_curator.py
tests/tools/test_skill_usage.py
```

## Resolution decisions

- `agent/curator.py`: kept upstream curator improvements while preserving the fork invariant: authored skill source is the Hermes Agent checkout `skills/` tree; runtime/usage/archive state is under `~/.hermes/skills`. Removed the local hardcoded `/home/konstantin/...` prompt path.
- `scripts/release.py`: used a union `AUTHOR_MAP`: kept the fork mapping for `4eburek404` and upstream mappings such as `olisikh` and `leoneparise`.
- `tools/skill_usage.py`: kept upstream locking/provenance/activity/archive/hub detection improvements while preserving `get_skills_dir()` for source skills and `get_skills_state_dir()` for runtime state.
- `tests/agent/test_curator.py` and `tests/tools/test_skill_usage.py`: adapted focused tests to the source/runtime split so fixtures use separate source `skills/` and runtime `~/.hermes/skills` locations. Also replaced placeholder credential strings in tests with explicit non-secret dummy values.

## Verification

Commands run from `/tmp/hermes-013-sync-analysis-20260510`:

```bash
git diff --name-only --diff-filter=U -- agent/curator.py scripts/release.py tools/skill_usage.py tests/agent/test_curator.py tests/tools/test_skill_usage.py
git diff --cached --check -- agent/curator.py scripts/release.py tools/skill_usage.py tests/agent/test_curator.py tests/tools/test_skill_usage.py
python3 -m py_compile agent/curator.py scripts/release.py tools/skill_usage.py tests/agent/test_curator.py tests/tools/test_skill_usage.py
python3 -m pytest tests/agent/test_curator.py tests/agent/test_curator_activity.py tests/agent/test_curator_reports.py tests/tools/test_skill_usage.py -q -o 'addopts='
```

Observed results:

```text
unmerged_scoped=0
changed_file_marker_hits=0
scoped_cached_check=pass
py_compile_ok
focused_pytest=100 passed in 2.60s
```

Repository-level merge state check:

```text
git ls-files -u | wc -l => 0
```

## Remaining risks / next gate

- This is not a full release validation; only the conflict files and focused curator/skill-usage tests were verified.
- Upstream non-conflict drift around `skills.external_dirs` still needs fork-policy review/adaptation, especially `tests/agent/test_external_skills.py` and skill manager external mutation tests.
- A global `git diff --cached --check` currently reports upstream whitespace issues and flags `tests/tools/test_mcp_oauth_metadata.py:10` because it is an RST heading line exactly equal to `=======`, not one of the conflict files changed here. Treat this as a broader upstream/check-policy issue, not a blocker for the scoped conflict resolution.
- Do not commit/push/update/restart until the external-dir policy gate and selected broader tests are complete.
