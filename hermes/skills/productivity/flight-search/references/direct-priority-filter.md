# Direct-Priority Filter

## Problem

Default search (`max_connections=null`) mixed direct and one-stop flights in results:
- SVX→LED 10.07: 9 direct + 242 one-stop → 251 candidates, ranked output showed 4 direct + 46 one-stop, rendered_text showed only 7 (4 direct + 3 one-stop).
- 5 of 9 direct flights were lost to budget truncation.

## Root Causes (4 layers)

1. **Stop policy**: `BUSINESS_DEFAULT_STOP_POLICY.preferred_max_connections=1` — T0 (direct) and T1 (one-stop) in same preferred tier. One-stop not suppressed when direct exists.
2. **Assembly**: `outbound_journeys = outbound_direct + outbound_pairs` — unconditional merge, both enter candidate pool.
3. **Ranking**: `ranked.sort(key=lambda item: item["risk"]["rank_key"])` — sorts by risk/price, not stop tier. Cheap one-stop outranks expensive direct.
4. **Budget**: `max_recommended_options=5`, `catalog limit=10` truncate output, dropping direct flights.

## Fix (commit 2c1e85d, v0.5.0)

### assembly.py:693-694 — per-direction filter

```python
# Before:
outbound_journeys = outbound_direct + outbound_pairs
return_journeys = return_direct + return_pairs

# After:
outbound_journeys = outbound_direct if outbound_direct else outbound_pairs
return_journeys = return_direct if return_direct else return_pairs
```

Each direction filtered independently. Round-trip with direct outbound + no direct return → direct×one-stop.

### Diagnostics in assembly block

- `direct_priority_applied`: bool — True when direct journeys suppressed one-stop for either direction
- `suppressed_one_stop_outbound_count`: int
- `suppressed_one_stop_return_count`: int

## Unified `all_direct_inventory` flag

### Problem with the scatter-helper approach

Commit `2c1e85d` and a subsequent scatter-fix added bypass checks in 5 locations, each with its own `_all_*_direct()` helper re-deriving "all direct?" from data shape:

| Layer | File | Helper | Data shape used |
|-------|------|--------|----------------|
| 5 | `assembly.py:834` | `_all_ranked_direct()` | `validation_summary.max_connections_per_journey` on ranked items |
| 6 | `agent_report_builder.py:774` | `_all_candidate_details_direct()` | `max_connections_per_journey` on ranked-candidate details |
| 7 | `agent_report_builder.py:859` | `_all_candidate_details_direct()` | same helper reused |
| budget | `report_budget.py` | `_all_options_direct()` | `max_connections_per_journey` on recommended_options |
| catalog | `user_answer.py` | `_all_direct_options()` | `max_connections_per_journey` on recommended |

Problems:
- **Whack-a-mole**: every new truncation point needs a manual bypass.
- **Data-shape coupling**: each helper navigates a different data shape (ranked items vs candidate details vs recommended options).
- **No single source of truth**: the decision "this is a direct inventory" is re-derived 5 times.
- **Unbounded bypass**: `len(items)` with no cap — 50 direct flights → 50 in output.

### Architecture: single flag, single source

One predicate computed once in `assembly.py` from **post-filter** journeys:

```python
outbound_is_direct = bool(outbound_direct) or not outbound_journeys
return_is_direct   = bool(return_direct)   or not return_journeys
all_direct_inventory = (
    (bool(outbound_direct) or bool(return_direct))   # at least one real direct direction
    and outbound_is_direct and return_is_direct       # nothing shown is one-stop
)
```

Semantic checks:
- One-way direct → `True`
- Round-trip all-direct → `True`
- Round-trip direct-out/one-stop-return → `False`
- One-way one-stop-only → `False`

The flag is stored in `ranked["assembly"]["all_direct_inventory"]` and flows downstream.

### Downstream consumption

Each truncation layer reads the flag instead of re-deriving from data:

| Layer | Before | After |
|-------|--------|-------|
| `assembly.py` | `int(getattr(args, "include_ranked_candidates", 5))` | `min(len(full_ranked_items), ALL_DIRECT_CATALOG_CAP) if all_direct_inventory else default` |
| `agent_report_builder.py` (catalog) | `ranked_candidate_options(data, limit=5)` | `ranked_candidate_options(data, limit=catalog_limit)` where `catalog_limit = min(len(ranked_candidates), ALL_DIRECT_CATALOG_CAP) if all_direct else CATALOG_LIMIT_DEFAULT` |
| `agent_report_builder.py` (display) | `build_itinerary_display(report, store)` | `build_itinerary_display(report, store, limit=max(display_limit, CATALOG_LIMIT_DEFAULT))` |
| `report_budget.py` | `_all_options_direct(recommended)` | `report.get("assembly", {}).get("all_direct_inventory")` |
| `user_answer.py` | `_all_direct_options(recommended)` | `report.get("assembly", {}).get("all_direct_inventory")` (via catalog contract) |

Constants:
- `ALL_DIRECT_CATALOG_CAP = 20` (in `assembly.py`, imported by `agent_report_builder.py`)
- `CATALOG_LIMIT_DEFAULT = 5` (in `agent_report_builder.py`)

### Flag propagation check (Phase 2.5)

`report_budget.py` and `user_answer.py` operate on the flat `report` dict (output of `build_agent_report`). They read `report["assembly"]["all_direct_inventory"]` because `build_agent_report` copies the `assembly` block from `data` into `report`. If `assembly` is not present in `report`, add it explicitly.

### Cap and UX

`ALL_DIRECT_CATALOG_CAP = 20` prevents unbounded output. When the cap is hit, the `omitted_counts` mechanism reports "и ещё N прямых" (Phase 4 — reuse existing omission infrastructure, do not create a new one).

## Diagnosis recipe — "direct flights missing from display"

1. Run `diagnose kb-search ORIGIN DEST --direct-only --limit 20` — check `offer_count` and `offers[].price`. All direct flights with prices in raw provider output means the provider is NOT the problem.
2. Check `assembly.all_direct_inventory` — should be `True` for all-direct inventory.
3. Check counts at each pipeline stage to locate the truncation point:
   - `route_result.ranked` (full ranked list)
   - `route_result.ranked_candidates` (assembly truncation — should be min(count, 20) when all_direct_inventory)
   - `agent_report.frontier.recommended_options` (builder truncation — same cap logic)
   - `agent_report.diagnostics.display.options` (display truncation — same cap logic)
4. The truncation point is where the count drops below expected. If `ranked` has 8 but `recommended_options` has 5, the `all_direct_inventory` flag may not be propagating.

**Do not claim "provider did not return prices" when the display is truncated — always verify with `diagnose kb-search` first.**

## Testing

- SVX→LED 10.07 default: 9 direct, 0 one-stop (was 4 direct + 3 one-stop)
- SVX→LED 10.07 `max_connections=0`: 9 direct, no budget truncation (was 5)
- SVX→LED 20.08 default: 8 direct, all with prices (was 5 — 3 lost to layers)
- 396 pytest tests pass
- pyflakes clean

## Round-trip scenarios

| Scenario | Outbound | Return | Candidates | Composition |
|---|---|---|---|---|
| A: Direct both | direct=5 | direct=3 | 15 | direct×direct |
| B: Direct out, one-stop return | direct=5 | direct=0, one-stop=15 | 75 | direct×one-stop |
| C: No direct | one-stop=20 | one-stop=15 | 300 | one-stop×one-stop |
| D: Direct out, empty return | direct=5 | empty | 0 | round-trip impossible |

## What was rolled back (pre-flag scatter helpers)

The following helpers existed temporarily and were removed when the unified flag was introduced:

- `_all_ranked_direct()` in `assembly.py` — checked `validation_summary.max_connections_per_journey == 0` on ranked items
- `_all_candidate_details_direct()` in `agent_report_builder.py` — checked `max_connections_per_journey == 0` on ranked-candidate details
- `_all_options_direct()` in `report_budget.py` — checked `max_connections_per_journey == 0` on recommended options
- `_all_direct_options()` in `user_answer.py` — checked `max_connections_per_journey == 0` on recommended

All four were replaced by reading the single `all_direct_inventory` flag from `assembly`.