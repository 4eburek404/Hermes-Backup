# Provider Failover

Provider routing is per probe. `auto` does not mean "run every provider"; it means choose the best supported provider sequence for each probe.

## Policy

| Provider | Role |
| --- | --- |
| Tutu | Primary provider for aggregate and direct offer evidence. |
| KupiBilet | Fallback when capability and market allow the probe. |
| FLI | Fallback for non-RU probes only. |

`provider_policy=both` is rejected. Use `provider_policy=tutu`, `kupibilet`, or `fli` only when a diagnostic or user request needs a forced provider.

## Failure Handling

- A provider failure should be recorded in the probe ledger and report diagnostics.
- If hard constraints have no satisfying options and budget remains, the planner may use policy fallback probes.
- Control probes may pin a provider when product visibility requires cross-provider evidence.
- Live smoke checks are opt-in; fixture tests are the merge gate.

## Answering

Answer from `agent_report.user_answer.rendered_text`. If DecisionFrontier has route options, the user answer must show those flights even when no legacy assembly fields exist.

## Diagnostics

```bash
python3 -m flights_cli --json diagnose plan --request "$HOME/flight-search-request.json"
python3 -m flights_cli --json diagnose probe --provider tutu --request "$HOME/probe.json"
python3 -m flights_cli --json diagnose tutu-search --request "$HOME/tutu-search.json"
```

Use provider diagnostics to explain evidence boundaries, not as final traveler text.
