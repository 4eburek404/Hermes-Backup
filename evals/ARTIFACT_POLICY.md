# Eval artifact lifecycle

Generated eval evidence is temporary working material, but it may be committed to a development branch when another agent or reviewer needs the actual run evidence.

## During development and evaluation

It is acceptable to commit full run evidence to the working branch when it is needed to inspect or verify the work, including:

- timestamped `runs/`;
- raw sessions, streams, terminal output, reports, scores, and derived evidence;
- ad-hoc `experiments/`;
- `reassessments/`;
- generated audit evidence bundles.

This is a transport and review mechanism between development/evaluation steps. These files are not automatically permanent repository content.

## Before merge to main

Clean generated eval evidence from the final PR diff before merging to `main`.

Keep the durable parts:

- behavioral specifications;
- shared harness and evaluator/consumer code;
- manifests, prompts, deterministic replay code, expected results, and stable fixtures;
- contract tests that protect observable behavior;
- small curated regression fixtures extracted from real failures when permanent executable coverage is useful.

Remove temporary run evidence unless it has been deliberately promoted into a stable fixture or another durable input.

## Promotion rule

When a real run exposes a defect worth protecting:

1. identify the observable defect;
2. extract the smallest stable evidence needed to reproduce it;
3. place that evidence under a deterministic fixture path;
4. add an executable check against that fixture;
5. remove the full generated run from the final PR diff.

The cleanup requirement applies to the result merged into `main`, not to intermediate development branches.
