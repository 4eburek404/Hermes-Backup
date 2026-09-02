# Reference Index and Ownership Map

This file is the canonical map for `flight-search` support references. `SKILL.md` links here for anything outside the happy path. Keep this index small and keep each referenced file single-purpose.

## Operating rule

- Start with the Golden Path in `SKILL.md`: run `python3 -m flights_cli search --request ...` and return stdout verbatim. Use `--json` only when structured diagnostics are needed.
- Load a reference only when the current task crosses its trigger below.
- Before changing a reference, verify the rule against current code, schema, or tests. If a rule cannot be verified, keep it out of active docs or label it as a source-boundary caveat.
- Do not create incident, audit, proposal, smoke, or handoff Markdown in `references/`. Distill durable behavior into the owner file below, CLI code/schema/tests, or session history.
- When two files seem to own the same rule, update this index first, then move the rule into the listed owner and replace duplicates with cross-references.

## Canonical references

| File | Owns | Load when | Non-goals |
|---|---|---|---|
| `report-contract.md` | How to read `data`; `flight_search_result.v10`; `flight_search_user_answer.v11`; canonical answer path; renderer guarantees. | You need to decide what to show the traveler, inspect report fields, or maintain report/user-answer schema/renderer behavior. | Provider dispatch, source/proof taxonomy, route-pipeline internals. |
| `source-boundaries.md` | Evidence classes, absence taxonomy, airport/city/ticketing boundaries, connection/MCT policy, adjacent non-flight source boundaries, static-catalog limits, provider/source caveats. | You need to phrase confidence/absence/ticketing claims, decide whether a caveat is decision-useful, or classify non-dated route-network/RZD comparison evidence. | Route planning mechanics and provider dispatch internals. |
| `pipeline-reference.md` | Current data flow from `flight_search_request.v1` to `flight_search_result.v10`; flow decision, route hypotheses, provider/airport dispatch, direct-first gate, date-window mode, compact report assembly, and data artifacts. | You need to debug or maintain how the CLI makes route decisions, how direct/connected options are assembled, how provider/airport scope is chosen, or how fields move between stages. | Targeted live-probe recipes and traveler-facing caveat wording. |
| `debug-playbook.md` | Bounded diagnostic workflow: runtime provenance, JSON extraction, targeted provider probes, suppressed/missing gateway-chain triage, and diagnostic split patterns. | The Golden Path report is inconsistent, sparse, degraded, or surprising, and a narrow probe could change the answer. | Normal route search; do not expose debug output as the traveler answer. |
| `cli-maintenance.md` | Source/runtime governance, CLI JSON stdout/stderr rules, contract/schema lifecycle, provider-port maintenance, renderer tests, generated artifacts, reference lifecycle. | The task is inspect/debug/refactor/sync/version/test work on the skill or CLI. | Traveler-facing route search and provider-live evidence. |

## Routing examples

| Situation | Read |
|---|---|
| Report answer/read order, final answer source, renderer/schema change | `report-contract.md` |
| Single PNR, baggage-through, refund/exchange/fare-rule proof | `source-boundaries.md` |
| Empty provider output, absence language, structural vs provider/horizon uncertainty | `source-boundaries.md` |
| Exact airport vs city scope and provider endpoint validation | `pipeline-reference.md` for dispatch mechanics; `source-boundaries.md` for wording |
| Global non-RU must not inherit RU-specific routing; market classification | `pipeline-reference.md` |
| Gateway defaults, provider-returned gateways, or hardcoded route/gateway audit | `pipeline-reference.md` |
| Short/missing direct set, direct-first gate, connected suppression, output caps | `pipeline-reference.md` first; `debug-playbook.md` only if a narrow live probe is needed |
| Direct/nonstop options across several dates | `pipeline-reference.md` |
| Provider failure, suspected horizon/coverage gap, targeted carrier/direct probe | `debug-playbook.md` |
| User specifies exact routing (via X→Y→Z), CLI doesn't assemble it | `pipeline-reference.md` for constraint/gateway mechanics; `debug-playbook.md` for narrow leg probes |
| Route network without a date, or train-vs-flight price/time comparison | `source-boundaries.md` for source boundaries; do not treat these as normal live-ticket search |
| Source/runtime parity, branch/publish/sync, generated artifacts, schema/test updates | `cli-maintenance.md` |

## Reference lifecycle

A reference remains canonical only if it owns a stable function in the table above. Historical fixes, flow-decision design notes, route examples, provider bug reports, and hardcode audits should live in the owner file as compact rules/tests, not as separate active Markdown.
