# SVX–FRA flight search metrics — 2026-08-17 / 2026-08-19

## Goal
Find operationally viable tickets for SVX→FRA on 2026-08-17 and FRA→SVX on 2026-08-19, save runtime/search metrics, and diagnose where the flight-search workflow loses time.

## Plan
1. ✅ Verify the flight-search CLI runtime with `doctor` and record environment/source status.
2. ✅ Run `route live-assemble` with the business profile and capture full stdout/stderr plus wall-clock timings.
3. ✅ Parse `agent_report`, provider failures, source boundaries, route options, and timing metrics into saved artifacts.
4. ✅ If the compact report is insufficient or contradictory, run targeted segment/provider probes and capture per-command timings.
5. ✅ Report: best options, timing bottleneck, inconsistencies, and search-algorithm complexity/limitations.

## Outputs
- Analysis report: `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/analysis_report.md`
- Metrics summary: `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/metrics_summary.json`
- Diagnostics: `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/algorithm_diagnostics.json`

## Assumptions
- `17.08` and `19.08` mean upcoming dates: 2026-08-17 and 2026-08-19.
- Exact airports: SVX and FRA.
- Ranking profile: business/operational frontier, not cheapest-first.
