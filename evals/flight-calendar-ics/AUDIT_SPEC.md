# Flight-calendar-ics evaluate audit and behavioral specification

Baseline: branch `SDD-skill`, HEAD `24397661e1729038959f283311ae15be88aad101`; manifest mode `recorded`, candidate source `git:update/flight-calendar-ics`, 3 scenarios, 3 model/provider pairs, 2 repeats (18 configured runs), execution max-turns 10, run-budget 90, evaluator timeout 300s. No production skill file was changed during this audit.

## Existing scenario paths (observed)

- `url-success`: prompt supplies the raw Aeroflot SPA URL. Agent must invoke the candidate CLI using `--url`. Candidate commit `update/flight-calendar-ics` performs route inference, Aeroflot source parsing, request construction, response conversion, contract validation, and ICS rendering. `consumer.py` materializes that candidate into a temporary skills directory and replaces its transport module with `replay/carrier_http.py`. The Aeroflot replay returns the fixture for any request: it currently ignores URL, method, headers, and body. Thus source parsing and conversion/rendering execute, but outbound request fidelity is not tested.
- `ural-url-success`: prompt supplies the direct `https://service.uralairlines.ru/?pnr=…&lastName=…` URL and the agent invokes `--url`. Candidate route detection, Ural source parsing, deployment/config handling, timestamp/API-key generation, reservation response conversion, validation, and ICS rendering execute. The copied replay substitutes HTTP responses, but checks only Ural GET method and host/path; it ignores query values and headers. The reservation fixture itself is raw carrier response JSON; replay does not convert it to itinerary. The prompt does not contain the Ural mail-wrapper URL, so the wrapper-specific source/routing path is outside this scenario.
- `pdf-success`: user supplies `ticket.pdf`; the agent invokes `npx -y @firecrawl/anydoc ticket.pdf -o …`. The eval `npx` shim checks the invocation and input filename/existence, then writes checked-in Markdown without reading/extracting the PDF. The agent must derive private itinerary JSON from that Markdown and call the candidate CLI with `--input`; production source routing, carrier parsing, provider requests, and response conversion are bypassed. Input contract validation and ICS rendering execute. The evaluator can compare retained intermediate flight numbers and final ICS fields.

The recorded evidence includes raw prompts, tool traces, CLI commands/results, copied artifact observations, and (for PDF) intermediate JSON where available. Historical Ural traces show one successful CLI invocation with the direct URL; the 2026-09-22 14:45 batch's saved outcome is FAIL because the final answer was absent, while its copied ICS has two expected events. In the 17:55 batch the same CLI/artifact exists but final answer is empty. The raw Ural evidence currently present does not itself contain a PASS; the supplied known false-PASS report is explained by the unsupported source-path coverage gap: direct service URLs do not exercise the mail wrapper input that failed in production.

## Outcome meaning at baseline

Outcome is not merely `ok:true`, `MEDIA`, and file existence. The deterministic oracle reads the artifact and checks expected VEVENT count, DTSTART/DTEND, and required DESCRIPTION fragments (route/local time/aircraft); PDF also checks intermediate flight numbers. It checks a MEDIA response. It does not read CLI `ok:true` as part of Outcome and does not compare SUMMARY, LOCATION, UID, STATUS, VALARM, or other VEVENT fields. Flight numbers are not present in the Ural ICS DESCRIPTION/SUMMARY, so the Ural artifact oracle cannot currently verify them. The separate trajectory dimension checks CLI success and tool-action constraints.

## Baseline controlled mutation results

All source mutations were applied only after materializing the candidate skill into disposable temporary copies; baseline worktree/production skill was not mutated.

| Mutation | Scenario | Baseline result | Finding |
|---|---|---|---|
| Break route selection for the direct supported Ural input | `ural-url-success` | FAIL (`route_unknown`) | Killed by CLI failure |
| Stop extracting the required Ural PNR from source URL | `ural-url-success` | FAIL (`route_input_insufficient`) | Killed by CLI failure |
| Rename required reservation query key in candidate request | `ural-url-success` | PASS | Survives: replay matches host/path and returns fixture regardless of query values |
| Convert departure airport incorrectly | `ural-url-success` | FAIL (DTSTART/DTEND mismatch) | Killed by semantic output oracle |
| Replace both VEVENT SUMMARY values with `WRONG FLIGHT`, preserving CLI success/MEDIA and all oracle-checked fields | `ural-url-success` | PASS | Proven outcome-oracle gap: SUMMARY is never observed/checked |
| Add a terminal action after the successful CLI, preserving the artifact | `ural-url-success` | Outcome PASS; Trajectory FAIL | Independent dimensions behave as specified; reason `tool call after successful CLI` |

Baseline run command: `PYTHONPATH=/home/konstantin/Hermes-Backup-SDD-skill:/home/konstantin/Hermes-Backup-SDD-skill/evals/flight-calendar-ics python3 /home/konstantin/.hermes/cache/scratch/flight_eval_mutation_baseline.py` (exit 0). It exercised the candidate CLI and evaluator in isolated copies; it did not launch model agents.

## Behavioral specification for evaluate

1. **Source-path fidelity:** Each existing scenario must give the agent the same class of user source input it claims to evaluate. Production route selection, source parsing, and extraction of required credentials must run on that source. A scenario for a direct carrier URL must not be represented as evidence for a mail-wrapper URL. No new carrier scenarios are in scope.
2. **Fixture boundary:** A fixture may replace unavailable external services and return recorded external responses only. It must not pre-parse/normalize source inputs, construct a production request, repair a bad request, or convert a raw carrier response into an itinerary. The candidate production code must perform those transformations.
3. **Request fidelity:** Before returning a response, replay must validate the actual outbound request's destination, method, expected query/body, and required headers for the existing scenario. A mismatch must fail deterministically and must not receive a success fixture. Safe request evidence may redact credential values while retaining match results and field names.
4. **Artifact correctness:** Outcome must parse the resulting ICS and compare segment/event count, expected route, flight identity wherever the final artifact exposes it, times, and required VEVENT properties. It must distinguish an intact success envelope from a semantically wrong artifact. Properties absent from the artifact cannot be claimed as checked; this limitation must be explicit rather than inferred from the input fixture.
5. **Mutation sensitivity:** Controlled routing, mandatory-source-value parsing, request-construction, response-conversion, and ICS-semantic defects affecting an existing scenario must fail at least one deterministic check. Mutation results must record kill/survive and the evidence/reason.
6. **Outcome/trajectory independence:** Outcome evaluates the delivered artifact and response; trajectory evaluates tool sequence/policy. A valid artifact can have Outcome PASS with Trajectory FAIL, and a valid trajectory cannot make a wrong artifact pass.
7. **Deterministic evidence:** Use captured tool calls, process exit/status and structured result, fixture request assertions, intermediate structured input, and parsed ICS as the primary oracles. LLM judgment is not the sole evidence for these contracts.

No evaluator, fixture, or production implementation changes are included in this baseline specification commit. RED checks and minimal changes follow only after this specification.
