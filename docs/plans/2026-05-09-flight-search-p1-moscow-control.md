# Plan: flight-search P1 Moscow gateway control

Current status: completed / verified offline

## Goal
Implement first-class Moscow gateway controls in the flight-search CLI/report path, so Russian-origin international business routes can show a realistic via-Moscow control even when direct or other-hub options exist.

## Constraints
- No live flight searches/API calls during implementation verification unless explicitly requested.
- Do not recreate raw JSON analyzer/workflow.
- Do not touch unrelated dirty files.
- Preserve P0 contract: recommendation/control options referenced by agent_report must have `detail_status` and full segment details when available.
- Prefer SVO; use DME/VKO only when practical and not airport-mismatch clutter.

## TDD plan
1. Inspect route-family and priority/frontier mechanisms. — done
2. Add RED tests with offline segment results. — done
3. Implement minimal CLI/report changes. — done
4. Run focused tests, full flight-search CLI suite, doctor, diff-check, pycache check. — done

## Contract shape
- `agent_report.priority_options[]` includes an option with `category="moscow_gateway_control"` when a viable SVO route exists and origin is Russian while destination is international.
- `answer_lines[]` contains a compact Moscow control line.
- `detail_status="full"` when retained segments are present.
- Existing controls such as `all_su_svo`, `all_su`, and `single_carrier` remain valid; the same itinerary may also appear as `moscow_gateway_control` for a different decision reason.

## Implementation summary
- Generalized legacy `ist_svo_su_fallback` / `synthetic_moscow_fallback` behavior into `moscow_gateway_control`.
- Removed old direct/IST-empty gating for Moscow/SVO control segments: the control can be generated even when direct or primary hub options exist.
- Added/kept `moscow_gateway_control` in `priority_options[]` without suppressing existing priority categories.
- Added explicit `Moscow gateway control: ...` answer line while preserving generic `Priority control: ...` for non-Moscow categories.
- Documented the new category in `references/report-contract.md` and `references/moscow-gateway-control.md`.

## Verification log
Offline-only; no live flight searches/API calls were run.

Focused/contract checks passed:
- `test_agent_report_p1_moscow_control.py` — OK.
- `test_kupibilet.py -k test_ru_priority_synthesizes_moscow_control_even_when_ist_direct_has_offers` — OK.
- `test_kupibilet.py` — 19 tests OK.
- `test_agent_report_contract.py` — 12 tests OK.
- `test_agent_report_p0_completeness.py` — OK.
- `test_route_workflows.py -k agent_report` — OK.

Full verification passed before final doc-plan bookkeeping:
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests` — 89 tests OK.
- `PYTHONDONTWRITEBYTECODE=1 python -m flights_cli --json doctor` — exit 0, `ok=true`.
- `git diff --check -- skills/productivity/flight-search` — exit 0, clean.
- pycache/pyc check under `flight-search/cli` — no generated files found.

Final verification after documentation/plan updates completed:
- `test_agent_report_p1_moscow_control.py` — 1 test OK in 0.207s.
- `test_kupibilet.py -k test_ru_priority_synthesizes_moscow_control_even_when_ist_direct_has_offers` — 1 test OK.
- `test_agent_report_contract.py` — 12 tests OK.
- `test_agent_report_p0_completeness.py` — 1 test OK.
- `test_route_workflows.py -k agent_report` — 1 test OK.
- Full suite: 89 tests OK in 7.360s.
- Doctor summary: `{'ok': True, 'command': 'doctor'}`.
- `git diff --check -- skills/productivity/flight-search` — clean.
- Test run generated Python bytecode caches; cleanup was required after verification.
