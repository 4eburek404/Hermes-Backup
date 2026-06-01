# Travelpayouts Airport Timezones

## Lesson

When airline booking data contains IATA airport codes but does not include IANA timezone names, do not grow per-carrier or local fallback maps one airport at a time. Use the skill-bundled Travelpayouts-derived timezone asset at `assets/travelpayouts/airport_timezones.json`.

Observed case: Aeroflot booking `SVO -> KUF -> SVO` initially failed because `KUF` was absent from the small local fallback map. The Travelpayouts airport catalogs already carried `KUF.time_zone = Europe/Samara`, so the durable fix was to bundle a compact provider-neutral timezone asset inside this skill.

## Source priority

Build timezone maps in this order:

```text
skill-bundled Travelpayouts airport timezone asset < explicit --tz override
```

Rationale:

- there is intentionally no local/manual timezone fallback map;
- the bundled Travelpayouts-derived asset has broad airport coverage and avoids one-off local patches while keeping the skill independent of live plugin cache paths;
- `--tz CODE=Area/City` remains the emergency/manual correction path and must win over all defaults.

## Asset generation

The skill keeps only the fields it needs: airport IATA code -> IANA timezone. Rebuild the asset from the Travelpayouts plugin airport cache with:

```bash
python "$SKILL_DIR/scripts/travelpayouts_airport_catalog.py" build \
  --source-dir "$HOME/.hermes/plugins/travelpayouts-flights/cache" \
  --output "$SKILL_DIR/assets/travelpayouts/airport_timezones.json"
```

Inspect the bundled asset with:

```bash
python "$SKILL_DIR/scripts/travelpayouts_airport_catalog.py" inspect
```

## Expected diagnostics

Carrier commands should expose a `load_timezone_map` process step in the JSON envelope, with counts similar to:

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

The exact catalog count may change as the upstream cache changes. The important invariants are `defaults_count == 0`, `catalog_timezones_count > 0`, and explicit overrides win over the asset.

## Future debugging rule

For `missing timezone for airport(s): CODE` failures:

1. Inspect the `load_timezone_map` process step.
2. If `catalog_timezones_count == 0`, repair or rebuild the skill asset from the Travelpayouts airport cache before considering the command usable.
3. If the asset is loaded but the airport is genuinely absent or wrong, verify the IANA timezone from an authoritative airport/geodata source.
4. Rerun once with `--tz CODE=Area/City` to unblock the user.
5. Add a narrow regression for the asset/catalog path; do not add a manual fallback map.

## Regression shape

Useful tests:

- provider helper `DEFAULT_AIRPORT_TZ` maps stay empty;
- the bundled asset includes important historically problematic airports such as `KUF -> Europe/Samara`;
- provider timezone map uses the bundled Travelpayouts asset;
- explicit `--tz` override beats the asset.

## Maintenance verification

After changing the timezone catalog path or provider fallback behavior, run this compact verification bundle before reporting success:

```bash
python tests/test_flight_calendar_ics_cli.py
python scripts/flight_calendar_ics.py --json doctor >/tmp/flight-calendar-ics-doctor.json
python scripts/travelpayouts_airport_catalog.py inspect >/tmp/flight-calendar-ics-catalog-inspect.json
python -m py_compile scripts/flight_calendar_ics.py scripts/travelpayouts_airport_catalog.py scripts/aeroflot_pnr_to_itinerary.py scripts/ural_airlines_to_itinerary.py scripts/utair_to_itinerary.py tests/test_flight_calendar_ics_cli.py
```

Then audit in Python that:

- `DEFAULT_AIRPORT_TZ == {}` for Aeroflot, Ural, and Utair helpers;
- catalog schema is `travelpayouts-airport-timezones.v1`;
- catalog has broad coverage (`len(timezones) > 1000`, currently around 10k);
- `KUF`, `SVO`, and `SVX` resolve to known expected zones;
- an explicit override such as `KUF=Etc/GMT-4` wins over the asset;
- `SKILL.md` and this reference do not still describe the old `local fallback < Travelpayouts < --tz` priority.
