# Hermes release-dir → supported pip venv migration runbook

Date: 2026-05-24. Scope: analysis/runbook only; no production migration performed.

## Executive conclusion

**Is release-dir still necessary?** Partially today, **no as the target architecture**.

The release-dir deployment originally solved a real production risk: Hermes core was locally patched, and copying files into a live runtime once produced a mixed-code failure. An immutable release directory plus symlink switch made core deployments atomic and rollbackable.

That risk is now mostly gone because Konstantin no longer patches Hermes core. Custom work is maintained as skills/plugins/state in `HERMES_HOME` and in the private backup repo, not as changes inside the active Hermes core. The remaining risk is not “dirty core checkout” anymore; it is upgrade/state safety. That should be handled by a supported pip venv, pinned package versions, pre-migration backups, and explicit rollback procedures.

Recommended target: **dedicated pip-based Python venv + unchanged `HERMES_HOME=/home/konstantin/.hermes`**.

## Current production layout observed

Read-only inventory from 2026-05-24:

- Active CLI:
  - `command -v hermes` → `/home/konstantin/.local/bin/hermes`
  - resolved CLI → `/home/konstantin/.hermes/releases/hermes-agent-d04c50f2f614/venv/bin/hermes`
  - version → `Hermes Agent v0.13.0 (2026.5.7)`
- Active symlink:
  - `/home/konstantin/.hermes/hermes-agent`
  - resolves to `/home/konstantin/.hermes/releases/hermes-agent-d04c50f2f614`
- Active package:
  - `hermes-agent==0.13.0`
  - installed in `/home/konstantin/.hermes/hermes-agent/venv/lib/python3.11/site-packages`
- systemd user service:
  - unit: `/home/konstantin/.config/systemd/user/hermes-gateway.service`
  - drop-ins:
    - `10-killmode-control-group.conf`
    - `10-release-dir-paths.conf`
  - `ExecStart=/home/konstantin/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run --replace`
  - `WorkingDirectory=/home/konstantin/.hermes/hermes-agent`
  - environment includes `VIRTUAL_ENV=/home/konstantin/.hermes/hermes-agent/venv`
  - environment includes `HERMES_HOME=/home/konstantin/.hermes`
- Config/state paths:
  - `/home/konstantin/.hermes/config.yaml` exists, mode `0600`, about `16K`
  - `/home/konstantin/.hermes/.env` exists, mode `0600`, about `20K`
  - `/home/konstantin/.hermes/auth.json` exists, mode `0600`, about `8K`
  - `/home/konstantin/.hermes/pairing` exists, about `16K`
  - `/home/konstantin/.hermes/sessions` exists, about `773M`
  - `/home/konstantin/.hermes/memory_store.db` exists, about `1.5M`, SQLite integrity check `ok`
  - `/home/konstantin/.hermes/skills` exists, about `19M`
  - `/home/konstantin/.hermes/plugins` exists, about `29M`
  - `/home/konstantin/.hermes/cron` exists, about `1.4M`
  - `/home/konstantin/.hermes/credentials` exists, about `8K`
  - `/home/konstantin/.hermes/tool-output-artifacts` exists, about `18M`
- Scope guard:
  - keep this runbook focused on the Hermes core install/update model, `HERMES_HOME` state, skills, present plugins, systemd gateway, and existing auth/pairing/session/memory state.
  - retired legacy integrations absent from current Hermes state are out of scope for readiness checks and mandatory backup lists unless explicitly requested.
- Skills:
  - current 0.13 runtime sees local skills and release-bundled skills
  - `/home/konstantin/.hermes/skills`: `101` `SKILL.md` files
  - active release bundled skills: `85` `SKILL.md` files
  - comparison result: `0` bundled release skills are missing from `/home/konstantin/.hermes/skills`
  - `/home/konstantin/.hermes/skills` has `16` extra/custom skills over the bundled set

## Supported install/update models

### Official git install

Official docs describe the one-line Linux/macOS/WSL installer as a git-based install that clones Hermes and tracks `main`:

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

Official update semantics for git installs:

```bash
hermes update
```

The official flow pulls latest code from `main`, updates dependencies, runs config migration prompts, syncs bundled skills, and restarts gateways. Preview mode:

```bash
hermes update --check
```

For git installs, preview fetches and compares against the configured remote branch.

### Official pip install

Official docs describe PyPI releases as tagged major/minor releases, not every commit on `main`.

Preview:

```bash
hermes update --check
```

Upgrade:

```bash
hermes update
```

Manual equivalent:

```bash
pip install --upgrade hermes-agent
# or:
uv pip install --upgrade hermes-agent
```

Important implementation detail verified from `hermes-agent==0.14.0` wheel:

- `detect_install_method()` returns `pip` when the project root has no `.git`.
- `hermes update --check` queries PyPI for pip installs.
- `hermes update` runs a pip/uv upgrade path for pip installs.
- `get_skills_dir()` returns `HERMES_HOME/skills` in 0.14.0.

A temporary non-production venv install was verified:

```text
Hermes Agent v0.14.0 (2026.5.16)
method: pip
recommended_update_command: uv pip install --upgrade hermes-agent
HERMES_HOME: /tmp/hermes-pip-model-0.14.0/home
skills dirs: [/tmp/hermes-pip-model-0.14.0/home/skills]
hermes update --check: ✓ Already up to date.
```

The temporary venv was installed with:

```bash
uv venv /tmp/hermes-pip-model-0.14.0/venv --python 3.11
uv pip install --python /tmp/hermes-pip-model-0.14.0/venv/bin/python \
  'hermes-agent[messaging,mcp,web]==0.14.0'
```

## Can a normal pip venv replace release-dir?

Yes, for the current operating model.

A normal pip venv can run Hermes 0.14.0, detect itself as a pip install, use PyPI-based update checks, and keep the same `HERMES_HOME` state directory. The critical requirement is to keep custom skills/plugins/state outside the venv and backed up.

For this host, the pip install should include at least the extras needed by the production gateway and toolset:

```bash
'hermes-agent[messaging,mcp,web]==0.14.0'
```

Rationale:

- Telegram gateway needs messaging dependencies such as `python-telegram-bot` and `aiohttp`.
- MCP is enabled in config and should remain available.
- Web/dashboard support is cheap to keep if used by gateway/status flows.
- Do not add extras for retired or absent legacy integrations unless current config/state proves they are active.

## What would be lost by removing release-dir

Removing release-dir from the active path would lose these properties:

1. **Atomic full-runtime symlink switch**
   - Current rollback is a single symlink flip from one full source+venv directory to another.
   - Pip target replaces this with venv backup/version pinning or a venv-current symlink strategy.

2. **Immutable per-commit source artifact under `~/.hermes/releases/`**
   - Active runtime would no longer have `release_metadata.json` with a commit hash.
   - Provenance would move to `hermes --version`, `pip show hermes-agent`, PyPI version, and optionally a lock file.

3. **Local full Hermes source tree as the active runtime**
   - `run_agent.py`, `hermes_cli/`, `tools/`, `web/`, `scripts/`, `package.json`, and `package-lock.json` would no longer be active source files.
   - Runtime code would live under venv `site-packages`.

4. **Release-bundled skills path as a fallback scan root**
   - Current 0.13 sees both `/home/konstantin/.hermes/skills` and active release skills.
   - Verified impact is currently zero: all `85` release-bundled skills already exist in `/home/konstantin/.hermes/skills`.

5. **Release-dir-specific operational assumptions**
   - Existing docs and at least one skill script usage example mention `/home/konstantin/.hermes/hermes-agent/skills/...`.
   - These should be migrated to `/home/konstantin/.hermes/skills/...` or to Hermes skill tooling before cutover.

What is **not** lost if backed up correctly:

- config
- `.env`
- auth/pairing
- sessions
- memory store
- custom skills
- plugins
- cron definitions
- credentials metadata/files
- Telegram pairing/auth state

## What risk release-dir originally solved

Release-dir solved the “mixed runtime” risk while Hermes core was patched locally.

Historical failure mode:

- files were copied into a live production directory in pieces;
- `run_agent.py` and support modules came from different code revisions;
- gateway started with an inconsistent module set;
- result was an import/runtime failure.

Release-dir avoided this by building a complete new source+venv tree, smoke-testing it, then switching the active symlink atomically.

## Does that risk still exist?

Mostly no.

The specific risk of local patched core diverging from upstream no longer exists if Hermes core is not modified. The remaining risks are:

- PyPI package upgrade failure inside a venv.
- New upstream config/schema prompts.
- State compatibility after upgrade.
- Custom skills/plugins depending on source-tree paths.
- Running gateway while replacing files in the active venv.

Those should be handled by backups, a staged venv install, explicit systemd cutover, and rollback commands — not by maintaining a custom Hermes core release system.

## Recommended target architecture

```text
/home/konstantin/.hermes/                  # HERMES_HOME, unchanged durable state
  config.yaml
  .env
  auth.json
  pairing/
  sessions/
  memory_store.db
  memories/
  skills/                                  # canonical custom + installed skills
  plugins/
  cron/
  credentials/
  venvs/
    hermes-agent-py311/                    # pip venv, managed by pip/uv
      bin/hermes
      bin/python

/home/konstantin/.local/bin/hermes -> /home/konstantin/.hermes/venvs/hermes-agent-py311/bin/hermes

systemd hermes-gateway:
  WorkingDirectory=/home/konstantin/.hermes
  VIRTUAL_ENV=/home/konstantin/.hermes/venvs/hermes-agent-py311
  ExecStart=/home/konstantin/.hermes/venvs/hermes-agent-py311/bin/python -m hermes_cli.main gateway run --replace
```

Keep the old release directory for rollback until the pip runtime has survived a defined observation window.

## State that must be backed up before migration

Back up these paths before any cutover. Treat optional `HERMES_HOME` subtrees as existence-gated: include them when present in the current state, and do not invent backup paths for retired legacy integrations.

- `/home/konstantin/.hermes/config.yaml`
- `/home/konstantin/.hermes/.env`
- `/home/konstantin/.hermes/auth.json`
- `/home/konstantin/.hermes/pairing/`
- `/home/konstantin/.hermes/profiles/`
- `/home/konstantin/.hermes/sessions/`
- `/home/konstantin/.hermes/memories/`
- `/home/konstantin/.hermes/memory_store.db`
- `/home/konstantin/.hermes/skills/`
- `/home/konstantin/.hermes/plugins/`
- `/home/konstantin/.hermes/cron/`
- `/home/konstantin/.hermes/checkpoints/`
- `/home/konstantin/.hermes/credentials/`
- `/home/konstantin/.hermes/tool-output-artifacts/`
- `/home/konstantin/.hermes/ops/`
- `/home/konstantin/.config/systemd/user/hermes-gateway.service`
- `/home/konstantin/.config/systemd/user/hermes-gateway.service.d/`

Also preserve current rollback artifact:

- `/home/konstantin/.hermes/releases/hermes-agent-d04c50f2f614`

## Future dry-run commands

These commands are intended for a future migration window. They do not switch production by themselves.

```bash
set -euo pipefail
export HERMES_HOME=/home/konstantin/.hermes
export HERMES_VENV="$HERMES_HOME/venvs/hermes-agent-py311"

printf '== active runtime ==\n'
command -v hermes
readlink -f "$(command -v hermes)"
readlink -f "$HERMES_HOME/hermes-agent"
hermes --version

printf '== systemd ==\n'
systemctl --user show hermes-gateway \
  -p LoadState -p ActiveState -p SubState -p ExecStart -p WorkingDirectory -p FragmentPath -p DropInPaths
# Avoid printing full Environment here: future units may contain secret-like values.

printf '== state sizes ==\n'
du -sh \
  "$HERMES_HOME/config.yaml" \
  "$HERMES_HOME/.env" \
  "$HERMES_HOME/auth.json" \
  "$HERMES_HOME/pairing" \
  "$HERMES_HOME/sessions" \
  "$HERMES_HOME/memory_store.db" \
  "$HERMES_HOME/skills" \
  "$HERMES_HOME/plugins" \
  "$HERMES_HOME/cron" \
  "$HOME/.config/systemd/user/hermes-gateway.service" \
  "$HOME/.config/systemd/user/hermes-gateway.service.d"

printf '== sqlite integrity ==\n'
python3 - <<'PY'
import sqlite3
p='/home/konstantin/.hermes/memory_store.db'
con=sqlite3.connect(f'file:{p}?mode=ro', uri=True)
print(con.execute('pragma integrity_check').fetchone()[0])
con.close()
PY

printf '== build candidate pip venv, no cutover ==\n'
rm -rf "$HERMES_VENV.candidate"
uv venv "$HERMES_VENV.candidate" --python 3.11
uv pip install --python "$HERMES_VENV.candidate/bin/python" \
  'hermes-agent[messaging,mcp,web]==0.14.0'
HERMES_HOME="$HERMES_HOME" "$HERMES_VENV.candidate/bin/hermes" --version
HERMES_HOME="$HERMES_HOME" "$HERMES_VENV.candidate/bin/hermes" update --check
HERMES_HOME="$HERMES_HOME" "$HERMES_VENV.candidate/bin/hermes" config check

printf '== skills path hard-code check ==\n'
python3 - <<'PY'
from pathlib import Path
roots=[Path('/home/konstantin/.hermes/skills'), Path('/home/konstantin/src/Hermes-Backup')]
needle='.hermes/hermes-agent'
for root in roots:
    if not root.exists():
        continue
    for p in root.rglob('*'):
        if p.is_file() and p.suffix in {'.md', '.py', '.json', '.yaml', '.yml', '.sh'}:
            try:
                if needle in p.read_text(errors='ignore'):
                    print(p)
            except OSError:
                pass
PY
```

## Future cutover outline

Do not run this without an approved maintenance window.

```bash
set -euo pipefail
umask 077
export HERMES_HOME=/home/konstantin/.hermes
export HERMES_VENV="$HERMES_HOME/venvs/hermes-agent-py311"
export HERMES_BACKUP="$HERMES_HOME/backups/pip-migration-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$HERMES_BACKUP"

printf '== stop gateway ==\n'
systemctl --user stop hermes-gateway

printf '== backup critical state ==\n'
tar --ignore-failed-read -czf "$HERMES_BACKUP/hermes-critical-state.tar.gz" -C /home/konstantin \
  .hermes/config.yaml \
  .hermes/.env \
  .hermes/auth.json \
  .hermes/pairing \
  .hermes/profiles \
  .hermes/sessions \
  .hermes/memories \
  .hermes/memory_store.db \
  .hermes/skills \
  .hermes/plugins \
  .hermes/cron \
  .hermes/checkpoints \
  .hermes/credentials \
  .hermes/tool-output-artifacts \
  .hermes/ops \
  .config/systemd/user/hermes-gateway.service \
  .config/systemd/user/hermes-gateway.service.d

printf '== install pip venv ==\n'
rm -rf "$HERMES_VENV"
uv venv "$HERMES_VENV" --python 3.11
uv pip install --python "$HERMES_VENV/bin/python" \
  'hermes-agent[messaging,mcp,web]==0.14.0'
HERMES_HOME="$HERMES_HOME" "$HERMES_VENV/bin/hermes" --version
HERMES_HOME="$HERMES_HOME" "$HERMES_VENV/bin/hermes" config check

printf '== switch CLI symlink ==\n'
ln -sfn "$HERMES_VENV/bin/hermes" /home/konstantin/.local/bin/hermes

printf '== install systemd pip override ==\n'
mkdir -p /home/konstantin/.config/systemd/user/hermes-gateway.service.d
cat > /home/konstantin/.config/systemd/user/hermes-gateway.service.d/20-pip-venv.conf <<EOF
[Service]
WorkingDirectory=/home/konstantin/.hermes
Environment="PATH=/home/konstantin/.hermes/venvs/hermes-agent-py311/bin:/home/konstantin/.local/bin:/usr/local/bin:/usr/bin:/bin"
Environment="VIRTUAL_ENV=/home/konstantin/.hermes/venvs/hermes-agent-py311"
Environment="HERMES_HOME=/home/konstantin/.hermes"
ExecStart=
ExecStart=/home/konstantin/.hermes/venvs/hermes-agent-py311/bin/python -m hermes_cli.main gateway run --replace
EOF

systemctl --user daemon-reload
systemctl --user start hermes-gateway

printf '== verify ==\n'
systemctl --user is-active hermes-gateway
systemctl --user show hermes-gateway \
  -p ExecStart -p WorkingDirectory -p FragmentPath -p DropInPaths
hermes --version
hermes update --check
```

## Rollback procedure

Rollback to current release-dir runtime, assuming the old release directory is still present.

```bash
set -euo pipefail
export HERMES_HOME=/home/konstantin/.hermes
export OLD_RELEASE="$HERMES_HOME/releases/hermes-agent-d04c50f2f614"

test -d "$OLD_RELEASE"

systemctl --user stop hermes-gateway

# Restore active source symlink and CLI symlink.
ln -sfn "$OLD_RELEASE" "$HERMES_HOME/hermes-agent"
ln -sfn "$OLD_RELEASE/venv/bin/hermes" /home/konstantin/.local/bin/hermes

# Disable pip override while preserving it for audit.
if [ -f /home/konstantin/.config/systemd/user/hermes-gateway.service.d/20-pip-venv.conf ]; then
  mv /home/konstantin/.config/systemd/user/hermes-gateway.service.d/20-pip-venv.conf \
     /home/konstantin/.config/systemd/user/hermes-gateway.service.d/20-pip-venv.conf.disabled-$(date -u +%Y%m%dT%H%M%SZ)
fi

systemctl --user daemon-reload
systemctl --user start hermes-gateway

systemctl --user is-active hermes-gateway
hermes --version
readlink -f "$HERMES_HOME/hermes-agent"
readlink -f "$(command -v hermes)"
```

If rollback is due to corrupted/migrated state, keep gateway stopped and restore the relevant files from `$HERMES_BACKUP/hermes-critical-state.tar.gz` before starting the service.

## Pip-version rollback after migration

If the architecture is already pip-based and only the package version is bad, prefer version pinning over release-dir rollback:

```bash
set -euo pipefail
export HERMES_HOME=/home/konstantin/.hermes
export HERMES_VENV="$HERMES_HOME/venvs/hermes-agent-py311"

systemctl --user stop hermes-gateway
"$HERMES_VENV/bin/python" -m pip install --force-reinstall \
  'hermes-agent[messaging,mcp,web]==0.14.0'
systemctl --user start hermes-gateway
hermes --version
systemctl --user is-active hermes-gateway
```

For future releases, replace `0.14.0` with the last known-good version.

## Open readiness items before actual migration

- Update docs/runbooks that still assume release-dir is the steady-state target.
- Update any active skill/script examples that mention `/home/konstantin/.hermes/hermes-agent/skills/...` to use `/home/konstantin/.hermes/skills/...` or `skill_view`/`skill_manage`.
- Verify the nightly backup job prompt/systemd timer does not instruct agents to avoid supported pip update forever.
- Decide whether to keep a venv backup directory or rely on package version pinning plus state backups.
- Decide the observation window before deleting old `/home/konstantin/.hermes/releases/` artifacts.

## Recommendation

Migrate to supported pip venv, but only after a maintenance-window dry run and a verified backup. Keep the old release directory as rollback until the pip runtime has survived normal Telegram/gateway usage and the next scheduled backup cycle.
