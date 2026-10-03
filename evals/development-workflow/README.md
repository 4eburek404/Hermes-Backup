# Development workflow agent evaluation

This eval is the first BDD-level contract for the 'software-development' and
'github' skill families.

It runs Hermes against small real fixture repositories and judges the resulting
repository behavior. Skill loading/routing is recorded for diagnosis but is not
used as an acceptance oracle.

## Baseline

The baseline owner is pinned to branch state `ddab90073d5b00e44c0b2987217eef6ae14f67fb`,
before the BDD migration. The controlled skill-behavior matrix selects
`spec-driven-development` for baseline and `behavior-driven-development` for
candidate. Only the selected owner skill is materialized from that version; all
other skills are shared from the working tree so the owner remains the only
source-level experimental variable.

## Run

'python3 evals/development-workflow/run_eval.py --mode skill-behavior'

For one scenario:

'python3 evals/development-workflow/run_eval.py --mode skill-behavior --scenario bug-boundary'

For a quick candidate-only run:

'python3 evals/development-workflow/run_eval.py --mode skill-behavior --scenario feature-shout --version candidate'

The primary skill-behavior experiment explicitly passes the configured owner
with Hermes CLI `--skills`. To audit autonomous skill routing separately, run
`python3 evals/development-workflow/run_eval.py --mode natural-routing`; that
mode does not force a skill and must not be treated as evidence of a particular
skill's effect. The manifest pins the controlled owner to
`behavior-driven-development`.

Run the deterministic evaluator checks with:

'python3 -m pytest -q tests/contract/test_development_workflow_eval_consumer.py'

## Acceptance model

A scenario passes from observable evidence:

- black-box behavior probes;
- the fixture's executable verification;
- the same verification passing against a behavior-equivalent implementation
  with a different internal structure;
- preservation of protected unrelated files;
- absence of destructive/delivery actions that contradict the task.

A scenario does **not** pass because a particular skill was loaded, a particular
file/function was used, or a particular internal implementation shape appeared.
Trajectory evidence is assessed semantically from observed behavior and
verification events: feature/bug scenarios require RED before production change
and GREEN after; refactor requires GREEN before and after, with preserved
behavior. Missing or ambiguous trace evidence is non-pass.

The existing source-text GitHub contract tests are migration-era checks. Do not
extend them with new wording/name assertions; replace their useful requirements
with agent-level behavioral scenarios over time.
