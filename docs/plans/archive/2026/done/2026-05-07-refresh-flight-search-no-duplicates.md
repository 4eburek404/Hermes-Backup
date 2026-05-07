# Plan: refresh flight-search skill and flights CLI with no duplicates

## Status
Completed on 2026-05-07.

## User request
Update the local `flights` CLI and `flight-search` skill from GitHub repository `https://github.com/4eburek404/Hermes`, with `origin/main` updated to `9551041`, and ensure there are no legacy skills or duplicate flight-search skills.

## Source of truth
- Repository: `https://github.com/4eburek404/Hermes.git`
- Branch: `main`
- Verified `origin/main` / `refs/heads/main`: `9551041ed4fde3833a130a21134aeebdd4c9f25d`
- Temporary sparse checkout used for verification: `/tmp/hermes-4eburek404-cli-9551041-FHJU0u` — removed after verification to avoid leaving duplicate source copies.
- Checkout HEAD during verification: `9551041ed4fde3833a130a21134aeebdd4c9f25d`

## Installed state
- Skill: `/home/konstantin/.hermes/skills/productivity/flight-search`
- Legacy duplicate removed: `flight-search-routing`
- CLI source: `[legacy CLI path removed; current source is the development repo skills tree]/flights`
- Executable shim: `/home/konstantin/.local/bin/flights`
- Runtime command: `/home/konstantin/.local/bin/flights`
- CLI version: `flights 0.8.0`
- Python package metadata: `flights-cli 0.8.0`
- Python module version: `0.8.0`
- Python module path: `[legacy CLI path removed; current source is the development repo skills tree]/flights/flights_cli/__init__.py`

## Verification
### GitHub source
- `git ls-remote https://github.com/4eburek404/Hermes.git refs/heads/main` returned `9551041ed4fde3833a130a21134aeebdd4c9f25d`.
- Sparse checkout HEAD equals `9551041ed4fde3833a130a21134aeebdd4c9f25d`.

### Skill inventory / no duplicates
- Disk scan of `/home/konstantin/.hermes/skills/**/SKILL.md` found exactly one flight-related installed skill:
  - name: `flight-search`
  - path: `/home/konstantin/.hermes/skills/productivity/flight-search`
- `flight-search-routing` lookup failed as expected: skill not found.
- `skills_list(category="productivity")` shows `flight-search` and does not show `flight-search-routing`.

### Source parity against GitHub snapshot
- `flights_cli package`: `src_files=37`, `dst_files=37`, `missing=0`, `extra=0`, `different=0`
- `tests`: `src_files=11`, `dst_files=11`, `missing=0`, `extra=0`, `different=0`
- `docs`: `src_files=1`, `dst_files=1`, `missing=0`, `extra=0`, `different=0`
- `flight-search skill`: `src_files=3`, `dst_files=3`, `missing=0`, `extra=0`, `different=0`
- top-level CLI files: `Makefile`, `README.md`, `pyproject.toml` all matched upstream exactly.

### Runtime smoke checks
- `flights --json doctor`: `ok=True`, command `doctor`, version `0.8.0`
- `flights --catalog-refresh never --json route plan SVX LHR --depart-date 2026-07-19 --profile business`: `ok=True`, command `route plan`

### Test suite
- Command: `python3 -m pytest -q [legacy CLI path removed; current source is the development repo skills tree]/flights/tests`
- Result: `66 passed, 9 subtests passed in 4.59s`

## Durable memory/facts
Updated existing fact_store records instead of adding duplicates:
- Fact `157`: `flights` CLI path/source commit/version updated to `9551041ed4fde3833a130a21134aeebdd4c9f25d`.
- Fact `158`: `flight-search` skill path/source commit updated to `9551041ed4fde3833a130a21134aeebdd4c9f25d`; legacy `flight-search-routing` removal recorded.
- Fact `128`: old `flight-search-routing` companion wording replaced with current `flight-search` wording.
- Fact `83`: main Hermes instance inventory updated to say legacy `flight-search-routing` was removed from main.

## Caveats
- `flights` still reports semantic version `0.8.0`; the source commit changed to `9551041ed4fde3833a130a21134aeebdd4c9f25d`.
- Current Telegram session prompt snapshot may still contain the pre-refresh skill list until a fresh session/reset/restart, but live `skill_view`/`skills_list` now see only `flight-search` in productivity.

## Outcome
Done: local skill and CLI are synced from GitHub `main` at `9551041ed4fde3833a130a21134aeebdd4c9f25d`; legacy duplicate `flight-search-routing` is removed; parity, smoke checks, and tests all pass.
