---
name: flight-search
version: 0.14.0
description: Use when finding or comparing live flight options with the bundled flights CLI, including direct, round-trip, open-jaw, date-window, carrier-filtered, and exact-airport searches; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: travel
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

Find and compare live flight options through the bundled CLI. One adult,
economy. Never book, and never claim a final fare, baggage allowance, protected
transfer, or single PNR that the provider has not proven.

## Path Resolution

Treat the directory containing this `SKILL.md` as `<skill-root>`. Resolve every
bundled path relative to that directory. Do not infer the location from a
client-specific skills home and do not assume a `SKILL_DIR` environment
variable exists.

Use `"${HERMES_SKILLS_PYTHON:-python3}"` as the Python interpreter for bundled
commands: when `HERMES_SKILLS_PYTHON` is set, use that exact executable,
otherwise `python3`.

## Golden Path

Three fields are a complete request: `origin`, `destination`, `depart_date`.
Everything else has a working default. Resolve `cli/` from `<skill-root>`, use
it as the working directory, and pipe the request in:

```bash
echo '{"origin":"SVX","destination":"LED","depart_date":"2026-10-28"}' |
  PYTHONDONTWRITEBYTECODE=1 "${HERMES_SKILLS_PYTHON:-python3}" -m flights_cli search --request -
```

`--request` also takes a file path. Add `--json` when you need the structured
answer; without it, stdout is the rendered text and nothing else.

Return the CLI's itinerary content, values, warnings, and option order as they
come. Do not assemble, supplement, remove, rerank, correct, or annotate them.

### Request fields

| Field | Meaning |
|---|---|
| `return_date` | Round trip. One provider search carries both dates; a provider that cannot do that is left out rather than silently handed a one-way, and if none of the selected providers can, the search fails loudly. |
| `max_connections` | Hard ceiling: an itinerary above it is rejected before ranking. `0` means direct only. |
| `preferred_connections` | Soft ceiling: options above it appear only when nothing within it exists. Must not exceed `max_connections`. |
| `date_window_end` | Scan direct inventory day by day from `depart_date` through this date. Requires `max_connections: 0` and no `return_date`. |
| `only_carriers` | `["KL"]` — narrows the provider query itself. |
| `origin_airports` / `destination_airports` | Pin exact airports, e.g. `["SVO"]`. |
| `limit` | How many options to return. |
| `currency` | Defaults to `RUB`. |
| `provider_policy` | `auto` (default) queries every compatible provider; a single name (`tutu`, `kupibilet`) restricts the search to it. |
| `schema_version` | `flight_search_request.v1`; filled in when omitted. |

Run budgets are CLI flags, not request fields: `--timeout`, `--max-searches`,
`--segment-limit`, `--live-cache-ttl`, `--no-live-cache`, `--fail-fast`.

### Request shaping

- One requested journey is one search. Do not split it into manual leg
  searches: connection assembly belongs to the CLI.
- A true multi-city or open-jaw trip is one request per independent leg. Group
  the results; never invent a through fare, protected connection, single PNR,
  or price for a sector nobody searched.
- An exact-airport request stays exact. Use a city code only when the user asks
  for city scope — airports in the same city are not interchangeable for
  connection continuity.
- An adjacent cross-airport connection is invalid. If one ever appears in the
  output, report the defect instead of presenting it as a valid option.

## Presentation

- **Telegram / CLI:** return text-mode stdout verbatim; those surfaces preserve
  its line breaks.
- **Hermes Desktop:** do not paste multiline stdout as one paragraph and do not
  wrap it in a fenced `text` block. Render the same facts as native Markdown so
  Desktop creates real block elements:
  - one numbered heading per option;
  - each flight is its own nested `- Рейс ...` item;
  - each layover is its own nested `- Пересадка ...` item, right after the
    flight that arrives;
  - price and each warning are separate nested items;
  - never put two flights, or a flight and its layover, in one item.

This is presentation only: every value and warning survives, and option order
never changes. In JSON mode the canonical sources are `data.rendered_text` and
the matching entry in `data.options`.

## Bounded Agent Expansion

Run one `search --json` and answer from it. `data.evidence` says how far the
search actually got: `providers_searched` names who was asked, `provider_failures`
names who failed, and `complete` is false when some planned probe never reached
a terminal state. A bounded search is not a missing route — say which it is
instead of reporting absence. Repeat the search at most once, and only when a
failure is what a retry would fix. Never turn evidence fields into traveler
control text.

For undated direct-network candidates, use
`../airport-direct-destinations/SKILL.md`. Its output is hypothesis evidence,
not a priced itinerary and not proof of dated availability.

## Failure

If the search fails or returns no options, report that. Do not reconstruct an
itinerary by hand. There is no separate diagnostic command: a narrower
`search --request` is the diagnostic, and its output is evidence for you, not
an answer for the traveler.

## Reference Routing

- `references/report-contract.md` — reading `data`, option fields, ticketing,
  connections, evidence.
- `references/source-boundaries.md` — what a result can prove: availability,
  airport continuity, MCT, ticketing, protection, adjacent sources.
- `references/cli-maintenance.md` — source, schema, version, test, or release
  work on the CLI itself.
- `references/index.md` — start here when ownership is unclear.
