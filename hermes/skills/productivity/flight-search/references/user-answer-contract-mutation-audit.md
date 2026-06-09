# User-answer contract mutation audit notes

Use when auditing or changing `flight_search_user_answer.v3`, `reporting/user_answer.py`, or any user-facing flight-search renderer.

## Why this exists

A previous audit found that the contract layer can validate JSON shape while allowing user-facing text to contradict structured evidence. Do not stop at schema or happy-path tests; mutate rendered output and verify semantic failure modes.

## Mutation checks to run

Start from a known-valid `build_user_answer(...)` fixture, mutate one property at a time, and call `validate_user_answer(...)`.

High-priority mutations that must fail unless evidence is proven:

- Append false ticketing guarantees to `rendered_text` / `answer_lines`:
  - `Single PNR and through fare confirmed.`
  - `Protected round-trip and baggage-through confirmed.`
  - `Единый билет, сквозной багаж и защищенная стыковка подтверждены.`
- Remove mandatory caveats from `rendered_text` while `required_caveats.*` stays true.
- Make `answer_lines` diverge from `rendered_answer_lines(rendered_text)`.
- Change rendered price/date/segment text without changing structured `catalog.items`.
- Change `catalog.items[*].render_line` so it no longer matches structured directions/price/risk fields.
- Use `answer_mode=recommendation` with non-empty numbered catalog.
- Set `primary_recommendation` to null or contradictory values while catalog remains populated.
- Let `catalog.presentation.max_items` conflict with actual item count.
- Set `detail_status != full` without visible caveat/marker.
- Keep `evidence_refs: []` for user-facing catalog items that claim source-backed options.

## Expected guardrails

- Validate truthfulness of the final user-visible text, not only JSON shape.
- Scan RU and EN guarantee phrases for single PNR / through fare / through baggage / protected connection claims.
- Link `required_caveats` booleans to required text markers in `rendered_text`.
- Treat `render_line` as derived from structured data, or re-render and compare it in semantic validation.
- Enforce mode consistency: catalog mode has catalog items; recommendation mode does not carry a numbered catalog.

## Audit style requirement

For flight-search audits, do not repeat only high-level findings such as “source/runtime drift” or “docs are large.” Provide concrete failing mutation, exact field/path, observed validator result, and the risk to traveler-facing output.