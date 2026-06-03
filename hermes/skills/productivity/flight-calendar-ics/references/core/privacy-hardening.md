# Privacy and Hardening

This file owns privacy, redaction, private artifact permissions, JSON-mode failure behavior, and hardening review checks for `flight-calendar-ics`. It does not own source/runtime sync or carrier API mechanics.

## Sensitive data classes

Never print these in chat, stdout/stderr summaries, commit messages, docs, or long-lived logs:

- PNR/locator values and PNR keys;
- full booking URLs and credential-bearing hash routes;
- access keys/secrets, API keys, generated request headers, bearer tokens, session keys;
- passenger names and surnames when tied to a booking;
- ticket numbers, document numbers, loyalty numbers;
- phone/email/contact/payment/fare details when private;
- raw carrier API payloads containing booking data.

It is acceptable for private requested artifacts (`.ics`, normalized itinerary JSON) to contain operational booking details when the user needs them after import. Those artifacts must be deliberately written to private paths with mode `0600`.

## Durable hardening checklist

Before considering the skill clean:

- Run tests with `PYTHONDONTWRITEBYTECODE=1` and remove/check `__pycache__` / `*.pyc` afterward.
- Test both preferred CLI and compatibility helpers that can write private artifacts:
  - preferred: `scripts/flight_calendar_ics.py --json build make|aeroflot|ural|utair|redwings`
  - compatibility: `scripts/flight_calendar_ics.py --json make|validate|aeroflot|ural|utair|redwings|doctor`
  - `scripts/make_flight_ics.py` direct invocation
  - carrier helper direct invocations, with network mocked/stubbed when testing permissions.
- Under a permissive umask such as `022`, assert private artifacts are still mode `0600`:
  - `build` bundle `itinerary.json`, `flights.ics`, and `envelope.json`;
  - generated `.ics`;
  - carrier-derived itinerary JSON;
  - carrier-derived `.ics`.
- For `--json`, usage/argparse failures must still produce a valid JSON envelope:
  - non-zero exit, normally `2`;
  - `ok=false`;
  - `error.code=usage_error`;
  - no raw argparse usage text in stderr for agent-facing JSON mode.
- Validate representative actual CLI envelopes against `schemas/cli-envelope.v1.schema.json`, not just the schema file itself:
  - `doctor --json` output, including `agent_contract`;
  - `build --json` output, including bundle paths and `data.verification`;
  - `validate --json` output, including process-step fields;
  - one usage/unknown-command error envelope.
- When adding a carrier command, extend `redact()` and tests for that carrier's credential shape before GREEN:
  - full manage-booking URL/hash route;
  - named secret/access fields in argparse errors and exception strings;
  - API payload snippets such as GraphQL `secret` fields;
  - stdout/stderr/process JSON must not contain sentinel PNR/access/passenger/ticket values.
- For validation failures with sensitive fixture values, assert stdout/stderr do not contain PNR, passenger names, ticket numbers, full booking URLs, or fixture sentinel strings.
- Re-run the skill audit helper and require no unresolved blocker findings before commit.
- Run an independent blocker-only review after fixes, not only before fixes.

## Carrier redaction hints

Redaction must cover carrier-specific source shapes:

- Aeroflot: PNR locator, surname/first name, generated `pnr_key`, generated direct deep-link, ticket/passenger fields.
- Red Wings: direct `#/find/<PNR>/<ACCESS_KEY>/Submit` route, access key, PNR/order ID, GraphQL `secret`, passenger/ticket/contact fields.
- Ural Airlines: direct/tracker manage URL, `pnr=`, `pnrNumber=`, `lastName=`, generated `X-Api-Key`, `X-Session`, session key, passenger/ticket/contact/document fields.
- Utair: `rloc=`, `last_name=`, `lastName=`, `filters[locator]`, `filters[passenger_lastname]`, URL-encoded variants, bearer tokens, 13-digit ticket numbers, passenger/contact fields.

## TDD pattern for review findings

When a review finds a blocker:

1. Add a focused failing test reproducing the blocker.
2. Run only that focused test set and confirm RED.
3. Fix the smallest code path that owns the behavior.
4. Run focused tests, then the full relevant test suite, then smoke/audit.
5. Sync runtime changes into the source/backup repo only after the source skill is green and clean.

## Pitfalls

- Do not assume a new wrapper protects legacy helpers; direct helper invocation remains a public compatibility surface if documented or shipped.
- Do not rely on process umask for privacy-sensitive travel artifacts.
- Do not let `argparse.ArgumentParser.parse_args()` run outside the JSON-aware envelope path when `--json` is present.
- Do not consider carrier support GREEN until both happy-path output and failure/error text are redaction-tested for that carrier's exact credential shape.
- Do not trust schema-documentation tests alone; validate real CLI envelopes against the schema to catch drift in process/data fields.
- Do not treat a clean runtime skill as source-complete; verify the source/backup repo copy separately after sync.
- Do not paste raw scanner matches for suspected credentials; report redacted metadata and classify placeholders/test fixtures separately from real secrets.
