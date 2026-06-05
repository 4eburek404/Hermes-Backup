---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.5.1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, redwings, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

## Purpose

Create an importable `.ics` from flight evidence.

Normal generation is one CLI-owned command:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
```

`build auto` means the CLI selects the route. The current route rule is known-host-first: if the input URL contains a known carrier host, that host locks the carrier namespace before generic field names are considered. Generic fields such as PNR/surname must not override a known host.

## When to Use

Use this skill for airline booking links, ticket PDFs, route receipts, emails, screenshots, pasted flight segments, or canonical itinerary JSON.

Do not use it for flight search, fare comparison, or route planning; load `flight-search`. If the user wants direct Google Calendar insertion, first generate/validate the itinerary here, then load `google-workspace`.

## Golden Path

1. **Keep evidence private.** If the source is a credential-bearing carrier URL, store it in a private file and pass it with `--url-file`. Do not print, read back, summarize, or grep the URL or generated `.ics` content.

2. **Run exactly one generation command.** Let the CLI infer the route, create the private bundle, choose artifact names, and verify the calendar.

   ```bash
   SKILL_DIR='<skill_dir returned by skill_view>'
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
   ```

   Keep path variables on separate assignment/export lines, or pass literal absolute paths. Do not use same-line temporary assignments such as `SKILL_DIR=... python <quoted $SKILL_DIR path>`; POSIX shells expand command words before those temporary assignments are visible, which can turn the CLI path into `/scripts/flight_calendar_ics.py`.

   For canonical itinerary JSON:

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --input /private/itinerary.json
   ```

   Do not run `doctor`, read carrier references, inspect CLI source, add `mktemp`, `chmod`, `tee`, `--output-json`, `--output-ics`, or stdout redirection on a successful happy path. `--output-dir` is only for reproducible diagnostics/tests or an explicit user-selected destination.

3. **Verify the envelope, then send.** Parse stdout or `data.envelope_path`; require:
   - `schema_version=flight-calendar-ics-cli.v1`
   - `ok=true`
   - `command=build`
   - `data.segments_count >= 1`
   - `data.ics_path` exists
   - `data.verification.ok=true`

   Then respond with `MEDIA:/absolute/path/flights.ics` and a short operational summary. Do not include PNR keys, full booking URLs, passenger names, ticket/document/contact/payment data, generated API headers, bearer tokens, or access keys in chat.

## Non-Happy Path

Use diagnostics only when the one-command path fails or the operator explicitly asks for diagnostics/evaluation:

- CLI `ok=false`: use the JSON error code to fix the selected source; switch routes only after new evidence.
- Unknown carrier or manual data: normalize to canonical itinerary JSON and run `build make`.
- Local airline receipt PDF feature: extract only calendar-safe operational fields with PyMuPDF/OCR, verify ambiguous city→airport mapping when needed, write private canonical JSON, then run `--json build make --input /private/itinerary.json`. See `references/core/pdf-receipt-normalization.md`.
- Explicit carrier command (`build aeroflot|ural|utair|redwings`) is for diagnostics/tests or a deliberate user/operator choice, not the default.
- `doctor` is a diagnostic runbook, not a route-selection step. Do not run it merely because this is an evaluation; run it only when the evaluation specifically measures diagnostics or the CLI contract is unknown.

## Maintenance References

Open these only when changing or debugging that layer:

- `references/registry.md` — owner map for references.
- `references/core/cli-contract.md` — JSON envelope, `doctor`, process traces, schema contract.
- `references/core/auto-route-dispatch.md` — `build auto`, known-host-first route inference, ambiguity errors.
- `references/core/canonical-itinerary.md` — provider-agnostic manual JSON input.
- `references/core/calendar-event-format.md` — `.ics` text layout.
- `references/core/manual-source-extraction.md` — PDF/email/screenshot/manual extraction.
- `references/core/pdf-receipt-normalization.md` — local airline receipt PDF normalization feature: PyMuPDF/OCR extraction → privacy-safe canonical itinerary JSON → `build make`.
- `references/core/timezone-catalog.md` — airport timezone asset and overrides.
- `references/core/privacy-hardening.md` — redaction tests, private artifact permissions, exact sentinel checks.
- `references/core/output-bundle-design.md` — CLI-owned private output bundle.
- `references/maintenance/source-runtime-sync.md` — source↔runtime parity and commit evidence.
- `references/maintenance/dead-code-and-contract-cleanup.md` — cleanup audit for dead code, legacy shims, stale tests, generated artifacts, registry gaps, and source/runtime drift.
- `references/maintenance/model-evaluation.md` — cross-model eval harness rules; evaluation still uses the one-command happy path unless diagnostics are explicitly under test.
- `references/maintenance/eval-provider-and-shell-pitfalls.md` — provider identity/fallback and shell path pitfalls observed in cross-model evals.
- Carrier refs only for carrier-specific fixes: `references/carriers/aeroflot.md`, `references/carriers/ural-airlines.md`, `references/carriers/utair.md`, `references/carriers/redwings.md`.

## Common Pitfalls

1. Re-asking for data already supplied in an attachment/cache.
2. Treating `doctor` as mandatory for obvious carrier URLs.
3. Leaving route dispatch to the agent instead of running `build auto`.
4. Trying several carrier helpers opportunistically instead of letting the CLI return an ambiguity/error envelope.
5. Scraping airline manage-booking pages or helper stdout instead of using the CLI envelope.
6. Reintroducing agent-owned output plumbing on the happy path.
7. Sending the `.ics` before checking `data.verification.ok=true`.
8. Dumping private URL or `.ics` content into model-visible output.
9. Using one timezone for all airports or adding local one-off timezone maps.
10. Reading source, carrier docs, or generated `.ics` after a successful `build auto` envelope.
11. Using same-line temporary shell assignments with `$SKILL_DIR` in the command path; assign/export first or use literal absolute paths.

## Verification Checklist

- [ ] Source stayed private or was normalized manually.
- [ ] Happy path used exactly one `--json build auto ...` command.
- [ ] No `doctor`, source reading, carrier reference reading, or generated `.ics` dump after successful `build auto`.
- [ ] Envelope passed: schema version, `ok=true`, `command=build`, route, segment count, `data.verification.ok=true`.
- [ ] `data.ics_path` exists and final response sends it as `MEDIA:/absolute/path/flights.ics` without private identifiers.
