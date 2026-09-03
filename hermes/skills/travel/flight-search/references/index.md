# Reference Index and Ownership Map

This file is the canonical map for `flight-search` support references.
`../SKILL.md` links here for anything outside the Golden Path. Keep this index
small and keep each referenced file single-purpose.

## Operating rule

- Start with the Golden Path in `../SKILL.md`: `search --request` with three
  fields, and return stdout as it comes. Use `--json` when you need the
  structured answer.
- Load a reference only when the current task crosses its trigger below.
- Before changing a reference, verify the rule against current code, schema, or
  tests. A rule that cannot be verified does not belong in an active document.
- Do not create incident, audit, proposal, smoke, or handoff Markdown here.
  Durable behaviour belongs in the owner file below, or in code, schema, and
  tests; everything else belongs in session history.
- When two files seem to own the same rule, fix this index first, then move the
  rule into the listed owner and replace the duplicate with a cross-reference.

## Canonical references

| File | Owns | Load when |
|---|---|---|
| `report-contract.md` | `flight_search_result.v1`: the six keys, option/ticketing/connection/evidence fields, the canonical text path, and what the frontier dropped before you saw it. | You are deciding what to show the traveler, inspecting answer fields, or changing the result schema or renderer. |
| `source-boundaries.md` | What a result can prove: evidence classes, absence taxonomy, airport and city boundaries, MCT and connection thresholds, the ticketing evidence hierarchy, provider caveats, adjacent non-flight sources. | You are phrasing a confidence, absence, or ticketing claim, or classifying route-network and rail evidence. |
| `cli-maintenance.md` | Source and runtime governance, stdout/stderr rules, contract lifecycle, module ownership, required validation, runtime provenance. | The task is inspect, refactor, version, test, or release work on the CLI. |

Three files, three questions: what the answer says, what it can prove, and how
to change the thing that produced it.

## Routing examples

| Situation | Read |
|---|---|
| Option order, what an option field means, why an option is missing | `report-contract.md` |
| Single PNR, baggage-through, refund or fare-rule proof | `source-boundaries.md` |
| Empty provider output, absence wording, horizon versus coverage | `source-boundaries.md` |
| Exact airport versus city scope | `source-boundaries.md` |
| A provider failed, or the search came back bounded | `report-contract.md` for `evidence`; `source-boundaries.md` for the wording |
| Route network without a date, or train-versus-flight comparison | `source-boundaries.md` — not a live-ticket search |
| Source/runtime parity, schema or test changes, publishing | `cli-maintenance.md` |

## Reference lifecycle

A reference stays canonical only while it owns a stable function in the table
above. Historical fixes, design notes, route examples, and provider bug reports
belong in the owner file as compact rules — or in a test — not as a separate
active document.

Two files left this directory in C6: `pipeline-reference.md` described a
gateway and route-hypothesis pipeline that no longer exists, and
`debug-playbook.md` read a diagnostic envelope that no longer exists. What
remained true in them is above.
