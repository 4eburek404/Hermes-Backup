# Eval artifact retention policy

This repository keeps the reusable parts of evaluation in source control and keeps generated run evidence out of the active source tree.

## Tracked

Track material required to define or reproduce evaluator behavior:

- behavioral specifications;
- the shared harness and evaluator/consumer code;
- manifests, prompts, deterministic replay code, expected results, and stable fixtures;
- small curated regression fixtures extracted from real failures when a historical defect needs permanent executable coverage;
- contract tests that protect the observable evaluator contract.

A regression fixture should contain only the evidence needed to reproduce the protected behavior. Record provenance such as the original run identifier or commit when useful.

## Not tracked

Do not add generated evaluation output to the active source tree:

- timestamped `runs/`;
- raw sessions, streams, terminal output, batch reports, scores, and derived evidence produced by those runs;
- ad-hoc `experiments/`;
- `reassessments/` generated from saved evidence;
- generated audit evidence bundles.

Full raw evidence may be retained outside the active source tree when an experiment needs archival reproducibility. It is not a dependency of normal contract tests.

## Promotion rule

When a real run exposes a defect worth protecting:

1. identify the observable defect;
2. extract the smallest stable evidence needed to reproduce it;
3. place that evidence under a deterministic `fixtures/regressions/` path;
4. add an executable check against that fixture;
5. leave the full generated run outside the active source tree.
