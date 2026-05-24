# Provider-aware Airport Priority

Use this source reference when maintaining route planning, provider dispatch, or report semantics for multi-airport city codes. These are durable rules distilled from runtime implementation/audit notes; dated audit counts and temporary implementation context stay out of active prompt docs.

## Active provider scope

- Active provider paths are KupiBilet and FLI.
- Travelpayouts / Aviasales are not active provider paths for price search.
- Static catalogs remain metadata only: they can normalize cities, airports, countries, airlines, alliances, and aircraft labels, but they do not prove live fares, availability, schedules, or direct service.

## Airport priority policy

- IST means the exact airport code `IST`; do not add `SAW` unless the user explicitly requests `SAW`.
- London defaults to business-priority airport tiers: LHR first; `LGW` fallback only if `LHR` has no accepted/viable offers; `STN` and `LTN` excluded by default.
- Keep preferred-tier and excluded-by-default metadata in the plan/report surface so ranking and audits can explain why one airport was preferred or suppressed.

## KupiBilet MOW city-code policy

- KupiBilet uses `MOW` city-code first.
- Exact `SVO`/`DME`/`VKO` fallback is deferred and not executed in parallel when city-code results have accepted offers.
- If the preferred airport tier has accepted/viable offers, lower-tier airport probes wait; for London this means `LGW` waits for `LHR` to produce no accepted/viable offers.
- Actual airports must be post-validated against `SVO`/`DME`/`VKO` and displayed as actual airport codes, not only `MOW`.
- Missing actual airport fields or out-of-scope actual airports must invalidate city-code results and allow exact-airport fallback.

## FLI exact-airport policy

- FLI is exact-airport only and must not receive `LON` city-code queries by default.
- For `IST→LON`, FLI candidates are `IST→LHR` first, then `IST→LGW` fallback.
- Do not add `SAW`, `STN`, or `LTN` to default FLI probes.

## RU-priority and report contract

- `direct_destination_control` is a search branch, not a nonstop claim.
- RU-priority controls remain structural: branch visibility must link to structured `priority_options` fields such as `control_family`, `control_branch`, `visibility_role`, and `priority_option_id`.
- Semantic validation must use structured fields, not only `answer_lines`.
- Display/report output must show actual airport codes from normalized offers; city codes are request scope, not a substitute for actual departure/arrival airports.

## Source/runtime sync note

- Source and runtime are separate sync surfaces.
- Before source-to-runtime sync, back up the runtime skill because runtime may contain local-only docs.
- After sync, verify source/runtime version markers in `SKILL.md`, `cli/pyproject.toml`, `cli/flights_cli/__init__.py`, and the CLI `--version` output.
- A gateway restart is normally not required for the CLI shim because a new invocation reads runtime files. Use a new Hermes session/reset only when skill text injection must refresh.
