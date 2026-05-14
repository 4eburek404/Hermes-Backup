# Skills dual-root fix (May 2026)

## Problem

After switching to release-dir deployment (`~/.hermes/hermes-agent` → symlink to `~/.hermes/releases/hermes-agent-<hash>/`), runtime skill discovery broke: `~/.hermes/skills/` was empty (0 SKILL.md files) despite 97 bundled skills existing in the release.

## Root cause

`SKILLS_DIR` in `tools/skills_sync.py` was set to `get_skills_dir()` which resolved to `<release>/skills/`. `_get_bundled_dir()` also resolved to `<release>/skills/`. The sync check `bundled_dir.resolve() == SKILLS_DIR.resolve()` made `sync_skills()` a no-op. Bundled skills were never copied to `~/.hermes/skills/`.

The `.bundled_manifest` at `~/.hermes/skills/.bundled_manifest` contained 97 origin hashes but the corresponding skill files never existed on disk — the manifest was orphaned.

`get_all_skills_dirs()` returned only `[get_skills_dir()]` (release/skills), so runtime discovery never saw `~/.hermes/skills/`.

## Fix (9 source files + test file patched)

| File | Change |
|------|--------|
| `hermes_constants.py` | Clarified docs: `get_skills_dir()` = bundled source, `get_skills_state_dir()` = runtime destination |
| `tools/skills_sync.py` | `SKILLS_DIR = get_skills_state_dir()`; removed no-op early-return when source==dest |
| `agent/skill_utils.py` | `get_all_skills_dirs()` → `[get_skills_state_dir(), get_skills_dir()]`; added import |
| `agent/prompt_builder.py` | `get_skills_dir()` → `get_skills_state_dir()` for scan/snapshot |
| `tools/skills_tool.py` | `SKILLS_DIR = get_skills_state_dir()` |
| `tools/skill_manager_tool.py` | `SKILLS_DIR = get_skills_state_dir()` |
| `tools/skills_hub.py` | `SKILLS_DIR = get_skills_state_dir()` |
| `tools/credential_files.py` | `get_skills_dir()` → `get_skills_state_dir()` for container mounts |
| `tools/skill_usage.py` | `_skills_dir()` → `get_skills_state_dir()` |
| `tests/tools/test_skills_sync_release_dir.py` | 16 new tests: sync, preservation, reset, stale manifest recovery, immutability, architecture |

## Key design decisions

- `get_skills_dir()` = bundled source inside release; used by `_get_bundled_dir()` for sync source
- `get_skills_state_dir()` = `~/.hermes/skills/` = runtime destination; all skill discovery, install, and runtime reads
- `get_all_skills_dirs()` returns [state_dir, bundled_dir] — state_dir first so user modifications override bundled
- `sync_skills()` copies FROM bundled TO state_dir; no longer a no-op
- User modifications preserved (hash-based change detection via manifest)
- Local deletions respected (skill in manifest but absent from disk → skip)
- Stale manifest blocks fresh sync → recovery: delete manifest, let sync repopulate

## Test coverage (all passed)

| Scenario | Status |
|----------|--------|
| `get_all_skills_dirs()` returns 2 directories, state_dir first | PASSED |
| Fresh sync copies all bundled skills to state_dir | PASSED |
| DESCRIPTION.md files copied | PASSED |
| Origin hashes recorded in manifest | PASSED |
| Second sync is no-op (unchanged) | PASSED |
| Existing user skill not overwritten | PASSED |
| Modified bundled skill not overwritten | PASSED |
| Deleted bundled skill respected | PASSED |
| `reset --restore` re-copies from bundled | PASSED |
| Stale manifest blocks sync (intentional) | PASSED |
| Removing stale manifest enables fresh sync | PASSED |
| `get_skills_dir() != get_skills_state_dir()` (immutability) | PASSED |
| `_compute_relative_dest` uses SKILLS_DIR | PASSED |

## Validation (live)

- `sync_skills()`: 96 copied, 1 skipped (ocr-and-documents: existing local)
- `find ~/.hermes/skills -name 'SKILL.md' | wc -l` → 96
- Combined discovery: State 96 + Bundled 97 = 97 unique
- `hermes skills list` → 92 builtin, 0 local

## Commit & deploy

- Commit: `fe6dbf61` on `4eburek404/Hermes-fork-development` (main)
- Merged upstream: `7e4f973 → fe6dbf6` (rebased on `33bcc95`)
- Release candidate: `~/.hermes/releases/hermes-agent-fe6dbf61/` (created, smoke-tested)
- Production switch: symlink `~/.hermes/hermes-agent → releases/hermes-agent-fe6dbf61` + `systemctl --user restart hermes-gateway` — pending explicit approval

## Recovery from stale manifest after release-dir migration

If `~/.hermes/skills/` has only dotfiles but no SKILL.md files, and manifest is stale:
```bash
# Backup manifest, remove it, re-sync
cp ~/.hermes/skills/.bundled_manifest ~/.hermes/skills/.bundled_manifest.stale-backup
rm ~/.hermes/skills/.bundled_manifest
# Then restart gateway or run sync_skills() manually
```

## Diagnostic commands

```bash
# Verify architecture
PYTHONPATH=. python3 -c "from agent.skill_utils import get_all_skills_dirs; print(get_all_skills_dirs())"

# Check sync state
PYTHONPATH=. python3 -c "from tools.skills_sync import SKILLS_DIR, _get_bundled_dir; print('SKILLS_DIR:', SKILLS_DIR); print('bundled:', _get_bundled_dir()); print('same?', _get_bundled_dir().resolve() == SKILLS_DIR.resolve())"

# Count skills in each root
find ~/.hermes/skills -maxdepth 3 -name 'SKILL.md' | wc -l

# Check manifest health
wc -l ~/.hermes/skills/.bundled_manifest
```
