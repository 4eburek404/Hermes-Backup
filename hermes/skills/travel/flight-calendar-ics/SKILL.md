---
name: flight-calendar-ics
description: Use when creating a compact importable .ics calendar file from a supported airline booking URL or a minimal flight itinerary JSON.
version: 3.02
metadata:
  hermes:
    category: travel
    tags: [travel, flights, calendar, ics]
---

# Flight Calendar ICS

Treat the directory containing this `SKILL.md` as `<skill-root>` and resolve
every bundled path relative to it.
Use `"${HERMES_SKILLS_PYTHON:-python3}"` as the Python interpreter for bundled
commands. When `HERMES_SKILLS_PYTHON` is set, use that exact executable;
otherwise use `python3`.

## Goal
Create one importable `.ics` file for flight calendar import using cli

## Steps
1. Put the source in a private file: booking URL in a text file, or itinerary data in minimal JSON.
2. For a booking URL, run:
   `"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/flight_calendar_ics.py" --json build --url-file <private-url-file>`
3. For itinerary JSON, run:
   `"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/flight_calendar_ics.py" --json build --input <private-itinerary.json>`
4. If the result has `ok: true`, return the `media` value and a short success reply.

## Input
- Required: exactly one source, either `--url-file` or `--input`.
- Optional: `--output <path>`, `--no-alarms`, `--tz CODE=Area/City` with `--url-file` only.
- For manual JSON, use `templates/itinerary.example.json`.

## Output
- The `.ics` artifact from the CLI `media` value.
- Short user-facing reply, for example: `Готово: прикрепил .ics для импорта в календарь.`

## Check
- CLI output is JSON with `ok: true`.
- CLI output includes `media`.
- For live carrier smoke tests, wrap the run so stdout/stderr are summarized into redacted fields only (`ok`, `segments_count`, `media`, sanitized error code/message) and explicitly check that private query keys or credential-bearing URL fragments did not print.
- Do not paste booking URLs, PNRs, passenger names, ticket numbers, raw JSON, private paths, or `.ics` contents into chat.

## Code-quality / maintenance checks
When modifying this skill's Python code or tests, do not treat `ruff check` as "all linters" by itself. Run and report all three checks explicitly:

```bash
uvx ruff check .
uvx ruff format --check .
"${HERMES_SKILLS_PYTHON:-python3}" -m pytest tests -q
```

If `ruff check` reports dead code such as `F401` unused imports or `F841` unused assignments, remove it without asking for separate approval. If `ruff format --check` fails, expect a potentially large formatter-only diff; ask before applying broad formatting unless the user already requested all lint/format gates to pass.

## Stop
- Stop if the source is missing required flight data.
- Stop after success; do not open, inspect, validate, rewrite, or rebuild the generated `.ics`.

## References
- `templates/itinerary.example.json` — open when converting tickets, PDFs, emails, screenshots, or manual segments to canonical itinerary JSON.
- `references/carriers.md` — open when checking supported booking URL routes, carrier notes, or transport dependencies.

## Dependencies
If the CLI fails with ModuleNotFoundError, install dependencies into the same Python interpreter used for the CLI:

"${HERMES_SKILLS_PYTHON:-python3}" -m pip install icalendar jsonschema curl_cffi
Use the selected interpreter with `-m pip`, not bare `pip`.

## Maintenance
Do not run maintenance during normal calendar generation.

If a Hermes runtime is missing `.ics` gateway delivery support after an upstream update, run:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/ensure_hermes_ics_delivery.py" --hermes-root "$HOME/.hermes/hermes-agent"
```

The script patches Hermes core delivery allowlists, writes a focused gateway regression test, and runs that test.
