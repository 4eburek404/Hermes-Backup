# Flow Decision Router for Flight Search

Use this reference when a flight-search task feels ambiguous, the CLI surface is distracting, or the user asks whether the workflow/data flow is well structured.

## Core Finding

The durable problem is not merely "too many commands". A large internal CLI is acceptable when commands have distinct arguments and maintenance/debug responsibilities. The risky gap is when the agent must choose among internal commands before a first-class `flow_decision` classifies the request.

Required first step before provider or command reasoning:

1. classify intent;
2. classify market;
3. classify evidence requirement;
4. then choose the primary command and allowed follow-up probes.

## Minimum Flow Classes

### Intent class

- `route_recommendation` — compare practical itineraries for a route/date.
- `direct_inventory` — all direct/nonstop options across one date or a bounded date range.
- `ticketing_proof` — single PNR, through baggage, fare rules, protected connection, booking/order proof.
- `carrier_or_airport_scope` — named carrier or exact-airport task; answer that scope first.
- `adjacent_mode` — rail comparison, ground/visa/hotel, or non-flight request.
- `maintenance` — inspect/debug/audit/sync the skill, CLI, schemas, or report contract.

### Market class

- `ru_domestic` — both endpoints/airport scopes are Russia.
- `ru_touching_international` — at least one endpoint or segment touches Russia.
- `global_non_ru` — no Russia endpoint/segment in the requested scope.
- `structurally_constrained` — exact airport/carrier/stop/date constraints dominate market defaults.

### Evidence class

- `shopping_advisory` — provider-live search evidence only; price/availability must be rechecked.
- `ticketing_required` — user needs order/booking/through-fare/baggage/protection proof.
- `absence_claim` — negative direct/carrier/airport claims require targeted controls.
- `diagnostic_only` — route validation/ranking without live availability.

## Objective Routing Rules

- `ru_domestic` should use `domestic-ru`: direct exact-airport controls first, Moscow-airport fallback only, no international hubs by default.
- `ru_touching_international` may use `ru-priority`: direct controls, SVO/Moscow controls, IST/DXB/SVO/Asia hubs where profile and geography justify them.
- `global_non_ru` must not silently inherit `ru-priority`/Moscow controls. If the current CLI defaults do this, report it as a routing limitation and either pass explicit routing/hub constraints or label results as advisory/limited.
- Direct inventory/date-window requests are not route recommendations. Use direct-only per-date probes; do not add connected alternatives unless the user asks.
- Ticketing/protection proof is not proven by route search. Require airline/GDS/OTA purchase-screen/order evidence, otherwise say unproven.

## Suggested `flow_decision` Shape

```json
{
  "flow_decision": {
    "intent_class": "route_recommendation | direct_inventory | ticketing_proof | carrier_or_airport_scope | adjacent_mode | maintenance",
    "market_class": "ru_domestic | ru_touching_international | global_non_ru | structurally_constrained",
    "airport_scope": "exact_airport | city_airports | mixed",
    "evidence_class": "shopping_advisory | ticketing_required | absence_claim | diagnostic_only",
    "routing_strategy": "domestic-ru | ru-priority | global-non-ru | hub-list",
    "provider_plan": ["kupibilet", "fli"],
    "primary_command": "search --request",
    "allowed_followups": ["diagnose kb-roundtrip", "diagnose kb-search --direct-only", "diagnose fli-search --direct-only"],
    "limitations": []
  }
}
```

## Audit Signals

Flag the workflow as structurally weak if:

- a fully non-RU route receives `routing_strategy=ru-priority` or Moscow/SVO controls by default;
- `SKILL.md` asks the agent to remember many commands before classifying intent/market/evidence;
- provider-specific probes are used as primary search instead of Level 2 controls;
- `rendered_text` can contradict structured evidence or omit mandatory caveats;
- negative availability claims are made from empty provider output without targeted controls.
