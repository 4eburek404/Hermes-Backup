# Tool Output Compaction — Artifact Root Migration

## When to Migrate

After 1–2 days of successful compaction in production with the `/tmp` root, migrate to a persistent path so artifacts survive reboots and `/tmp` cleanup.

**Signs you're ready:**
- Gateway stable, no ImportError/503 after compaction enablement
- New `.raw` artifacts appearing reliably on large terminal outputs
- Telegram receiving compacted summaries, not raw dumps
- `redaction_status: clean` on synthetic test artifacts

## Migration Steps

### 1. Pre-check
```bash
readlink -f ~/.hermes/hermes-agent                                 # active release
systemctl --user is-active hermes-gateway                          # must be active
grep -A6 "tool_output_compaction" ~/.hermes/config.yaml            # current config
find /tmp/hermes-tool-output-compaction-artifacts -type f | wc -l  # artifact count before
du -sb /tmp/hermes-tool-output-compaction-artifacts | cut -f1      # bytes before
```

### 2. Create persistent root
```bash
mkdir -p ~/.hermes/tool-output-artifacts
chmod 700 ~/.hermes/tool-output-artifacts
```

### 3. Copy existing artifacts (preserve structure)
```bash
cp -a /tmp/hermes-tool-output-compaction-artifacts/* ~/.hermes/tool-output-artifacts/
```
**Do NOT delete /tmp source** until migration is verified.

Verify:
```bash
find ~/.hermes/tool-output-artifacts -type f | wc -l   # should match source count
du -sb ~/.hermes/tool-output-artifacts | cut -f1       # should match source bytes
```

### 4. Backup config
```bash
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.backup_before_artifact_root_move_$(date +%Y%m%d%H%M%S)
```

### 5. Update config.yaml
Change ONLY the `artifact_root` line:
```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: [telegram]
  enabled_output_kinds: [terminal]
  artifact_root: /home/konstantin/.hermes/tool-output-artifacts
  secret_policy: redact_or_block
```

### 6. Restart gateway
```bash
systemctl --user restart hermes-gateway
sleep 8
systemctl --user is-active hermes-gateway
```

### 7. Verify with live test
Send a controlled synthetic terminal output (via Telegram):
```python
python - <<'PY'
for i in range(120):
    print(f"R13A_PERSISTENT_ARTIFACT_ROOT_LINE_{i:03d} " + "x" * 120)
PY
```

After execution:
- ✅ New artifact appears in `~/.hermes/tool-output-artifacts/`
- ✅ NO new artifact in `/tmp/hermes-tool-output-compaction-artifacts/`
- ✅ Telegram receives compacted summary, not full raw output
- ✅ Gateway remains active

### 8. Check logs for critical errors
```bash
journalctl --user -u hermes-gateway --since "3 minutes ago" --no-pager \
  | grep -Ei "ImportError|ModuleNotFoundError|ToolOutputCompactionConfig|file is not a database|503|traceback|exception" \
  | grep -Ev "/bin/bash -c|grep -Ei|journalctl" || true
```
Expected: empty (transient SSL ReadErrors during restart are not compaction-related).

## Rollback

If migration fails (artifacts go to wrong path, gateway errors):
```bash
# Restore config
cp ~/.hermes/config.yaml.backup_before_artifact_root_move_* ~/.hermes/config.yaml

# Restart
systemctl --user restart hermes-gateway
```

## Pitfalls

- **Don't delete /tmp artifacts before verification.** The migration is verified when a NEW tool call creates an artifact in the persistent path and NOT in /tmp.
- **Test invocation.** When running compaction tests in a repo with `pyproject.toml` that has baked-in xdist flags, use `-o 'addopts='`:
  ```bash
  ~/.hermes/hermes-agent/venv/bin/pytest tests/test_tool_output_compaction_*.py -q -o "addopts="
  ```
- **Push upstream.** New branches need `--set-upstream` on first push:
  ```bash
  git push --set-upstream origin <branch>
  ```
- **Config backup mandatory.** Always create a timestamped backup before editing `config.yaml`. The backup path must be reported in the final summary.

## Post-Migration Artifacts

- Persistent root: `/home/konstantin/.hermes/tool-output-artifacts/`
- Old root (kept for reference): `/tmp/hermes-tool-output-compaction-artifacts/`
- Config backup: `~/.hermes/config.yaml.backup_before_artifact_root_move_<timestamp>`
