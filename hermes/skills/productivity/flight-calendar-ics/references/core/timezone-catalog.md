# Timezone Catalog

Timezone handling is airport-specific. Do not use one global timezone for all segments and do not add one-off local maps in agent prose.

## Rule

Calendar generation must convert each segment from local airport time to UTC using the bundled airport timezone catalog and explicit overrides where needed.

## Owner surfaces

- Asset: `data/airport-timezones.json`.
- Loader/generator: `scripts/timezone_catalog.py`.
- Diagnostics: `diagnose timezone inspect` and `maint timezone-catalog inspect`.
- Tests: route/bundle/timezone contract tests.

## Operator debugging

Use timezone diagnostics when:

- an airport code is missing from the catalog;
- a city maps to multiple airports;
- UTC duration is impossible;
- a receipt omits the year or mixes local/UTC notation;
- daylight-saving behavior is suspected.

Report metadata only: airport counts, timezone counts, safe sample airport codes, schema version, and missing code names. Do not print private itinerary content.

## Maintenance

Catalog changes need:

1. source asset update;
2. deterministic generation or documented override;
3. tests for affected airports/segments;
4. `maint timezone-catalog inspect` evidence;
5. no runtime sync unless explicitly approved.
