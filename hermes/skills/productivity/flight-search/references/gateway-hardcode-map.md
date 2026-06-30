# Gateway Hardcode Map

This is an inventory of current and recently removed hardcoded gateway and hub
behavior. It is not a design target. Gateway-discovery mode should source
bridge gateways from discovery data rather than imperative segment generation.
Moscow/SVO controls are a separate route/control evidence layer, not ordinary
static gateway priors.

## Source Owners

| Area | File | Current role |
|---|---|---|
| Hub constants and airport priors | `cli/flights_cli/config.py` | Defines default hub lists, RU-priority hubs, Moscow city-code airports, Dubai defaults, and Asia/Oceania triggers. |
| Strategy and hub context | `cli/flights_cli/orchestrators/route_graph.py` | Converts routing strategy/profile into route families and effective hubs. |
| Segment fallback plan injection | `cli/flights_cli/orchestrators/route_plan_builder.py` | Imperatively adds direct controls, gateway legs, and fallback hub legs to `plan["segments"]`. |
| Segment execution skips | `cli/flights_cli/orchestrators/live_assembly_runner.py` | Retains the generic `skip_if_priority_route_viable` compatibility hook, but current segment fallback planning no longer emits DXB fallback probes. |
| Synthetic Moscow control | `cli/flights_cli/execution/synthetic_control_runner.py` | Synthesizes SVO/Moscow control results from executed legs. |
| Ranking/report visibility | `cli/flights_cli/services/assembly.py`, `cli/flights_cli/reporting/agent_report_builder.py`, `cli/flights_cli/reporting/projections/summary_lines.py` | Keeps SVO/Moscow priority controls visible even when normal ranking would hide them. |

## Hardcoded Constants

| Constant/value | Category | Meaning |
|---|---|---|
| `DEFAULT_ROUTE_HUBS = ("IST",)` | primary gateway | Built-in `hub-list` fallback when the user does not pass explicit hubs and the strategy resolves to hub-list. Secondary gateway candidates now come from gateway discovery data, not this code list. |
| `DOMESTIC_RU_HUBS = ("SVO", "DME", "VKO")` | fallback priors | Domestic-RU bounded fallback hubs; endpoint airports are removed before segments are built. |
| `PRIORITY_PRIMARY_HUB = "IST"` | legacy primary gateway | Legacy RU-priority international gateway. When `use_gateway_discovery_for_fallback_hubs` is enabled, IST is removed from imperative segment generation and can appear through gateway discovery data. |
| `PRIORITY_MOSCOW_GATEWAY = "SVO"` | Moscow-specific visibility control | Main Moscow gateway used for control legs and synthetic Moscow results. |
| `PRIORITY_ASIA_HUB = "SVO"` | primary gateway | Independent SVO hub for Asia/Oceania routes; bridge gateways such as IST are data-driven when gateway-discovery mode is enabled. |
| `PRIORITY_ROUTE_CARRIERS = ("U6", "SU", "TK")` | fallback priors | Preferred carrier metadata on RU-priority direct/gateway legs. |
| `ASIA_OCEANIA_COUNTRIES`, `ASIA_DESTINATION_CODES` | fallback priors | Trigger the `asia-oceania` route profile and the `svo_asia` family. |
| `KUPIBILET_CITY_CODE_FIRST_AIRPORTS["MOW"] = ["SVO", "DME", "VKO"]` | Moscow-specific visibility control | Gives Moscow gateway controls a KupiBilet city-code-first search path plus deferred exact-airport fallbacks. |
| `DUBAI_DEFAULT_AIRPORTS = ("DXB", "DWC")`, `DUBAI_EXCLUDED_BY_DEFAULT = ("SHJ",)` | airport-scope prior | Dubai endpoint resolution hardcode. This is not a route-plan gateway insertion, but it affects DXB/DWC endpoint scope before planning. |

## Gateway Discovery Priors

`gateway_priors.yaml` can contain ordinary gateway priors and control-layer
priors. Ordinary priors become `GatewayCandidate` signals. Control-layer priors
are retained for diagnostics but are not ranked as ordinary gateway candidates.

Moscow/SVO airport codes (`MOW`, `SVO`, `DME`, `VKO`, `ZIA`) are protected by
default: a static prior for one of these codes is rejected from ordinary gateway
ranking unless it explicitly sets `allow_as_gateway: true`. Current SVO/Moscow
entries use `control_layer: moscow_svo_control` or
`control_layer: domestic_ru_moscow_airport_control`, so diagnostics expose why
they were skipped while Moscow/SVO route controls remain visible elsewhere.

Provider-returned route evidence is separate from static priors: if a full-route
provider result actually contains an intermediate SVO segment, that
`provider_returned_route` signal can still produce a candidate because it is
observed route evidence, not a static Moscow prior.

## Route Families

| Route family | Category | Injected where | Current behavior |
|---|---|---|---|
| `direct_control` | direct control | `RoutePlanBuilder._build_outbound_ru_priority`, `_build_return_ru_priority`, and global non-RU hub-list direct controls | Adds exact endpoint direct probes with priority `0`. No hardcoded hub, but it is part of RU-priority viability. |
| `svo_asia` | primary gateway | `RoutePlanBuilder._build_outbound_ru_priority`, `_build_return_ru_priority` when `routing_profile == "asia-oceania"` | Adds SVO as an independent Asia/Oceania hub. Outbound adds origin->SVO and SVO->destination; return adds destination->SVO and SVO->origin. |
| `ist_direct` | legacy primary gateway | RU-priority outbound/return builders when gateway-discovery mode is off | Adds IST direct gateway probes. Outbound adds origin->IST; return adds destination->IST and IST->origin. Not emitted when `use_gateway_discovery_for_fallback_hubs` is enabled. |
| `ist_shared_destination` | legacy primary gateway | RU-priority outbound builder when gateway-discovery mode is off | Adds IST->destination second legs for outbound assembly. The route-family metadata table names the broader IST branch as `ist_direct`, while segment rows can carry `ist_shared_destination`. Not emitted when `use_gateway_discovery_for_fallback_hubs` is enabled. |
| `moscow_gateway_control` | Moscow-specific visibility control | RU-priority outbound/return builders plus synthetic runner/reporting | Adds SVO/Moscow control legs and keeps SVO/Moscow alternatives visible even when direct or bridge-gateway options exist. |
| `dxb_direct` | removed fallback gateway | Not emitted by current segment fallback planning | DXB remains available as a data-driven `GatewayDiscovery` candidate from `gateway_priors.yaml` or provider-returned route signals. |
| `domestic_ru` | fallback priors | Domestic-RU outbound/return builders | Adds direct domestic probes plus bounded Moscow-airport hub fallback using `DOMESTIC_RU_HUBS`; excludes IST/DXB by default. |
| `hub_list` | gateway candidates | Hub-list outbound/return builders | Adds one-hop probes through effective `self.hubs`: user-provided hubs or the primary default `DEFAULT_ROUTE_HUBS = ("IST",)`. |

## Strategy-To-Hub Rules

`domain.hubs.resolve_route_hubs()` returns manual hubs if present; otherwise it
returns `DEFAULT_ROUTE_HUBS`. `domain.hubs.resolve_routing_strategy()` maps
`auto` with manual hubs to `hub-list`, and `auto` without manual hubs to
`ru-priority`.

`route_graph.resolve_route_graph_context()` then overrides effective hubs for
strategy-owned cases:

| Strategy/profile | Effective hubs | Category |
|---|---|---|
| `ru-priority`, default profile | legacy `["IST"]`; gateway-discovery mode `[]` | primary gateway in legacy mode; bridge gateways are data-driven discovery candidates in gateway-discovery mode |
| `ru-priority`, `asia-oceania` profile | legacy `["SVO", "IST"]`; gateway-discovery mode `["SVO"]` | SVO Asia gateway remains a control; bridge gateways are data-driven discovery candidates in gateway-discovery mode |
| `domestic-ru` | `DOMESTIC_RU_HUBS` minus endpoint airports, or `["SVO"]` if none remain | fallback priors |
| `hub-list` | manual hubs or `DEFAULT_ROUTE_HUBS = ("IST",)` | gateway candidates |

## Imperative Segment Injection

The current hardcoded segment plan is built in `RoutePlanBuilder`, not in
`SearchPlan.primary_offer_queries`.

Outbound RU-priority:

- Adds exact direct endpoint probes as `direct_control`.
- If Asia/Oceania: adds `origin -> SVO` and `SVO -> destination` as `svo_asia`.
- Legacy mode adds `origin -> IST` as `ist_direct`.
- Adds `origin -> SVO` as `moscow_gateway_control` for origins other than SVO; legacy mode also adds `SVO -> IST`.
- Legacy mode adds `IST -> destination` as `ist_shared_destination`.
- Gateway-discovery mode does not add IST, DXB, or other bridge gateways; they can appear through `GatewayDiscovery` data.
- Adds `MOW/SVO/DME/VKO -> destination` controls through `_gateway_segment_options` as `moscow_gateway_control`.

Return RU-priority:

- Adds exact direct endpoint probes as `direct_control`.
- If Asia/Oceania: adds `destination -> SVO` and `SVO -> origin` as `svo_asia`.
- Legacy mode adds `destination -> IST` and `IST -> origin` as `ist_direct`.
- Adds `SVO -> origin` as `moscow_gateway_control` for origins other than SVO; legacy mode also adds `IST -> SVO`.
- Gateway-discovery mode does not add IST, DXB, or other bridge gateways; they can appear through `GatewayDiscovery` data.
- Adds `destination -> MOW/SVO/DME/VKO` controls through `_gateway_segment_options` as `moscow_gateway_control`.

Domestic-RU:

- Adds direct endpoint probes.
- Adds outbound `origin -> domestic_hub` and `domestic_hub -> destination`.
- Adds return `destination -> domestic_hub` and `domestic_hub -> origin`.
- Domestic hubs are only SVO/DME/VKO after endpoint exclusion; international hubs are not added.

Hub-list:

- Adds direct controls only for global non-RU routes.
- Adds outbound `origin -> hub` and `hub -> destination` for every effective hub.
- Adds return `destination -> hub` and `hub -> origin` for every effective hub.
- Effective hubs are manual hubs or `DEFAULT_ROUTE_HUBS = ("IST",)`.

## Downstream Controls

`LiveAssemblyRunner.skipped_by_condition()` still interprets
`skip_if_priority_route_viable` for compatibility with older plans, but current
`RoutePlanBuilder` no longer emits DXB or secondary fallback segments that use
that skip.

`synthesize_moscow_gateway_control_results()` builds synthetic
`moscow_gateway_control` results from SVO split legs. It intentionally keeps
Moscow as a control, not as a fallback, even when direct or bridge-gateway probes
already have offers.

`frontier_representative_details()` hardcodes two SVO visibility categories:
`all_su_svo` and `moscow_gateway_control`. These force representative SVO/Moscow
options into the frontier even if normal ranking would choose another option.

`agent_report_builder.ru_priority_controls()` hardcodes `primary_hub = "IST"`,
Moscow airport scope from `SPECIAL_CITY_AIRPORTS["MOW"]` plus `MOW`, and branch
keys:

- `direct_destination_control`
- `ist_primary_hub_control`
- `moscow_gateway_control`
- `moscow_via_ist_secondary_control`

Those report controls do not add provider probes, but they define the current
visibility/report contract for RU-priority branches.
