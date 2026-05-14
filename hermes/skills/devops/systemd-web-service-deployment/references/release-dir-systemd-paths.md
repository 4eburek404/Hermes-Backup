# Release-Directory Systemd Path Convention

## Problem

When deploying via a release-directory scheme (symlink `hermes-agent` → `releases/hermes-agent-<hash>`), systemd units that hardcode concrete release paths survive symlink switches:

```
WorkingDirectory=/home/konstantin/.hermes/releases/hermes-agent-d1c549c4  ← stale
PATH=.../releases/hermes-agent-d1c549c4/node_modules/.bin:...             ← stale
```

The gateway restarts against the old release directory even though the symlink points elsewhere. Any code doing `pathlib.Path.cwd()` or relative file access loads from the wrong release.

## Fix: Drop-In Override

Create `~/.config/systemd/user/<unit>.service.d/10-release-dir-paths.conf`:

```ini
[Service]
WorkingDirectory=/home/konstantin/.hermes/hermes-agent
Environment="PATH=/home/konstantin/.hermes/hermes-agent/node_modules/.bin:/home/konstantin/.hermes/hermes-agent/venv/bin:/home/konstantin/.local/bin:/usr/local/bin:/usr/bin:/bin"
```

All paths use the symlink, not the concrete release directory.

### Apply

```bash
systemctl --user daemon-reload
systemctl --user restart <unit>
```

### Rollback

```bash
mv ~/.config/systemd/user/<unit>.service.d/10-release-dir-paths.conf{,.disabled}
systemctl --user daemon-reload
systemctl --user restart <unit>
```

## Verification

```bash
# Check resolved paths
systemctl --user show <unit> -p ExecStart -p WorkingDirectory -p Environment

# Check raw unit + drop-ins for concrete release references
systemctl --user cat <unit> | grep -E "releases/[a-zA-Z0-9_-]+-[a-f0-9]+"
```

Expected: WorkingDirectory resolves through the symlink; PATH does not contain concrete release paths; only the symlink path appears.

## R14A-2 Case Study

- **Active symlink:** `hermes-agent → releases/hermes-agent-fe6dbf61`
- **Systemd unit had:** `WorkingDirectory=.../releases/hermes-agent-d1c549c4` (old)
- **ExecStart was canonical** (used symlink path) — no change needed
- **Fix:** drop-in override for WorkingDirectory + PATH only
- **Backup:** `/home/konstantin/.hermes/systemd-backups/hermes-gateway.before-r14a2.20260512092709.service.txt`
- **Drop-in:** `/home/konstantin/.config/systemd/user/hermes-gateway.service.d/10-release-dir-paths.conf`
- **Result:** gateway restarted cleanly on first attempt, no critical logs

## R14C-1 Preflight Checks

The release preflight script (`scripts/hermes_release_preflight.py`) now validates systemd path hygiene automatically:

- **`systemd_execstart_symlink_based`** — ExecStart uses `~/.hermes/hermes-agent/venv/bin/python` (symlink), not a concrete release path
- **`systemd_working_directory_symlink_based`** — WorkingDirectory uses `~/.hermes/hermes-agent` (symlink), not a concrete release path
- **`systemd_path_contains_concrete_release`** — PATH contains no paths matching `~/.hermes/releases/hermes-agent-*`
- **`systemd_release_dir_paths_ok`** — aggregate: all three above pass

All checks are **read-only** (use `systemctl --user show` and `systemctl --user cat`, never start/stop/restart). If any check fails, preflight reports FAIL without modifying the running system.

## R14C-2 CWD Leak and Skills Architecture

The same preflight also validates that RC runtime subprocess calls use `cwd=rc_dir` (simulating the production WorkingDirectory). Without this, Python `sys.path[0]=""` causes imports to resolve from the script's CWD (repo checkout) instead of the RC venv. See `references/release-preflight-cwd-leak.md` for full reproduction and fix details.
