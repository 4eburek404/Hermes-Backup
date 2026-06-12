# Canonical Itinerary and Source Normalization

The single document for producing valid private canonical itinerary JSON from any source. Exact validation and rendering behavior is code-owned (schema, `itinerary_contract.py`, `ics_render.py`, bundle verification); this file covers what the agent must supply.

## Role

Canonical itinerary JSON is the private, provider-neutral handoff into calendar generation. Use it when the source is a PDF, email, screenshot, pasted segment list, unsupported carrier, or already-normalized data:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --input /private/itinerary.json
```

Start from the synthetic template `templates/aeroflot-itinerary.example.json` — it shows the exact field shapes. Per flight segment the schema requires `flight_number` plus `departure` and `arrival` endpoints, each with `airport` (IATA), `local` (local datetime), and `tz` (IANA zone for that airport — never one global zone for all segments; the bundled catalog and `--tz CODE=Area/City` overrides exist for resolution, see `core/timezone-catalog.md`). Carrier, terminals, status, and links are optional — include them only when safe and present in the source.

## Normalization path (PDF / email / screenshot / manual)

1. Keep the original private; never print full document text into chat or logs.
2. Try text extraction first; use OCR only when extraction is insufficient.
3. Extract only calendar-safe operational fields; resolve ambiguous city names to airports with explicit evidence.
4. Preserve multi-segment ordering; treat ambiguous airports, a missing year, an impossible duration, or mixed timezone notation as problems to resolve before building.
5. Write the JSON to a private file and run the `build auto --input` command above. The CLI rejects bad data with a specific `validation_error`; fix the canonical source and retry rather than switching to a carrier helper without new evidence.

Booking identifiers, passenger identity, ticket/document/contact/payment fields stay out of canonical JSON unless the schema explicitly carries them for a private adapter (sensitive classes: `core/privacy-hardening.md`).

## What the agent never does here

Event text (`SUMMARY`/`LOCATION`/`DESCRIPTION`), UTC conversion, alarms, placeholder rules, and artifact verification are renderer- and bundle-owned and locked by tests. Do not inspect or recount the generated `.ics`; require `data.agent_handoff.ready=true` and report `safe_summary`.
