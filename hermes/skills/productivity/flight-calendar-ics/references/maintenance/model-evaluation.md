# Model Evaluation for Flight Calendar ICS

Use this when comparing changes to the CLI/skill contract across multiple agent models. Keep this reference privacy-safe: never include concrete booking URLs, PNRs, passenger names, ticket/document/contact/payment data, or generated deep-links.

## Purpose

Measure agent behavior around the class-level contract, not just raw CLI speed. The direct CLI should usually be fast; model variance comes from how quickly the agent discovers and follows the host-first `build auto` path without leaking private data, over-auditing source, or reintroducing shell-owned plumbing.

## Stable evaluation pattern

1. **Scope and provenance first.** Record branch, commit short/subject, clean/dirty git status, skill source path, CLI path, and whether the runtime skill was deliberately synced.
2. **Use the same private evidence across compared runs.** Store credential-bearing URLs in a private file such as `/tmp/flight_ics_private_input/url.txt` with mode `0600`; do not print or read the file into the model-visible transcript.
3. **Use the host-first golden path.** For carrier URLs and canonical itinerary JSON, the harness/subagents should read `SKILL.md` once, then run exactly one normal generation command: `--json build auto --url-file <private-file>` or `--json build auto --input <itinerary.json>`. Do not use explicit `build <route>` for happy-path model eval unless the eval is deliberately testing diagnostics. Do not use `mktemp`, `chmod`, `tee`, `--output-ics`, `--output-json`, or stdout redirection on the happy path. `--output-dir` is acceptable for reproducible diagnostics/eval artifacts.
4. **Validate envelope, not private content.** Require:
   - `schema_version == flight-calendar-ics-cli.v1`
   - `ok is true`
   - `command == build`
   - `data.route` is the expected carrier or `make`
   - `data.route_detection.mode == auto`
   - `data.route_detection.evidence` contains only safe host/field/category labels
   - `data.segments_count >= 1`
   - `data.verification.ok is true`
   - `data.ics_path` exists and generated artifacts intended for private use are mode `0600`.
5. **Privacy scan before reporting.** Check stdout, stderr, JSON envelopes, summaries, and comparison reports for booking URLs, PNR-like values, names, tokens, keys, and full `.ics` descriptions. Report only redacted/safe metrics.
6. **Compare against previous runs with the same task and model set.** Track at minimum success, elapsed seconds, tool calls, route, whether `doctor` was used, selected command, route detection, envelope verification, and privacy status.

## Recommended comparison fields

- `model`
- `provider`
- `current_elapsed`
- `current_success`
- `current_tool_calls`
- `current_used_doctor`
- `current_command`
- `current_route`
- `current_route_detection_mode`
- `current_privacy_ok`
- `prev_<baseline>_elapsed`
- `prev_<baseline>_success`
- `delta_vs_<baseline>_sec`
- `delta_vs_<baseline>_pct`

Session IDs and output directories may be kept in local JSON artifacts for auditability, but omit them from compact chat summaries unless needed for troubleshooting.

## Reporting shape

Start with status and verification, then compact per-model bullets. Telegram has no table syntax, so prefer bullets with `current`, `previous`, and `delta` fields over markdown pipe tables. Make the interpretation explicit:

- direct CLI elapsed indicates CLI overhead;
- model wall-clock reflects agent/tool-loop behavior and provider/network variance;
- one run per model is directional, not statistically stable;
- a slower result may be acceptable if contractness/privacy/error rate improved.

## Interpreting model-size paradoxes

If larger models get slower while smaller models speed up, first separate CLI time from agent-loop time with a direct CLI smoke test. In observed bundle evaluations, the CLI itself was about one second; most wall-clock variance came from agent behavior: reading/inspecting skill docs, running `doctor`, provenance checks, privacy checks, wrapper retries, verification scripts, and final reporting.

Typical pattern:

- fast/smaller models often treat `SKILL.md` and the CLI envelope as a recipe and stop after `build auto` + envelope verification;
- cautious/larger models may treat the same contract as an audit surface and spend extra turns proving branch/source provenance, dispatch shape, privacy boundaries, or skill quality;
- a bundle CLI can reduce deterministic work but still increase perceived compliance surface unless the prompt/skill explicitly says to avoid source/reference inspection on successful happy paths.

When reporting the cause, say "agent/tool-loop over-audit around the contract" rather than "CLI got slower" unless the direct CLI smoke also regressed.

For future eval harnesses/subagent prompts, include an anti-overthinking clause:

```text
Fast path: read SKILL.md once, run exactly one `--json build auto --url-file <private-file>`, verify only envelope/path/mode/counts/route_detection, do not run doctor, inspect source/references/generated .ics content, or patch the skill unless build/verification fails, and stop after successful envelope verification.
```

## Pitfalls

- Treating fastest happy-path latency as the only objective. This skill optimizes deterministic private artifact generation and verification.
- Comparing runs that used different evidence, route selection rules, or output plumbing.
- Letting subagents dump private URL or `.ics` descriptions into stdout for debugging.
- Reporting full output directories or session narratives instead of distilled metrics.
- Interpreting provider wall-clock differences as CLI performance without a direct CLI smoke test.
