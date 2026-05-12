# Hermes 0.13 sync — selected broader verification gate

Recorded: 2026-05-10 11:53 +05

Scope: isolated analysis worktree only.

```text
worktree=/tmp/hermes-013-sync-analysis-20260510
branch=sync/hermes-013-v2026-5-7-20260510-analysis
primary_checkout=/home/konstantin/.hermes/hermes-agent
```

No commit, push, active checkout update, `hermes update`, gateway restart, reset, or stash-pop was performed.

## Selected broader test scope

This gate covers the areas most likely to regress after the conflict and `skills.external_dirs` policy adaptations:

- agent skill commands and `/reload-skills` handling;
- CLI reload-skills behavior;
- gateway reload-skills and command help surfaces;
- Discord slash command registry surface;
- gateway `/update` command behavior and streaming;
- `hermes update` CLI/autostash/gateway-restart/stale-dashboard/yes-flag behavior.

Command run from `/tmp/hermes-013-sync-analysis-20260510`:

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 -m pytest \
  tests/agent/test_skill_commands.py \
  tests/agent/test_skill_commands_reload.py \
  tests/cli/test_cli_reload_skills.py \
  tests/gateway/test_reload_skills_command.py \
  tests/gateway/test_reload_skills_discord_resync.py \
  tests/gateway/test_gateway_command_help.py \
  tests/gateway/test_discord_slash_commands.py \
  tests/gateway/test_update_command.py \
  tests/gateway/test_update_streaming.py \
  tests/hermes_cli/test_cmd_update.py \
  tests/hermes_cli/test_update_autostash.py \
  tests/hermes_cli/test_update_gateway_restart.py \
  tests/hermes_cli/test_update_stale_dashboard.py \
  tests/hermes_cli/test_update_yes_flag.py \
  -q -o 'addopts='
```

## Initial failure and root cause

Initial run result:

```text
1 failed, 239 passed in 108.11s
```

Failing test:

```text
tests/hermes_cli/test_update_autostash.py::test_cmd_update_retries_optional_extras_individually_when_all_fails
```

Root cause: test drift, not runtime code failure. `hermes_cli/main.py::_install_python_dependencies_with_optional_fallback()` explicitly removed `--quiet` from `pip install` calls so users can see progress during slow C/Rust extension builds. The test still mocked exact commands with `--quiet`, so the fake `.[all]` failure did not fire and the fallback path was not exercised.

Adaptation:

```text
tests/hermes_cli/test_update_autostash.py
```

Updated the fake command matching and expected install command list to match current code:

```text
uv pip install -e .[all]
uv pip install -e .
uv pip install -e .[matrix]
uv pip install -e .[mcp]
```

## Verification after adaptation

Focused regression:

```text
python3 -m pytest tests/hermes_cli/test_update_autostash.py::test_cmd_update_retries_optional_extras_individually_when_all_fails -q -o 'addopts='
1 passed in 4.85s
```

Selected broader gate:

```text
240 passed in 108.35s (0:01:48)
```

Focused logs:

```text
/tmp/hermes-013-update-autostash-focused-after.log
/tmp/hermes-013-selected-broader-tests-after.log
```

Additional scoped checks:

```text
python3 -m py_compile tests/hermes_cli/test_update_autostash.py
unmerged_entries=0
scoped_cached_check=pass
scoped_conflict_marker_hits=0
```

Scoped files in this gate/check set:

```text
agent/curator.py
agent/skill_commands.py
agent/skill_utils.py
hermes_cli/commands.py
hermes_cli/config.py
hermes_cli/tips.py
scripts/release.py
tests/agent/test_curator.py
tests/agent/test_external_skills.py
tests/hermes_cli/test_commands.py
tests/hermes_cli/test_update_autostash.py
tests/tools/test_skill_manager_tool.py
tests/tools/test_skill_usage.py
tools/skill_manager_tool.py
tools/skill_usage.py
```

## Remaining risks / next gate

- This is still not a full release validation.
- Candidate branch is closer to commit-ready, but before commit/push/update/restart the next safe gate should inspect staged resolution diffs for policy correctness, then decide whether to run either a broader full Python test subset or full suite.
- Active checkout/gateway remain outside this gate; do not run `hermes update` or restart until primary dirty state and deployment sequence are explicitly reconciled.
