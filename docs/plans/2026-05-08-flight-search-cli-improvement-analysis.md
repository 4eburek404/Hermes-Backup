# Plan: flight-search CLI improvement analysis

Current status: completed

## Scope

Read-only analysis of saved flight-search raw JSON files, current flight-search skill/CLI behavior, and public CLI best-practice references. Produce prioritized improvement recommendations. No new live searches/API calls and no new raw-JSON recovery workflow.

## Evidence collected

- [x] External CLI best-practice references:
  - clig.dev: human-first output, consistent flags/subcommands, machine-readable output, stdout/stderr separation, progressive disclosure.
  - Python argparse docs: subcommands/choices/help/error behavior; JSON/YAML parsing needs explicit error handling beyond simple `type=` conversion.
  - GitHub CLI manual: default human output plus opt-in `--json`, `--jq`, `--template` for structured downstream use.
  - Azure CLI docs: stable JSON as default/major output mode and explicit `--output` formats.
- [x] Saved JSON structure and cross-file patterns from `/home/konstantin/docs/flights/2026-05-08/*.json`.
- [x] Current CLI/skill source touchpoints:
  - `cli.py` output flags and `--agent-brief` behavior.
  - `services/assembly.py` recommendations/frontier/retained candidate details.
  - `services/agent_report.py` report contract and answer_lines.
  - `orchestrators/kb_assemble.py` live plan execution, route-family skipping, aggregate controls.
  - `orchestrators/route_plan.py` static plan generation.
  - `output.py` human rendering and known token-field audit hotspots.
  - `SKILL.md` and references/report-contract/debug-playbook/source-boundaries.

## Raw JSON findings

Dataset: 11 saved `route live-assemble` envelopes, about 1.77 MB total.

Schema/completeness:
- All files have `segment_results=[]`; real flight details are only in `ranked_candidates[].candidate.journeys[].segments[]` for retained top candidates.
- `ranked_candidates` retains only 2, 3, or 5 full candidate bodies, while `ranked` has up to 50 summaries.
- 11 recommendation entries point outside retained full detail, so cheapest/fastest often lacks segment bodies in compact/debug output.
- No `aggregate_controls` were present in these saved files; they were not agent-mode/aggregate-control runs.
- All recorded segment searches were cache hits; this dataset is evidence about CLI behavior/output shape, not fresh fare availability.

Cross-file operational patterns:
- Moscow/SVO is already central for Asia/India: PEK, PKX, DEL top routes are via SVO or include SVO control families.
- Direct exact-airport probes were skipped by SVX official route index in 10 cases (`direct_route_schedule_negative`), but PKX direct had offers. This is useful but must not become final absence proof.
- `dxb_direct` was skipped 52 times as `priority_route_viable`; DXB is currently late fallback, not a normal control.
- `ist_svo_su_fallback` was skipped 42 times as `direct_probe_has_offers`; this creates blind spots when user wants Moscow/SU control even if IST is viable.
- Rejected pair warnings on Asia/India cluster around `invalid_time_order`, `airport_mismatch`, and `too_short`; this points to route-family assembly diagnostics, not necessarily route absence.
- Long overnight transfer appears in TLS→SVX: IST connection 805 minutes, rank #1 only because few competitors; business profile should surface a detour/control rather than just accept the technical optimum.

## Improvement backlog

### P0 — small, high-value CLI output/contract fixes

1. Retain full details for recommendation IDs, not just first N ranks.
   - Current issue: `recommendations.cheapest_acceptable` / `fastest_acceptable` often point to rank 7, 11, 13, 17, 32, 44, 46, 48, outside retained `ranked_candidates`.
   - Improvement: when building output, include full candidate bodies for `best_ranked`, `cheapest_acceptable`, `fastest_acceptable`, plus current top-N and frontier controls.
   - Expected effect: agent can explain cheapest/fastest trade-offs without raw dumps.

2. Add explicit `recommendation_details_available` or embed recommendation option objects in `agent_report`.
   - Current issue: summary-only recommendations look authoritative but may lack segment details.
   - Improvement: agent_report should mark `full` / `summary_only` and answer_lines should not imply full route detail when not retained.

3. Improve `answer_lines` to compare best vs cheapest/fastest controls.
   - Current issue: one-line best option hides big deltas (e.g. BCN best vs cheapest gap ~40k RUB; PKX gap ~30k RUB).
   - Improvement: report should say: best operational option, cheapest acceptable if materially cheaper, fastest if materially faster, and why lower-ranked.

4. Show route family / hub labels in `recommended_options` and `priority_options`.
   - Current issue: agent has to infer “via SVO/IST/direct” from segments.
   - Improvement: add compact labels: `route_family`, `hub_chain`, `direct/control`, `moscow_gateway_control`, `same_carrier_control`.

### P1 — planning/ranking behavior

5. Make Moscow gateway controls first-class, not only fallback.
   - Current issue: `ist_svo_su_fallback` skips when direct IST has offers. That is good for avoiding waste, but bad for Konstantin’s desired comparison: show direct/primary plus Moscow control when plausible.
   - Improvement: add a `moscow_control` route family or flag like `--include-moscow-control` enabled for Russian-origin international business routes.
   - For Asia/China/India this is already close via `svo_asia`; for IST/Europe it needs explicit control behavior.

6. Add overnight-transfer visibility/control, not automatic penalty.
   - Current issue: TLS→SVX ranks 13h25 IST layover as #1/good because no better assembled candidates are available.
   - Improvement: detect `connection.actual_min >= 480` and explicitly label as overnight/long-wait; show it as a visible trade-off and, when plausible, show an alternative gateway control. Do not automatically demote solely because the layover is overnight.

7. Improve rejected-pair diagnostics into aggregate counts.
   - Current issue: raw `rejected_pairs` samples are noisy; hidden pattern is counts by reason/family.
   - Improvement: `agent_report.rejected_pair_warnings` should include grouped counts: `invalid_time_order`, `airport_mismatch`, `too_short`, affected route families.

8. Align `route plan` and `route live-assemble` route-family builders.
   - Current issue: similar route-family logic exists in both `route_plan.py` and `kb_assemble.py`; drift risk.
   - Improvement: extract shared route-family plan builder so help/plan/live behavior cannot diverge.

### P2 — CLI ergonomics / best-practice cleanup

9. Add `--output human|json|agent|summary` or document current equivalents.
   - Current state: global `--json`, `--agent-report`, `--agent-mode`, `--agent-brief` are useful but overlapping.
   - Improvement: either alias to a clearer `--output agent` or improve help text/examples.

10. Add example sections in help/docs.
    - Current help lists many flags but few workflows.
    - Improvement: examples for normal search, Moscow control, SU-only aggregate control, debug rerun.

11. Ensure machine output stays pure stdout and diagnostics pure stderr.
    - Current CLI generally follows this, but the session had pipe fragility from mixed stderr/stdout patterns.
    - Improvement: add regression tests around `--json` stdout parseability under warnings/errors.

12. Remove/redact remaining audit false-positive hotspots separately.
    - Aeroflot bundle has been removed, but audit still flags old `secret_like_value` patterns in `output.py`, `fli_mcp.py`, and `test_cli_contract.py`.
    - Do not mix this with route behavior changes.

## Recommended next implementation order

1. P0 recommendation-detail retention + tests.
2. P0 answer_lines trade-off summary + agent_report schema tests.
3. P1 Moscow control family/flag + tests on SVX→IST and Asia cases.
4. P1 overnight-transfer detection + tests from TLS→SVX pattern.
5. P2 CLI help/examples and audit cleanup as separate small PRs.

## Verification state

Initial task was analysis-only. No live flight searches/API calls were run for the analysis.

## P0 implementation log — 2026-05-08

Implemented P0 recommendation-detail retention:
- `assembly.py`: recommendations are now computed from the full ranked list before compact `max_candidates` truncation; full candidate details are retained for `best_ranked`, `cheapest_acceptable`, and `fastest_acceptable` in addition to the normal top-N details.
- `agent_report.py`: recommendation option objects now include `detail_status` and `answer_lines` explicitly surface cheapest/fastest trade-offs when they differ from the best option.
- `agent_report.v1.schema.json`: option contract now requires `detail_status` (`full`, `summary_only`, or `missing`).
- Tests added/updated: `test_agent_report_p0_completeness.py`, `test_agent_report_contract.py`.

Verification:
- Focused P0 test: `Ran 1 test ... OK`.
- Agent report contract tests: `Ran 12 tests ... OK`.
- Full flight-search CLI suite: `Ran 87 tests ... OK`.
- `python -m flights_cli --json doctor`: `ok: true`.
- `git diff --check -- skills/productivity/flight-search`: clean.

No live flight searches/API calls were run for this P0 implementation; only offline unit/subprocess tests and `doctor` were run.
