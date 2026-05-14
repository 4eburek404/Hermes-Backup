# Hermes source/runtime file-management model

Session context: Konstantin consolidated Hermes skills/CLI development so there is one source tree and backup stores refs instead of copying runtime state.

## Current source model (release-dir deployment)

### Dual-root architecture

Hermes skills use **two directories** with distinct roles:

1. **Bundled source** — `get_skills_dir()` → `<release>/skills/` (e.g. `~/.hermes/releases/hermes-agent-<hash>/skills/`). Immutable, shipped with the release. Contains 85 bundled SKILL.md files. This is the **source** for `sync_skills()`.

2. **Runtime destination** — `get_skills_state_dir()` → `~/.hermes/skills/`. This is the **canonical runtime directory** where the agent reads skills from, where hub-installed and user-created skills live, and where `sync_skills()` copies bundled skills into.

### How it works

- On gateway startup, `sync_skills()` copies new/updated bundled skills from `<release>/skills/` into `~/.hermes/skills/`, preserving user modifications and respecting local deletions.
- `get_all_skills_dirs()` returns `[state_dir, bundled_dir]` — runtime dir first (user overrides bundled on name conflict).
- Manifest at `~/.hermes/skills/.bundled_manifest` tracks origin hashes for change detection.
- `~/.hermes/skills/` contains both synced bundled skills and user/hub-installed skills.
- Skill-owned CLIs live under their owning skill: `skills/<category>/<skill>/cli/`.

- Removed/obsolete locations that should not be recreated: `/home/konstantin/code/clis`, `~/.hermes/hermes-agent/local/skill-clis`, backup layers such as `cli/skill-clis`, `cli/hermes-agent`, `hermes/skills`.
- `skills.external_dirs` is ignored in this setup.

### Pitfall: release-dir broke sync (fixed May 2026)

When Hermes switched to release-dir deployment (`~/.hermes/hermes-agent` → symlink to `~/.hermes/releases/hermes-agent-<hash>/`), `SKILLS_DIR` in `skills_sync.py` was set to `get_skills_dir()` which now pointed inside the release. Since `_get_bundled_dir()` also pointed to `<release>/skills/`, `sync_skills()` was a no-op (`bundled_dir.resolve() == SKILLS_DIR.resolve()`), and `~/.hermes/skills/` never received any bundled skills. The `.bundled_manifest` became orphaned (hashes for skills that were never copied).

**Fix:** `SKILLS_DIR` in sync/tool modules → `get_skills_state_dir()` (`~/.hermes/skills`). Removed the no-op early-return. `get_all_skills_dirs()` returns `[state_dir, bundled_dir]`. All runtime skill discovery now reads from `~/.hermes/skills/`.

## File-change handling rule

Before editing files under the Hermes source tree:

```bash
git -C ~/.hermes/hermes-agent status --short
git -C ~/.hermes/hermes-agent branch --show-current
git -C ~/.hermes/hermes-agent rev-parse --short HEAD
```

Then inspect the touched path:

```bash
git -C ~/.hermes/hermes-agent diff -- <path>
```

Decision tree:

- Intended source change -> run focused verification -> commit -> push if requested/in scope.
- Accidental change -> discard/restore only after confirming scope.
- Temporary/local-only change -> may remain dirty, but do not describe the environment as fully reproducible from GitHub/backup.
- Runtime/config/secrets/session/log changes -> do not commit; verify through the owning runtime mechanism (`hermes config`, systemd, logs, etc.).

## Backup model

The backup repo is a reference backup, not a clone of all runtime/development files. It stores development references such as `development/hermes-agent.json` pointing to the dev repo. Dirty dev state is intentionally not written or verified by backup. Therefore, any important restoration-critical change must be committed in the active dev repo, not left only as a VPS dirty file.

## Custom skill inventory vs upstream distribution

When asked which skills are Konstantin-local or not part of the Hermes Agent distribution:

1. Work in `~/.hermes/hermes-agent` and verify the current branch/HEAD first.
2. Refresh the comparison ref:

```bash
git fetch upstream main --prune --no-tags
```

3. Compare active local `skills/**/SKILL.md` against `upstream/main:{skills,optional-skills}` by frontmatter `name`. Ignore `.archive/`.
4. Report custom skills separately from custom skills that have an owning `cli/` directory.
5. Use the packaged helper when available:

```bash
python3 skills/autonomous-ai-agents/hermes-agent/scripts/inventory-custom-skills.py --repo ~/.hermes/hermes-agent
```

Pitfall: do not infer "custom" from absence in `~/.hermes/skills` before verifying sync has run; after a fresh release-dir install or update, `~/.hermes/skills/` may be empty until `sync_skills()` runs. Use the packaged helper for comparison against upstream.

## Verification reminders

- `hermes-gateway.service` restart applies gateway/code changes, but tool/skill prompt availability may still require a fresh session or `/reset` because prompts/toolsets can be cached.
- Check scheduled backup separately from manual backup: a manual verifier pass does not prove the timer path works.
- Timer times may be in VPS timezone (e.g. Europe/Amsterdam/CEST), while Konstantin prefers UTC+5; convert explicitly when reporting next runs.
