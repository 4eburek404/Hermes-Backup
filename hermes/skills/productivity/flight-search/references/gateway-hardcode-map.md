# Gateway Policy Map

Runtime gateway selection is policy/config driven. It must not depend on route-specific Python branches for one origin, destination, airport, or carrier.

## Current Rules

| Policy area | Current owner | Rule |
| --- | --- | --- |
| Default bridge hints | `config.py` / route access profile data | May seed gateway discovery when the request has no explicit gateway constraint. |
| Explicit gateway request | `pipeline/options.py`, `orchestrators/search_plan_builder.py` | Becomes a hard planner seed and hard scorer gate through `must_include_airports`. |
| Provider-returned gateways | `domain/gateway_discovery.py` | Provider full-route offers can add gateway evidence. |
| Control probes | `execution/aggregate_control_runner.py`, policy config | Controls are evaluated from existing graph evidence before spending provider budget. |
| Frontier sections | `pipeline/decision_scorer.py` | Route options and controls stay separate in DecisionFrontier. |

## Invariants

- Defaults can fill gaps only when the user did not constrain the route.
- Explicit constraints outrank all default bridge hints.
- Moscow/RU visibility is a control-policy concern, not a runtime branch.
- No runtime logic may special-case `NTE`, `AMS`, `SVX`, or `KLM`.
- Route-specific provider data belongs in fixtures, policy/config, or provider evidence, not in Python conditionals.

## Audit

Architecture tests guard removed imports and route-specific runtime literals. Use this file only as the policy owner map; do not add old segment-plan behavior back here.
