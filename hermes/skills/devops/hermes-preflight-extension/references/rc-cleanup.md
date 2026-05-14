# Release Candidate Cleanup (R14-RC-CLEAN-1)

## Problem

Old release candidates accumulate in `~/.hermes/releases/`, consuming ~300MB each (venv + cache). Near-full disks cause preflight `--replace-rc` to fail silently.

## Solution

`scripts/hermes_release_cleanup.py` — safe RC cleanup script.

### Usage

```bash
# Dry-run (default): show what would be deleted
python scripts/hermes_release_cleanup.py \
  --hermes-home ~/.hermes --keep-latest 2

# Execute: actually delete old RCs
python scripts/hermes_release_cleanup.py \
  --hermes-home ~/.hermes --keep-latest 2 --execute
```

### Safety Guarantees

- **Dry-run by default** — `--execute` required for actual deletion
- **Never deletes active production target** — reads symlink `~/.hermes/hermes-agent`
- **Never deletes dirs without valid `release_metadata.json`** — broken/missing metadata = protected
- **Never deletes dirs where `production_switch=true`** — already deployed releases are protected
- **Never deletes dirs outside `~/.hermes/releases/`**
- **Keeps latest N RCs** — `--keep-latest` (default: 2)
- **Reports estimated bytes to free** before deletion

### Implementation Pattern

- `read_metadata(release_dir)` — parses `release_metadata.json`, returns `None` on missing/broken
- `get_active_target(hermes_home)` — resolves `~/.hermes/hermes-agent` symlink
- `classify_releases(dirs, active_target)` — splits into candidates, protected-no-metadata, protected-active
- `select_for_deletion(candidates, keep_latest)` — sorts by `build_timestamp_utc`, keeps N newest
- `run_cleanup(hermes_home, keep_latest, execute)` — main entry point, returns report dict
- `print_report(report)` — human-readable output
- `format_bytes(num_bytes)` — human-readable size

### Test Pattern

Tests import the script as a module via `importlib.util.spec_from_file_location`:
```python
def _load_module():
    spec = importlib.util.spec_from_file_location("hermes_release_cleanup", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

Test fixtures create fake hermes-home with:
- Active production dir + symlink (`_make_active`)
- RC dirs with valid metadata (`_make_rc`)
- Broken metadata dirs
- Directories that mock production_switch status

### When to Run

Before every full preflight with `--replace-rc`, check disk space:
```bash
df -h / && du -sh ~/.hermes/releases/hermes-agent-*
```

If disk usage > 95%, run cleanup first:
```bash
python scripts/hermes_release_cleanup.py \
  --hermes-home ~/.hermes --keep-latest 1 --execute
```

## History

- R14-RC-CLEAN-1: Created `scripts/hermes_release_cleanup.py` with 29 tests. Freed 611.7 MB from 2 old RCs (e259cbc35a90, 223ce41a4ed8). Later freed 608.8 MB from 2 more old RCs (7b7eb7b9f805, 425c8bddbd9d). Cleanup is now routine before full preflight runs on low-disk systems.