# Multi-Instance Infrastructure Notes

Volatile reference for Hermes instance/source/runtime inventory. Use this only as a routing hint; re-verify paths, processes, Docker containers, and active config before making current-state claims.

## Why this is a reference

The main `knowledge-architecture/SKILL.md` should stay a compact router. Instance inventory drifts quickly and can be wrong if kept as always-loaded skill prose. This file preserves the check pattern and last verified evidence without treating it as permanent truth.

## Last verified evidence

Checked on 2026-05-08 during P1 skill shrink:

- Branch context: `/home/konstantin/.hermes/hermes-agent`, branch `fix/ollama-native-auxiliary-routing`, HEAD `6ac6367f196e`.
- Main Hermes data path exists: `/home/konstantin/.hermes`.
- Main editable skill source exists: `/home/konstantin/.hermes/hermes-agent/skills`.
- Historical guest data path did **not** exist at check time: `/home/konstantin/hermes-instances/guest/data`.
- Historical guest skill path did **not** exist at check time: `/home/konstantin/hermes-instances/guest/data/skills`.
- `docker ps` returned no relevant `hermes`/`guest` container names at check time.

Interpretation: previous main-skill prose claiming an active guest instance was not current on this machine at the time of the P1 refactor. Treat guest-instance notes as historical unless a fresh check proves otherwise.

## Re-check recipe

```bash
python3 - <<'PY'
from pathlib import Path
import json, subprocess
paths = {
  'main_data': Path('/home/konstantin/.hermes'),
  'main_skill_source': Path('/home/konstantin/.hermes/hermes-agent/skills'),
  'guest_data': Path('/home/konstantin/hermes-instances/guest/data'),
  'guest_skill_source': Path('/home/konstantin/hermes-instances/guest/data/skills'),
}
out = {
  'paths': {k: str(v) for k, v in paths.items()},
  'exists': {k: v.exists() for k, v in paths.items()},
}
try:
    p = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], text=True, capture_output=True, timeout=15)
    out['docker_ps_rc'] = p.returncode
    out['docker_names_relevant'] = [n for n in p.stdout.splitlines() if 'hermes' in n.lower() or 'guest' in n.lower()]
except Exception as exc:
    out['docker_error'] = type(exc).__name__ + ': ' + str(exc)
print(json.dumps(out, ensure_ascii=False, indent=2))
PY
```

## Pitfalls

- `skills_list` shows the current Hermes instance only; it is not proof that another instance lacks a skill.
- A historical path in docs/skills is not proof that the path exists now.
- A successful read from one instance does not prove another instance shares memory, skills, config, credentials, or runtime state.
- Do not update `USER.md`, `MEMORY.md`, or `SOUL.md` with instance inventory unless the user approves a specific diff.
