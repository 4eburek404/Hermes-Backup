---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.5.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, redwings, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

## Overview

Create an importable `.ics` from flight evidence. The normal path is the single CLI-owned bundle command:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto ...
```

Do not reason through carrier APIs in `SKILL.md`. Let the CLI infer the route from a safe source fingerprint on the happy path; use `doctor` only for ambiguity, failures, evaluation, capability discovery, or maintenance.

## When to Use

Use this skill for airline booking links, ticket PDFs, route receipts, emails, screenshots, pasted flight segments, or canonical itinerary JSON.

Do not use it for flight search, fare comparison, or route planning; load `flight-search`. If the user wants direct Google Calendar insertion, first generate/validate the itinerary here, then load `google-workspace`.

## Golden Path

1. **Prepare evidence and choose the shortest safe dispatch.** If the user already sent a PDF/email/screenshot/link in this conversation, inspect or reuse that source before asking again for PNR, surname, route, or times. For credential-bearing carrier URLs, prefer a private input file and pass it with `--url-file` when practical.

   If the source can be fingerprinted locally (for example a carrier URL or a known canonical itinerary JSON), run `build auto`; do **not** force a `doctor` call merely to rediscover an obvious route. Use explicit `build <route>` only for diagnostics/tests or when the user has deliberately selected a route. Use `doctor` only when route/capability is ambiguous, the CLI contract is unknown, a previous build failed, or you are doing evaluation/maintenance.

   ```bash
   SKILL_DIR='<skill_dir returned by skill_view>'
   # Optional diagnostic/runbook source, not mandatory for obvious happy paths:
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json doctor
   ```

2. **Run exactly one CLI-owned generation command.** Default to `build auto` so the CLI owns route selection. Use explicit routes only for diagnostics/tests or after an explicit user/operator choice. Let the CLI create the private bundle, choose artifact names, write `itinerary.json`/`flights.ics`/`envelope.json`, and verify the calendar before returning `ok=true`.

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto ...
   ```

   Typical route shapes:

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --input /private/itinerary.json
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build make --input /private/itinerary.json
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build aeroflot --url-file /private/source-url.txt
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build ural --url-file /private/source-url.txt
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build utair --url-file /private/source-url.txt
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build redwings --url-file /private/source-url.txt
   ```

   Do not add shell-owned `mktemp`, `chmod`, `--output-json`, `--output-ics`, `tee`, or stdout redirection for normal generation. `--output-dir` is only for tests, reproducible diagnostics, cron artifacts, or an explicit user-selected destination.

   If no carrier route fits but flight facts are known, normalize to canonical itinerary JSON (`references/core/canonical-itinerary.md`) and run `build make`.

3. **Verify envelope and send.** Parse stdout or `data.envelope_path`; require `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, `command=build`, `data.segments_count >= 1`, `data.ics_path`, and `data.verification.ok=true`. Then respond with `MEDIA:/absolute/path/flights.ics` and a safe operational summary only.

Privacy: never print PNR keys, full booking URLs, passenger names, ticket/document/contact/payment data, generated API headers, bearer tokens, or access keys in chat. Those may exist only inside the requested private artifact.

Trajectory privacy: avoid pulling private booking inputs or generated `.ics` contents into model-visible tool output. Prefer passing credential URLs to the CLI from a private file; avoid `cat`, `read_file`, or grep commands that emit full `.ics` `SUMMARY`/`DESCRIPTION` lines. Trust `data.verification.ok=true` for structural `.ics` checks instead of dumping calendar content.

## Failure / Maintenance Gate

- CLI `ok=false`: fix the selected route/source from the JSON error. Switch routes only after new explicit evidence.
- Unknown carrier or manual data: use canonical itinerary JSON + `build make`.
- PDF/document extraction ambiguity: open `references/core/manual-source-extraction.md`.
- Missing timezone/catalog issue: open `references/core/timezone-catalog.md`; prefer bundled asset or explicit `--tz`, not local fallback maps.
- Event wording/layout change: open `references/core/calendar-event-format.md` and update renderer tests first.
- Carrier/API/CLI contract change: open `references/core/cli-contract.md`, the relevant carrier file under `references/carriers/`, and `references/core/privacy-hardening.md`; add tests before implementation.
- Output/artifact bundle design change: open `references/core/output-bundle-design.md`; do not reintroduce mandatory shell-owned output filenames when the CLI can own them.
- Source/runtime skill sync or commit evidence: open `references/maintenance/source-runtime-sync.md`.
- Cross-model eval of CLI/skill behavior: open `references/maintenance/model-evaluation.md`; compare success, elapsed time, tool calls, route selection, envelope verification, and privacy status against prior runs using the same private evidence.

## References

- `references/registry.md` — owner map for all references; check before adding or renaming support files.
- `references/core/cli-contract.md` — CLI JSON envelope, `doctor.data.agent_contract`, process traces, tests, and dispatch contract.
- `references/core/auto-route-dispatch.md` — design notes for `build auto`: deterministic CLI-owned route inference, safe source fingerprints, ambiguity errors, and agent stop rules.
- `references/core/canonical-itinerary.md` — provider-agnostic manual JSON input and schema/semantic boundary.
- `references/core/calendar-event-format.md` — compact mobile calendar summaries/descriptions.
- `references/core/manual-source-extraction.md` — cached attachment/PDF/email/screenshot extraction notes.
- `references/core/timezone-catalog.md` — timezone asset and override policy.
- `references/core/privacy-hardening.md` — redaction, private artifact permissions, and hardening checks.
- `references/core/output-bundle-design.md` — CLI-owned private output bundle and artifact verification boundary.
- `references/maintenance/source-runtime-sync.md` — source↔runtime parity, cleanup, and commit workflow.
- `references/maintenance/model-evaluation.md` — privacy-safe cross-model CLI/skill eval harness, comparison fields, and reporting shape.
- Carrier references only when needed: `references/carriers/aeroflot.md`, `references/carriers/ural-airlines.md`, `references/carriers/utair.md`, `references/carriers/redwings.md`.

## Common Pitfalls

1. Re-asking for data that was already supplied in an attachment/cache.
2. Treating `doctor` as mandatory on an obvious happy path. It is a machine-readable runbook/capability probe for ambiguity, failure, eval, and maintenance; normal generation should be one `build auto` call so the CLI owns route inference.
3. Saying “the CLI does everything” while leaving route dispatch to the agent. Use `build auto` so the CLI infers route from a safe source fingerprint and returns a safe envelope.
4. Trying several carrier helpers opportunistically instead of letting `build auto` perform deterministic host-first dispatch.
5. Scraping airline manage-booking URLs or helper stdout instead of using `flight_calendar_ics.py --json build auto`.
6. Reintroducing agent-owned `mktemp`/`chmod`/`--output-json`/`--output-ics`/`tee` plumbing on the happy path.
7. Sending the `.ics` before parsing the envelope and requiring `data.verification.ok=true`.
8. Leaking booking credentials or passenger/ticket data in chat summaries or model-visible tool/session logs.
9. Verifying by dumping full `.ics` content instead of trusting the CLI bundle verification; calendar descriptions may contain passenger/PNR/ticket details.
10. Using one timezone for all airports or adding one-off local timezone maps.
11. Reading CLI source, `doctor`, or carrier references on the happy path; after one successful `build auto` with `data.verification.ok=true`, stop unless the user asked for evaluation/debugging or a failure requires maintenance.
12. Treating Red Wings already-opened order pages as access-key sources; use the direct find link or manual canonical JSON.

## Verification Checklist

- [ ] Source stored privately or normalized manually.
- [ ] Exactly one `--json build auto ...` command run on the happy path; `doctor`/explicit route used only for ambiguity, failure, evaluation, or maintenance.
- [ ] Envelope passed: schema version, `ok=true`, `command=build`, route, process, segment count, `data.verification.ok=true`, safe data.
- [ ] `data.ics_path` exists; no private calendar content was dumped into tool output.
- [ ] Final Telegram response includes `MEDIA:/absolute/path/flights.ics` and no private identifiers.
