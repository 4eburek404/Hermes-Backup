# Debug and Exception Probe Playbook

Use this playbook only to validate current live report behavior or narrow a decision-critical uncertainty. Debugging should support the Golden Path, not replace it.

## When to Debug

Start with `search --request`. Debug only when the report is internally inconsistent, too sparse for the user's constraint, affected by provider failures, or surprising relative to geography, schedule logic, route family, or airport continuity.

Common triggers:

- recommended options conflict with `source_boundaries`;
- `provider_failures` changes evidence quality;
- city/airport mismatch is plausible;
- a date may be outside provider horizon;
- a risk/profile setting may hide a physically possible option;
- an overnight connection appears when the user prefers same-day travel;
- `priority_options` is missing for an explicitly requested carrier, hub, direct flight, exact airport, or Moscow/SVO control;
- a cheapest, fastest, direct, carrier, or Moscow-control option is referenced without segment details.

## Runtime Provenance

Before declaring a provider root cause or patching behavior, prove which runtime is active from the same interpreter and working directory that will run the probe:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
command -v flights || true
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --version
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import flights_cli, pathlib
print(pathlib.Path(flights_cli.__file__).resolve())
PY
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli search --help
```

Record:

- source path, branch, HEAD, and dirty state when debugging source behavior;
- executable path when available;
- imported `flights_cli.__file__`;
- CLI version and live `--help`;
- source/runtime parity when the runtime skill tree matters;
- request normalization: dates, IATA/city, cabin, profile, passengers, filters, provider policy, and stop policy;
- whether the decision came from `data.agent_report`.

Use only flags shown by live `--help`. Temp editable checkouts under `/tmp` can shadow the permanent skill CLI; do not generalize traces until executable path, imported module path, package metadata, and source checkout are known.

Use `maint doctor` for environment readiness and degradation clues, not as flight evidence.

## JSON Extraction

Read only the JSON payload for decisions. For command output that includes logs, extract the JSON envelope first and then inspect `data.agent_report`. The canonical read order lives in `references/report-contract.md`; debug may inspect `diagnostics.*`, but final prose still comes from `user_answer.rendered_text`.

Decision fields in serialized `agent_report.v2`:

- `frontier.offer_graph`;
- `user_answer.rendered_text`;
- `frontier.recommended_options`;
- `frontier.priority_options`;
- `evidence.through_fare_checks`;
- `evidence.provider_failures`;
- `evidence.source_boundaries`;
- `diagnostics.*` for debug only.

If parsing fails, report the parse layer and rerun with JSON-clean stdout/stderr settings before making a travel claim.

## Targeted Probe Commands

Run the narrowest probe that answers the residual uncertainty. Label probe results as narrower evidence than the assembled report unless the report is demonstrably missing a decision-critical control.

Main report:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request request.json
```

Direct and carrier controls:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20

PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --only-carrier CARRIER \
  --limit 20
```

KupiBilet one-checkout round trip:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose kb-roundtrip ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --only-carrier CARRIER \
  --direct-only \
  --limit 20
```

FLI controls when exact-airport provider evidence is needed:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose fli-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20
```

Use these probe shapes as applicable:

- exact-airport direct-only;
- city-code direct-only when the CLI/provider supports city scope and the user did not name one airport;
- alternate airport when the city has multiple airports and the user allows city-wide search;
- carrier-specific direct or aggregate control for carrier questions;
- round-trip provider aggregate when the user asks for one checkout/order;
- nearby in-horizon control date to split horizon uncertainty from coverage gap.

## Moscow Controls for RU-Touching International

Negative direct/carrier/one-stop claims on Russian-origin international routes need Moscow controls unless structural constraints already prove unavailability.

For ru-priority routes the runtime now plans and executes these controls itself: the `moscow_gateway_control` family includes `gateway_to_destination` (MOW city-code first, deferred `SVO`/`DME`/`VKO` exact fallbacks) and the mirrored `destination_to_gateway` return legs, and `moscow_gateway_direct` is listed in `route.evidence_plan.required_controls`. Read their terminal states from `evidence.coverage_diagnostics` before assuming anything is missing.

Manual leg probes are a fallback for legacy/degraded reports only. If an old compact report lists Moscow or carrier controls as `not_executed`, do not treat that as absence evidence; first rerun the canonical `search --request` (fresh runs execute the gateway controls), and only then run narrow live leg controls:

- outbound date: `SVO|DME|VKO -> DEST --direct-only`;
- return date: `DEST -> SVO|DME|VKO --direct-only`;
- origin↔Moscow legs when they are not already obvious from the main report.

If targeted `--hub SVO --hub DME --hub VKO` live assembly fails contract validation because of two-stop priority artifacts, do not answer from the failed report. Use the narrow direct-only Moscow leg controls and label them as control evidence, not full itinerary assembly.

## RU -> China, Avoid-Moscow, Arrival Deadline

Use this pattern when the user asks for Russia-origin flights to China and says arrival must be by a certain morning/date, with a preference such as “желательно без пересадки в Москве”.

Rules:

1. Normalize destination airports separately: Guangzhou `CAN`, Shenzhen `SZX`, Beijing airport when named, etc.
2. Arrival deadline without departure date: state a working assumption; default “morning” to arrival before 12:00 local time.
3. Search latest plausible departure first, then previous date if needed.
4. Run Golden Path for each serious airport/date pair.
5. If non-Moscow is decision-critical, escalate to `kb-search` with a larger limit for outbound and return legs, then post-filter normalized `offers[].flights`.

Post-filter:

- reject Moscow airports in any segment when comparing non-Moscow options: `SVO`, `DME`, `VKO`, `ZIA`, and city code `MOW` if present;
- outbound must arrive before the stated destination-local cutoff;
- separate one-stop from two-stop options; for business travel, a two-stop return is fallback unless no one-stop non-Moscow option exists;
- compute elapsed time from the ISO timestamps already in the normalized offer.

Wording:

- “Желательно без Москвы” is a preference, not an absolute hard filter unless the user says so.
- Present the best non-Moscow option first if viable, then show a Moscow backup if it is materially cleaner.
- Do not call separate outbound/return provider offers a protected round trip. Say “ориентир за пару one-way предложений” unless a booking screen/GDS/airline fare proves one protected round-trip order.
- If using “morning” as before noon, state that assumption.

## Execution Semantics vs Live Availability

- Mocked/offline execution can prove dispatch, skip, fallback, post-validation, and report-projection semantics; it is not proof of live provider availability.
- For fan-out or fallback bugs, inspect actual executed calls and skipped calls with reasons. Planned candidates alone do not prove the runtime executed or suppressed the right probes.
- When the question is provider-call suppression, fallback order, airport post-validation, or compact report projection, prefer mocked/offline execution proof over broad live provider fan-out.
- Use targeted live smoke only for provider capability, credential/config readiness, or current upstream availability. Keep live probes narrow and date-current.

## Internal Fields

Use internal fields to diagnose, not to overrule the report:

- `segment_searches` for per-segment evidence and provider failures;
- `coverage_diagnostics` for horizon/coverage/control completeness;
- `hub_viability` for connection feasibility;
- `rejected_pair_warnings` for airport mismatch and connection filters;
- `stop_policy` and diagnostics for constraint effects;
- `omitted_counts` for truncation awareness.

If preferred options are missing while segment evidence exists, inspect generation diagnostics. Do not compensate by increasing `candidate_pool_limit` in normal flow; fix the generation contract or reproduce with a focused synthetic case.

## Common Diagnostic Splits

### Horizon vs Coverage

If a date has no useful result, test whether the date is outside the searchable horizon before calling it a route gap. A nearby in-horizon control date can show whether the route shape is discoverable at all.

### Overnight Avoidance

If the recommended option has an overnight connection, test whether same-day options were filtered by connection windows, airport continuity, provider failures, or ranking limits. Do not assume the overnight is physically required unless targeted evidence supports it.

### Ranking Profile Bias vs Physical Possibility

A safe, business, or balanced profile can demote short, cross-airport, late-night, low-confidence, or baggage-risk options. When the user asks whether something is possible, distinguish physical possibility from operational recommendation and explain which profile or field caused the ranking.

## Architecture

Pipeline data flow:

```
JSON request → apps/search.py (normalize + argparse.Namespace)
  → pipeline/search_pipeline.py (FlowDecision + EvidencePlan)
  → orchestrators/live_assemble.py (segment plan + live assembly)
  → execution/probe_dispatcher.py → adapters/providers/registry.py
  → services/assembly.py (assemble_direction + direct_journeys)
  → reporting/agent_report_builder.py (report)
  → reporting/user_answer.py (user_answer.v3 + rendered_text)
  → services/agent_report_contract.py (validate)
  → output envelope
```

Critical coupling points:

| Coupling | Symptom | Fix |
|----------|---------|-----|
| 3 sources of `routing_strategy` | Only `args.routing_strategy` drives routing; `FlowDecision.routing_strategy` is decorative | P0: make `FlowDecision` single source |
| `provider_policy` default mismatch | `live_assemble.py:294` defaults `"kupibilet"` vs `FlowDecision`/`search_request` normalize to `"auto"` | P0: align to `"auto"` |
| `PROVIDER_REGISTRY` singleton without DI | Direct access → TypeError (no fetcher/store) | P0: make `fetcher` mandatory or remove singleton |
| `args: Namespace` as universal param | 20+ `getattr` reads, `prefer_carrier` mutated in-place | P0: track; P1: `SearchContext` dataclass |
| Closures mutating shared state | `skipped_by_condition`, `priority_route_viable`, `ensure_moscow_gateway_control_synthesized` mutate `segment_results`/`searches` | P0: extract to `SegmentSkipPolicy` class |
| Semantic validation via text search | `agent_report_contract.py` checks `"through-fare"`/`"verify"` substrings in `answer_lines` | P0: switch to structured `required_caveats` tags |
| `validate_agent_report()` strips unknown keys | Adding field to builder but not validator → field vanishes from output | Always update both builder AND validator schema |

## Kupibilet Field Mapping

Raw API → normalized offer field names:

| Raw API key | Normalized key | Notes |
|---|---|---|
| `departure` | `origin` | IATA airport code |
| `arrival` | `destination` | IATA airport code |
| `departure_datetime` | `departure_at` | ISO-8601 with timezone |
| `arrival_datetime` | `arrival_at` | ISO-8601 with timezone |
| `equipment` | `aircraft` | ICAO type code |
| `marketing_carrier` | `marketing_carrier` | Same key |
| `operating_carrier` | `operating_carrier` | Same key |
| `flight_number` | `flight_number` | Same key |

**Canonical offer field is `segments`** (not `flights`). All providers must output `"segments"` in normalized offers. When adding a provider, ensure the offer dict key matches what `direct_journeys()`/`pair_offers()` read. Never call `normalize_kupibilet_flight()` on already-normalized data — it expects raw API keys.

**Double-prefix bug:** `kupibilet_flight_number()` constructs `f"{carrier}{number}"` but raw `number` already contains the carrier prefix (e.g. `"SU6418"` → `"SUSU6418"`). `transport_number` (numeric-only) is preferred but often absent.

**Diagnosis recipe — "flights missing from results":**
1. Offer dicts use `"segments"` key (not `"flights"`).
2. `direct_journeys()` reads `offer.get("segments")`.
3. `provider_offer_filter.py:offer_segments()` reads `offer.get("segments")`.
4. `stop_metrics.py:stop_metrics_from_offer()` reads `offer.get("segments")`.
5. Clear live_search cache after changing offer field names.

**Test mock pitfall:** Never global `sed` `"flights"` → `"segments"` in test mocks. Three contexts use `"flights"` legitimately: raw Kupibilet API format (variant segments), flight-by-ID dicts, and FLI MCP responses. Update each mock individually.

## Layover & Elapsed Penalty

**Status:** Implemented (2026-06-16). See `validation.py`, `config.py` (`layover_tiers`/`elapsed_tiers` in `RISK_PROFILES`), `ranking.py`.

IATA-calibrated long layover penalty tiers (multiplier-based, not flat cap):

| Tier | Domestic | International | balanced | safe | cheap | business |
|------|----------|---------------|----------|------|-------|----------|
| long (×1) | 4h | 24h | 10 | 14 | 6 | 16 |
| stopover (×2) | 8h | 48h | 24 | 32 | 18 | 36 |
| extreme (×3) | 12h | 72h | 42 | 54 | 34 | 58 |
| unreasonable (×4) | 16h | 96h | 68 | 80 | 58 | 84 |

Excessive elapsed penalty uses `min_elapsed_min` from search results (dynamic, not static):
- `excess_ratio = (elapsed - min_elapsed) / min_elapsed`
- Tiers: moderate (1.3–1.6), excessive (1.7–2.2), extreme (2.5–3.5)
- Both penalties are additive in `score_itinerary()`; `rank_candidate_list` does two-pass scoring; `pair_sort_key()` reads `rank_order` from profile config.

**Known gap:** `_is_domestic_route()` uses a heuristic airport-code set and receives empty dicts from pair assembly path (which strips `origin`/`destination`/`segments` before ranking). Fix: pass `route_family` or `origin`/`destination` through from assembly. Also verify `excessive_elapsed_penalty` Pass 2 re-scoring fires correctly end-to-end — `ranked` output strips source data before penalty can use it.

## Reference Lifecycle Rule

Route-specific debug notes should not become new active reference files by default. After a case is understood, distill the durable rule into this playbook, `references/report-contract.md`, `references/source-boundaries.md`, `references/provider-aware-airport-priority.md`, `references/cli-maintenance.md`, or tests; leave raw incident history to session search.
