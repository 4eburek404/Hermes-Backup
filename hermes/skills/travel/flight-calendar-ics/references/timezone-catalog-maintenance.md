# Timezone catalog maintenance

The bundled snapshot is a checked-in fallback. Runtime refresh writes only to the
persistent user cache; normal `flight-calendar` execution never changes the Git
checkout.

## Sources and extraction contract

The canonical upstream source is:

```text
https://api.travelpayouts.com/data/en/airports.json
```

The updater retains only records with:

- `iata_type == "airport"`;
- a valid three-letter IATA code;
- a non-empty `time_zone` accepted by Python `zoneinfo.ZoneInfo`.

`flightable` is recorded for analysis but does not filter airports. Inactive
(`flightable=false`) airports remain eligible for historical or unusual
itineraries. The shared extraction/validation code is used by both runtime
refresh and the explicit updater.

## Explicit bundled snapshot update

From `<skill-root>` run:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/update_airport_timezones.py"
```

The command downloads the source into a temporary area, validates the complete
candidate, and atomically replaces `data/airport-timezones.json` only after
success. Raw upstream JSON is not stored in the repository. Its output is a
short JSON result containing `ok`, `changed`, `timezone_count`, source hashes,
and diff counts. Review the live diff before committing the generated asset.

## Runtime cache and refresh

The persistent runtime cache follows the project convention of a per-skill
writable directory:

```text
~/.hermes/cache/flight-calendar-ics/airport-timezones.json
~/.hermes/cache/flight-calendar-ics/refresh-state.json
~/.hermes/cache/flight-calendar-ics/refresh.lock
```

The refresh age is fifteen days and is measured from the last successful
catalog update, not from a failed attempt. A valid runtime cache younger than
fifteen days is used without network access. If the runtime cache is absent,
the valid bundled snapshot is used as the current checked-in baseline. When the
runtime cache is fifteen days old or older, runtime makes at most one
synchronous fetch of the canonical source. A successful candidate is validated,
atomically written to the runtime cache, and records `last_success`. A failed
attempt leaves the previous cache untouched and falls back first to that cache,
then to the bundled snapshot. If neither local catalog is valid, runtime
performs synchronous recovery and fails closed when recovery fails. The state
file and catalog are written atomically.

The lock protects the check/recheck, refresh, success-state write, download, and
cache replacement critical section across concurrent processes. There is no scheduler
or systemd/cron dependency.
