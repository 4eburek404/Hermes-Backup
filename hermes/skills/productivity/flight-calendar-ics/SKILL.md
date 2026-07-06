---
name: flight-calendar-ics
description: Use when creating a compact importable .ics calendar file from a supported airline booking URL or a minimal flight itinerary JSON.
version: 3.04
---

# Flight Calendar ICS

## Goal
Create one importable `.ics` file. This skill does not search flights, compare fares, book tickets, or prove booking validity.

## Decision
Choose exactly one source path:
1. Supported booking/manage URL -> save the URL verbatim in a private text file and use `--url-file`.
2. Existing itinerary JSON -> save it in a private JSON file and use `--input`.
3. Ticket/PDF/email/screenshot/plain text -> convert only visible facts to the minimal JSON template, then use `--input`.
4. Missing required flight facts -> stop and ask for the missing facts; do not guess flight numbers, airports, dates, times, or timezones.

Do not switch to `flight-search` unless the user asked to find or compare flights. This skill starts from an existing booking source or known itinerary.

## Steps
1. Put the source in a private file: booking URL in a text file, or itinerary data in minimal JSON.
2. For a booking URL, run:
   `python "<skill_dir>/scripts/flight_calendar_ics.py" --json build --url-file <private-url-file>`
3. For itinerary JSON, run:
   `python "<skill_dir>/scripts/flight_calendar_ics.py" --json build --input <private-itinerary.json>`
4. Parse the CLI JSON. Success means `ok: true` and a non-empty `media` value.
5. On success, deliver the generated `.ics` using the Telegram order below, then send only a short success reply.
6. On failure, use the sanitized error code/message. For supported-carrier ambiguity, open `references/carriers.md`; if visible itinerary facts are sufficient, fall back to `--input`; otherwise stop.

## Input
- Required: exactly one source, either `--url-file` or `--input`.
- Optional: `--output <path>`, `--no-alarms`, `--tz CODE=Area/City` with `--url-file` only.
- Manual JSON: use `templates/itinerary.example.json`; every flight needs flight number, departure/arrival airports, local datetimes, and IANA timezones.

## Output
- The `.ics` artifact from the CLI `media` value, delivered as a native/downloadable file when the platform supports attachments.
- Short user-facing reply, for example: `Готово: прикрепил .ics для импорта в календарь.`
- Do not paste the raw `.ics`, raw CLI JSON, private source paths, booking URL, or Telegram token.

## Telegram delivery order
1. Extract the absolute `.ics` path from the CLI `media` value (`MEDIA:/abs/file.ics`) and verify it is a regular non-empty file.
2. First try normal gateway delivery: include exactly that `MEDIA:/abs/file.ics` tag in the final Telegram response together with the short success sentence.
3. If Telegram shows the `MEDIA:` tag as plain text, or the user says the attachment did not arrive, do not repeat the same final. Use Telegram Bot API `sendDocument` with the gateway/profile bot token, current `chat_id`, and current Telegram topic/thread metadata when present (`message_thread_id` / reply anchor). Never print the token.
4. Treat direct delivery as complete only after Telegram returns success and a `message_id`; then tell the user briefly that the `.ics` file was sent as a document.

## Check
- CLI output is JSON with `ok: true`.
- CLI output includes `media`.
- The generated artifact is delivered/attachable; if delivery fails, recover delivery before saying it is ready.
- For live carrier smoke tests, wrap the run so stdout/stderr are summarized into redacted fields only (`ok`, `segments_count`, `media`, sanitized error code/message) and explicitly check that private query keys or credential-bearing URL fragments did not print.
- Do not paste booking URLs, PNRs, passenger names, ticket numbers, raw JSON, private paths, Telegram tokens, or `.ics` contents into chat.

## Code-quality / maintenance checks
When modifying this skill's Python code or tests, do not treat `ruff check` as "all linters" by itself. Run and report all three checks explicitly:

```bash
uvx ruff check .
uvx ruff format --check .
python -m pytest tests -q
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

python -m pip install icalendar jsonschema curl_cffi
Use python -m pip, not bare pip.

## Maintenance
Do not run maintenance during normal calendar generation.

If a Hermes runtime is missing `.ics` gateway delivery support after an upstream update, run:

```bash
python "<skill_dir>/scripts/ensure_hermes_ics_delivery.py" --hermes-root "$HOME/.hermes/hermes-agent"
```

The script patches Hermes core delivery allowlists, writes a focused gateway regression test, and runs that test.
