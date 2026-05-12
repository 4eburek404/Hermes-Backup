# R11C — Release-Dir Deploy Plan

## Context

After R11A post-incident stabilization and R11B Docker sandbox validation, the next
phase is a controlled release-directory deployment — **not** manual file-copy hotfixes
into production.

## Key Principles

1. **Atomic switch, not piecemeal copy.** Each release is a self-contained directory
   under `/home/konstantin/.hermes/releases/`. Switching means updating one symlink
   and restarting the gateway. No partial state.

2. **No `/tmp` as release target.** Release directories live under
   `~/.hermes/releases/`, which is persistent and backed up. `/tmp` is cleared on reboot.

3. **Rollback = point symlink back.** No file-by-file reversal. Keep the previous
   release directory until the new one is verified.

4. **Production config must not be mutated during build.** The build phase only creates
   files in the new release directory. `~/.hermes/config.yaml` is only changed during
   the explicit switch phase, with a backup.

5. **Compaction stays disabled before switch.** `tool_output_compaction.enabled: false`
   in production config. Enablement is a separate config change after gateway stability
   is confirmed.

## Directory Layout

```
/home/konstantin/.hermes/releases/hermes-agent-<commit-or-timestamp>/
  ├── venv/
  ├── hermes_agent/  (or source symlink)
  ├── run_agent.py
  ├── scripts/
  │   ├── tool_output_compaction.py
  │   ├── tool_output_summarizer.py
  │   └── tool_output_artifacts.py
  ├── tools/
  │   └── budget_config.py
  └── ...

/home/konstantin/.hermes/hermes-agent-current → releases/hermes-agent-<active>
```

## Build/Install Procedure

1. Create release dir: `mkdir -p ~/.hermes/releases/hermes-agent-<tag>`
2. Copy or `git worktree add` the fork into the release dir
3. Create venv: `python3 -m venv venv && source venv/bin/activate`
4. Install: `pip install -e .`
5. Compile-check: `python -m py_compile run_agent.py scripts/tool_output_compaction.py ...`
6. Run targeted pytest
7. Run Docker sandbox smoke (or equivalent local smoke)
8. No `~/.hermes/` mutation during build

## Pre-Switch Checks

- Compare current production path: `readlink -f ~/.hermes/hermes-agent-current`
- Check systemd unit: `systemctl --user cat hermes-gateway | grep ExecStart`
- Backup config: `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.pre-$(date +%Y%m%d%H%M%S)`
- Verify gateway active: `systemctl --user is-active hermes-gateway`
- Note current route/model (without secrets)

## Switch Procedure (requires explicit approval)

```
systemctl --user stop hermes-gateway
ln -sfn <NEW_RELEASE_DIR> ~/.hermes/hermes-agent-current
# If ExecStart doesn't use the symlink, update the unit:
# systemctl --user edit hermes-gateway  # set ExecStart to use symlink
# systemctl --user daemon-reload
systemctl --user start hermes-gateway
systemctl --user is-active hermes-gateway
# Check logs, send Telegram /reset + ping manually
```

## Controlled Compaction Enablement (after gateway stable)

```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: [telegram]
  enabled_output_kinds: [terminal]
  artifact_root: /home/konstantin/.hermes/artifacts
  secret_policy: redact_or_block
```

## Rollback

```
systemctl --user stop hermes-gateway
ln -sfn <PREV_RELEASE_DIR> ~/.hermes/hermes-agent-current
# If config was changed: cp ~/.hermes/config.yaml.pre-<TS> ~/.hermes/config.yaml
systemctl --user start hermes-gateway
# Verify logs, no errors
```

## Stop Conditions (rollback immediately)

- ImportError on ToolOutputCompactionConfig
- HTTP 503 on /reset + ping after stable route
- "file is not a database" in logs
- Gateway not active after start
- Artifact written outside configured root
- Raw secret leak in compacted output
- Raw large terminal output in payload when compaction enabled
- Deleted tracked files in release worktree