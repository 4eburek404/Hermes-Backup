# Final Answer Rendering RCA

Use this when flight-search output is technically correct but hard to read, misses carrier-specific options, or exposes CLI/debug labels in a user answer.

## Symptom

- The agent reports only the first visible combinations, then later finds more after a follow-up.
- The final answer is a field dump or debug-like block instead of a traveler-facing Telegram summary.
- Carrier-specific controls such as Aeroflot/SU/SVO exist in `priority_options` or aggregate controls but are hidden by generic `display.text` / first-ranked options.

## Root Cause Pattern

The skill has two layers that must stay separate:

1. Evidence/report layer: `data.agent_report`, `human_answer`, `display`, `display.options`, `recommended_options`, `priority_options`, `answer_lines`, diagnostics.
2. User-answer layer: compact Telegram answer following `SKILL.md` → `## User Answer Style`.

A past regression came from `references/report-contract.md` treating `display.text` as ready user-facing text. That conflicted with `SKILL.md` user-answer style and encouraged copying raw itinerary/debug fragments.

## Files Responsible

- `SKILL.md` — canonical user-answer style and decision rules.
- `references/report-contract.md` — how to read `data.agent_report`; must not instruct agents to copy debug/report text verbatim.
- `cli/flights_cli/reporting/agent_report_builder.py` — builds `agent_report`, including `display`, `answer_lines`, and `human_answer`.
- `cli/flights_cli/reporting/human_answer_renderer.py` — provider-neutral deterministic Telegram/Markdown renderer; default final answer source.
- `cli/flights_cli/reporting/flight_display.py` — builds deterministic itinerary fragments; evidence only, not the final Telegram answer.
- `cli/flights_cli/reporting/answer_line_renderer.py` — builds compact internal summary/diagnostics; do not copy labels like `Best CLI-ranked option`, `Priority control`, or `Coverage diagnostics` into final answers.
- `cli/flights_cli/output.py` — CLI human/debug renderer; not the Telegram renderer.
- `cli/flights_cli/reporting/final_answer_contract.py` — contract/validation surface, not currently a deterministic final-answer renderer.

## Existing Analogue: Travelpayouts Formatter

A proven analogue exists in the Hermes Travelpayouts plugin:

- Runtime path: `$HERMES_HOME/plugins/travelpayouts-flights/formatters.py`
- Source path commonly used in Konstantin's setup: `/home/konstantin/code/Hermes/hermes/plugins/travelpayouts-flights/formatters.py`
- It is adapted from `bot/modules/flights/formatters.py` and is deliberately separated from the upstream bot package.

What it does:

- `format_time`, `format_date`, `format_date_full`, `format_duration`, `format_transfer`, `format_price`, `format_transfers_count` are mostly provider-agnostic formatting helpers.
- `format_flight_results()` is the actual deterministic Telegram-HTML final renderer.
- `_format_single_flight()`, `_format_segment()`, and `_format_leg()` render a nested `FlightOut -> SegmentOut -> LegOut/TransferOut` structure.

What is provider-specific:

- The integration lives under the `travelpayouts` toolset and requires `TRAVELPAYOUTS_TOKEN`.
- `enrichment.py` maps the legacy plugin `FlightPrice` shape into `FlightOut` and builds external fallback booking URLs/marker links.
- `format_flight_results()` currently emits a legacy cache/aggregator caveat that is not appropriate for every live provider.

Lesson for `flight-search`: copy the architectural seam, not any provider-specific wording: raw/provider report -> normalized report fields -> deterministic provider-neutral `human_answer` renderer -> compact model summary. The renderer reads `agent_report` (`recommended_options`, `priority_options`, `through_fare_checks`, `provider_failures`, `source_boundaries`) and produces `human_answer.text` without leaking `agent report:`, `Best CLI-ranked option`, `Coverage diagnostics`, `provider_aggregate_candidate`, or other debug labels.

## Session Lesson: Per-Segment Times Are a Renderer Contract

A May 2026 correction exposed a specific final-answer regression: the answer explained the desired human-centered itinerary notation, but the actual `human_answer` renderer still collapsed a connected itinerary into one whole-journey range:

- Wrong collapsed form: `SU1437→SU1844 | 01 авг 18:10–21:55 | SVO 1ч40 | всего 5ч45`
- Correct rendered form: `SU1437 18:10–18:55 → SU1844 20:35–21:55 | 01 авг | SVO 1ч40 | всего 5ч45`

Root cause: the line formatter used `flight_numbers(segments)` plus first departure / last arrival. That hides each flight's individual departure and arrival times and pushes the burden back onto the model/user-answer prose.

Durable fix pattern:

1. Make `human_answer_renderer.py` render a per-segment sequence (`flight_number dep–arr`) from normalized segment fields.
2. Keep the date as a separate field after the segment sequence so the line stays compact in Telegram.
3. Add RED/GREEN tests in `tests/test_human_answer_renderer.py` that assert the per-segment sequence and explicitly reject the collapsed whole-journey form.
4. Update `tests/test_agent_report_contract.py` fixtures when the expected `human_answer.text` shape changes.
5. Run the focused renderer/contract suite and then the full flight-search test suite.

## Fix Pattern

When this recurs:

1. Search the skill for stale wording such as `display.text verbatim`, `copied as-is`, or instructions that make `answer_lines` final user text.
2. Patch `SKILL.md` and `references/report-contract.md` so `display`/`answer_lines` are evidence inputs, not final answer shape.
3. Ensure read order checks `recommended_options` and `priority_options` before relying on `answer_lines`, especially for carrier-specific questions.
4. If adding a code fix, prefer a renderer patterned after the provider-neutral seam: report fields -> deterministic `human_answer` renderer -> tests.
5. For connected itineraries, enforce the renderer contract in tests: every flight/segment must show its own departure and arrival time; reject lines that show only first departure and final arrival for a multi-leg journey.
6. Add or update tests only when changing CLI behavior. Markdown contract fixes can be verified by read-back + search for stale wording.
7. Keep `human_answer` schema/tests current so the deterministic renderer remains the default final-answer path instead of reverting to prompt/contract-only discipline.
