# Hermes 0.13 active update results

Recorded: 2026-05-10 12:47 +05

## Source / git

Primary checkout:

```text
repo=/home/konstantin/.hermes/hermes-agent
branch=main
HEAD=e0d5636c93d31d17fcd52ef79ea72fff32680b66
status=## main...origin/main
origin=https://github.com/4eburek404/Hermes-fork-development.git
upstream=https://github.com/NousResearch/hermes-agent.git
```

Integration commits:

```text
851b10e82fbf docs: preserve pre-update skill maintenance notes
288cb8d748b6 chore: sync Hermes to v2026.5.7
01c21ebfc762 docs: preserve pre-update Hermes skill notes
e0d5636c93d3 chore: update Hermes to v2026.5.7
```

Push:

```text
git push origin main
result=pass
remote_update=2cdb54d22..e0d5636c9 main -> main
```

## Version / install verification

```text
pyproject_version=0.13.0
package_version=0.13.0
hermes --version=Hermes Agent v0.13.0 (2026.5.7)
python=/home/konstantin/.hermes/hermes-agent/venv/bin/python
hermes_entrypoint=/home/konstantin/.local/bin/hermes
```

Install command:

```text
uv pip install --python venv/bin/python -e '.[all]'
```

Install result:

```text
hermes-agent 0.11.0 -> 0.13.0
new deps: aiohttp-socks==0.11.0, python-socks==2.8.1, vercel==0.5.8
import_hermes_cli_main=ok
```

## Verification gates

Final integration worktree:

```text
/tmp/hermes-013-final-integration-20260510-123808
branch=sync/hermes-013-final-20260510-123808
```

Checks:

```text
unmerged=0
unstaged=0
untracked=0
exact conflict marker scan=0
py_compile=pass
focused pytest=258 passed in 7.07s
selected broader pytest=240 passed in 108.07s
```

Focused pytest covered curator, skill usage, external skill policy, skill manager external mutation policy, and Hermes CLI command surfaces.

Selected broader pytest covered skill commands/reload, gateway reload/help/update paths, and Hermes CLI update/autostash/gateway-restart/update-yes paths.

## Policy decisions preserved

```text
source/authored skills remain under Hermes Agent checkout skills/
runtime/user skill state remains under ~/.hermes/skills
skills.external_dirs remains ignored by this fork
```

## Runtime restart note

Gateway process observed before restart request:

```text
systemd_user_unit=hermes-gateway.service active/running
process=/home/konstantin/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run --replace
```

Because the current Telegram turn is running inside the gateway process, immediate `systemctl --user restart hermes-gateway.service` would kill the active agent mid-report. The old running gateway process was started from the pre-update code path, and the old revisions checked (`851b10e82fbf`, `01c21ebfc762`, `2cdb54d2236b`) do not contain the newer SIGUSR1/self-restart implementation. Therefore the safe runtime path is a delayed user-systemd restart after the final update report has time to leave Telegram, followed by a post-restart Telegram smoke message from a transient systemd unit.
