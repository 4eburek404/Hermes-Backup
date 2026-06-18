# Reference index

Routing hub for everything outside the flight-search happy path. Loaded on demand. Not in the runtime hot path.

## Runtime follow-ups → reference

Enter only when the report flags missing evidence or the user asks for a narrower proof.

| When | Read | Notes |
|---|---|---|
| Direct / nonstop over a bounded date window | `direct-date-window.md` | Set `route_options.date_window_end`; read `evidence.date_window_inventory`. |
| Carrier or exact-airport scope | `provider-aware-airport-priority.md` | Answer the requested scope first, then alternatives; required controls appear in the report evidence plan. |
| PNR / through-baggage / protection / final fare / refund / exchange / terminal proof | `source-boundaries.md` | Require purchase-screen, airline/GDS, seller, or explicit upstream proof; otherwise unproven. |
| Market controls — RU-domestic, RU-touching, global non-RU | `flow-decision-router.md` | Global non-RU must not silently inherit RU-priority, Moscow/SVO controls, or Russian-provider assumptions; if it does, it is a structured limitation. |
| Train vs flight comparison after a search | `rail-rzd-live-pricing.md` | Official RZD read-only; bound to price/time evidence. |
| Short / missing direct set | `direct-priority-filter.md` | Truncation vs provider absence; `all_direct_inventory` flag, caps, round-trip per-direction. |
| Report read order / renderer contract | `report-contract.md` | `agent_report.v2`, `flight_search_user_answer.v3`, semantic validation. |

## Maintenance rules → SSOT file

Load only for an inspect/debug/modify/sync task. Never expose maintenance output as the traveler answer.

| Topic | File |
|---|---|
| Parameter renames, no legacy aliases (`fallback_max_connections` → `tier2_max_connections`); direct-only is `max_connections=0` | `cli-maintenance.md` |
| Terminology: «deferred» / «secondary tier» / «two-stop tier» / «last-resort», never «fallback» for priority tiers | `cli-maintenance.md` |
| No new audit/session/proposal Markdown; move durable behavior into CLI/report/tests; reference lifecycle | `cli-maintenance.md` |
| Tests verify deterministic code/contract strings, not prose phrases (no `assertIn("sentence", reference_text)`) | `cli-maintenance.md` |
| Bulk-rename checklist (`grep -rn` → rename code/flags/schemas/tests → fix assertions → drop migration notes → `pytest -x`) | `cli-maintenance.md` |
| One canonical source per rule; replace cross-file duplicates with a cross-reference | `cli-maintenance.md` |
| Direct-vs-connected mixing: assembly-level suppression, budget caps/bypass, round-trip per-direction — root causes | `debug-playbook.md` |
| `is not None` guard on `max_connections_per_journey` (fixtures without the key must not read as direct) | `debug-playbook.md` |
| Candidate-generation caps (`--max-candidates`); all-direct catalog expansion: single `all_direct_inventory` flag, `ALL_DIRECT_CATALOG_CAP`, three truncation layers | `direct-priority-filter.md` |

When a topic spans files, treat the file above as SSOT and cross-reference the others rather than duplicating.
