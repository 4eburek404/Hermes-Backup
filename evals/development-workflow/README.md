# Development workflow agent evaluation

This eval is the first BDD-level contract for the 'software-development' and
'github' skill families.

It runs Hermes against small real fixture repositories and judges the resulting
repository behavior. Skill loading/routing is recorded for diagnosis but is not
used as an acceptance oracle.

## Baseline

The baseline is pinned to branch state 'ddab90073d5b00e44c0b2987217eef6ae14f67fb',
before the BDD migration. The candidate uses the working-tree versions of:

- 'hermes/skills/software-development/'
- 'hermes/skills/github/'

Other skills remain identical between baseline and candidate.

## Run

'python3 evals/development-workflow/run_eval.py'

For one scenario:

'python3 evals/development-workflow/run_eval.py --scenario bug-boundary'

For a quick candidate-only run:

'python3 evals/development-workflow/run_eval.py --scenario feature-shout --version candidate'

Run the deterministic evaluator checks with:

'python3 -m pytest -q tests/contract/test_development_workflow_eval_consumer.py'

## Acceptance model

A scenario passes from observable evidence:

- black-box behavior probes;
- the fixture's executable verification;
- preservation of protected unrelated files;
- absence of destructive/delivery actions that contradict the task.

A scenario does **not** pass because a particular skill was loaded, a particular
file/function was used, or a particular internal implementation shape appeared.

The existing source-text GitHub contract tests are migration-era checks. Do not
extend them with new wording/name assertions; replace their useful requirements
with agent-level behavioral scenarios over time.
