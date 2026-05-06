# flights CLI refactor cache-contract review — 2026-05-06

## Context

During review of backup repo branch `origin/flights-cli-refactor` in `/home/konstantin/code/Hermes`, the refactor split `cli/skill-clis/flights/flights_cli/__main__.py` into layered modules (`cli.py`, `commands/`, `domain/`, `providers/`, `orchestrators/`, `services/`, `store.py`) and added static Travelpayouts catalog refresh/probes.

## Verified commands and findings

Branch inspection:

```bash
git -C /home/konstantin/code/Hermes fetch origin main flights-cli-refactor
git -C /home/konstantin/code/Hermes diff --stat origin/main..origin/flights-cli-refactor
```

Safe review setup:

```bash
tmp=$(mktemp -d /tmp/hermes-flights-cli-refactor.XXXXXX)
git -C /home/konstantin/code/Hermes worktree add --detach "$tmp" origin/flights-cli-refactor
cd "$tmp/cli/skill-clis/flights"
python3 -m pytest -q
```

Observed test result: `37 passed`, `3 failed`. All failures had the same cause:

```text
CliError: no flightable airports found for 'SVX'
```

Root cause: the refactor changed canonical static cache names. Old/local cache had:

- `cities_ru.json`
- `airports.json`
- `airlines.json`

The branch's `Store` reads:

- `cities_ru.json`
- `airports_en.json`
- `airlines_en.json`

With `FLIGHTS_CATALOG_REFRESH=never` in tests, `SVX` resolves as city `Екатеринбург` but with `airports=[]`, breaking `route plan` and `route kb-assemble`.

Runtime default can mask this because `--catalog-refresh auto` downloads new static catalog files. In a clean temp `HOME`, this succeeded:

```bash
HOME="$tmp_home" PYTHONPATH="$PWD" \
python3 -m flights_cli --json --catalog-refresh auto route plan SVX LON \
  --depart-date 2026-07-20 --hub IST --hub DXB
```

Verified output summary:

- `ok=True`
- `origin_airports=['SVX']`
- `destination_airports=['LHR', 'LGW', 'STN', 'LTN']`
- `segment_request_count=10`
- `catalog_auto_refresh.refreshed=True`
- `updated_count=10`

## Review conclusions to reuse

Blocking before merge:

1. Preserve legacy cache compatibility: `airports_en.json` should fall back to `airports.json`; `airlines_en.json` should fall back to `airlines.json`, or a migration/alias should be provided.
2. Tests should be hermetic: seed temp cache fixtures or support an env override such as `FLIGHTS_CACHE_DIR`; do not rely on the user's real `~/.hermes/plugins/travelpayouts-flights/cache`.
3. Offline-first behavior should degrade gracefully: if auto-refresh fails but stale/legacy usable cache exists, use it with a warning rather than failing catalog-dependent commands.
4. README/doctor wording must distinguish no booking/no live price API from static catalog refresh: catalog-dependent commands may make no-token static Travelpayouts requests and write cache by default.

## Pitfall

Do not conclude `route plan` is purely offline/no-write if `--catalog-refresh auto` is default. With missing/stale static catalog, it can perform static catalog network requests and write files before planning. For offline validation, force `--catalog-refresh never` and provide a hermetic cache fixture.