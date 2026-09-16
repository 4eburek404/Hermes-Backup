---
name: flight-calendar-ics
description: Use when creating a compact importable .ics calendar file from a supported airline booking URL or a minimal flight itinerary JSON.
version: 3.03
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
0. Before touching any tool, choose the source path: the CLI `build` command below is the default first action for booking URLs and needs no browser. A booking URL is stored in a private file and read with `--url-file` (the CLI resolves carrier redirects itself). For a PDF, first convert it with `anydoc` to Markdown; if the PDF is scanned or `anydoc` returns no usable text, render its pages with PyMuPDF and run Tesseract OCR, then build the minimal itinerary JSON from the extracted text and read it with `--input`. Read `references/carriers.md` first for URL sources and `templates/itinerary.example.json` first for PDF/JSON sources.
1. Put the source in a private file: booking URL in a text file, or minimal itinerary JSON produced from the PDF's AnyDoc text or OCR text.
2. For a booking URL, run:
   `"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/flight_calendar_ics.py" --json build --url-file <private-url-file>`
3. For a PDF source, use this extraction order:
   - First run `npx -y @firecrawl/anydoc <file.pdf> -o <private-markdown-file>`.
   - If the output is empty, unsupported, or the pages are image-only, render the pages with PyMuPDF and OCR each rendered page with Tesseract (`rus+eng` for Russian tickets and Latin airport/flight codes).
   - Map the resulting text into the minimal JSON shape in `templates/itinerary.example.json`; do not send raw Markdown or raw OCR directly to the calendar CLI.
4. For itinerary JSON, run:
   `"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/flight_calendar_ics.py" --json build --input <private-itinerary.json>`
5. If the result has `ok: true`, return the `media` value and a short success reply.

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
- PDF-to-Markdown conversion requires Node.js 20+ and `npx`; `anydoc` does not perform OCR.
- OCR fallback requires PyMuPDF for PDF page rendering and the Tesseract executable with the needed language packs (normally `rus` and `eng`).
- If the CLI fails with ModuleNotFoundError, install dependencies into the same Python interpreter used for the CLI:

"${HERMES_SKILLS_PYTHON:-python3}" -m pip install icalendar jsonschema curl_cffi
Use the selected interpreter with `-m pip`, not bare `pip`.

## Maintenance
Do not run maintenance during normal calendar generation.

If a Hermes runtime is missing `.ics` gateway delivery support after an upstream update, run:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/ensure_hermes_ics_delivery.py" --hermes-root "$HOME/.hermes/hermes-agent"
```

The script patches Hermes core delivery allowlists, writes a focused gateway regression test, and runs that test.
