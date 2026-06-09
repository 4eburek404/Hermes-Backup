# Cross-model review for flight-calendar-ics

Use this when asking named models to review CLI-surface/refactor/privacy changes in this skill package.

## Durable pattern

1. Query every model the user named through Hermes CLI, not by substituting your own judgment.
2. Save per-model metadata JSON with at least:
   - `requested_model`
   - `resolved_model`
   - `exit_code`
   - `started_at`
   - `ended_at`
   - `stdout_sha256`
   - `stderr_sha256`
3. Save each raw model response to a local evidence file and report path + sha256, not just an informal summary.
4. Synthesize by separating:
   - consensus findings;
   - single-model dissent;
   - blockers confirmed by code/CLI evidence;
   - false positives caused by truncated review packets.
5. Before accepting a model-reported blocker, verify the relevant source path and/or run the exact CLI surface. Model review is evidence to investigate, not final proof.

## Review packet completeness

Avoid false positives from truncated excerpts. For CLI-surface and privacy reviews, include the complete files or focused excerpts that cover the actual dispatch path:

- command parser/dispatcher containing all relevant subcommands;
- implementation functions for the reviewed command;
- privacy/redaction helpers;
- route-detection code when evidence fields are discussed;
- schemas/registry docs if the claim is about envelope shape or command registration;
- representative tests and latest test output.

If the packet is intentionally bounded, say so in the synthesis and downgrade confidence for any claim that depends on omitted files.

## Known example from 2026-06 review

A minimax-m2.7 review reported two blockers: missing `maint source-runtime-sync` handler and missing `write_performed` in the response. Both were false positives: direct source/CLI verification showed the handler existed and returned `write_performed: false`. The useful durable lesson was not the alleged defect; it was that the review packet had truncated the maint dispatcher enough to invite a plausible but wrong blocker.

A separate glm5.1 note about `route_detection.evidence` was worth checking. A synthetic URL containing dummy sentinel values confirmed the output emitted safe fingerprints such as host/query-field names rather than full private values.
