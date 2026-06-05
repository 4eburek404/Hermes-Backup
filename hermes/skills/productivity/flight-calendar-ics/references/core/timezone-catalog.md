# Timezone Catalog

This file owns timezone resolution for `flight-calendar-ics` when booking data contains IATA airport codes but no IANA timezone names. It does not own carrier parsing or event wording.

## Rule

Do not grow per-carrier or local fallback maps one airport at a time. Use the skill-bundled Travelpayouts-derived timezone asset:

```text
assets/travelpayouts/airport_timezones.json
```

Source priority:

```text
skill-bundled Travelpayouts airport timezone asset < explicit --tz override
```

Rationale:

- there is intentionally no local/manual timezone fallback map;
- the bundled asset has broad airport coverage and avoids one-off patches while keeping the skill independent of live plugin cache paths;
- `--tz CODE=Area/City` remains the emergency/manual correction path and must win over all defaults.

## Asset generation

The skill keeps only the fields it needs: airport IATA code → IANA timezone.

Rebuild the asset from the Travelpayouts plugin airport cache:

```bash
python "$SKILL_DIR/scripts/travelpayouts_airport_catalog.py" build \
  --source-dir "$HOME/.hermes/plugins/travelpayouts-flights/cache" \
  --output "$SKILL_DIR/assets/travelpayouts/airport_timezones.json"
```

Inspect the bundled asset:

```bash
python "$SKILL_DIR/scripts/travelpayouts_airport_catalog.py" inspect
```

## Expected diagnostics

Carrier commands should expose a `load_timezone_map` process step in the JSON envelope, with fields like:

```json
{
  "step": "load_timezone_map",
  "status": "ok",
  "defaults_count": 0,
  "catalog_source": "skill-bundled-travelpayouts-airport-timezones",
  "catalog_timezones_count": 10216,
  "overrides_count": 0
}
```

The exact catalog count may change as upstream cache changes. Invariants:

- `defaults_count == 0`;
- `catalog_timezones_count > 0`;
- explicit overrides win over the asset.

## Missing timezone debugging

For `missing timezone for airport(s): CODE` failures:

1. Inspect the `load_timezone_map` process step.
2. If `catalog_timezones_count == 0`, repair or rebuild the skill asset from the Travelpayouts airport cache before considering the command usable.
3. If the asset is loaded but the airport is genuinely absent or wrong, verify the IANA timezone from an authoritative airport/geodata source.
4. Rerun once with `--tz CODE=Area/City` to unblock the user.
5. Add a narrow regression for the asset/catalog path; do not add a manual fallback map.

## Regression shape

Useful tests:

- the bundled asset includes important historically problematic airports such as `KUF -> Europe/Samara`;
- `build_timezone_map(..., catalog_path=sentinel_catalog)` returns timezone values from that catalog path and still lets explicit `--tz` overrides win;
- provider command/helper tests inject a sentinel `airport_catalog.load_airport_timezones()` map, then assert the saved canonical itinerary `departure.tz`/`arrival.tz` and any UTC `.ics` timestamps reflect the sentinel catalog values;
- do not preserve long-lived absence tests for retired internal names such as deleted fallback-map shims.

## Maintenance verification

After changing timezone catalog path or provider fallback behavior, run a compact verification bundle:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_flight_calendar_ics_cli
python scripts/flight_calendar_ics.py --json doctor >/tmp/flight-calendar-ics-doctor.json
python scripts/travelpayouts_airport_catalog.py inspect >/tmp/flight-calendar-ics-catalog-inspect.json
python -m py_compile scripts/flight_calendar_ics.py scripts/travelpayouts_airport_catalog.py scripts/aeroflot_pnr_to_itinerary.py scripts/ural_airlines_to_itinerary.py scripts/utair_to_itinerary.py scripts/redwings_to_itinerary.py tests/test_flight_calendar_ics_cli.py
```

Then audit that:

- catalog schema is `travelpayouts-airport-timezones.v1`;
- catalog has broad coverage (`len(timezones) > 1000`);
- `KUF`, `SVO`, and `SVX` resolve to known expected zones;
- an explicit override such as `KUF=Etc/GMT-4` wins over the asset;
- `../../SKILL.md` and references do not describe the old `local fallback < Travelpayouts < --tz` priority.
