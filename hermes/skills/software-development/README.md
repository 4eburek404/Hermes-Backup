# Software development skills

## Development model

Behavior-Driven Development (BDD) is the governing development model for this
skill family.

Before implementation changes, establish the target observable behavior and its
meaningful examples. Significant behavior is protected by executable
specifications at the closest useful public/observable boundary.

### Test design rule

Executable specifications and tests protect **behavior**, not a chosen
implementation.

Do not make a test pass/fail merely because of:

- a private function, class, helper, or module name;
- a particular internal file layout;
- an internal call sequence that is not itself a contract;
- the exact wording, heading structure, or owner names inside a 'SKILL.md';
- a chosen abstraction or algorithm when several implementations satisfy the
  same required behavior.

Such details may be fixture/setup mechanics or diagnostic evidence. They become
acceptance criteria only when they are genuinely part of a public/user-visible
contract.

## Ownership model

- 'behavior-driven-development' — owns target observable behavior, concrete
  examples, acceptance evidence, and preserved behavior;
- 'systematic-debugging' — establishes root cause when diagnosis is required;
- 'test-driven-development' — consumes the BDD handoff and owns
  regression-capable RED/GREEN/REFACTOR where appropriate;
- 'ponytail' — constrains implementation to the smallest complete shape after
  target behavior is known;
- 'plan' — creates a planning artifact when planning is actually requested.

`spec-driven-development` has been retired. Active workflows use
`behavior-driven-development`; historical evaluation records and pinned baseline
artifacts remain unchanged for reproducibility.

## Verification

The canonical migration eval is:

'evals/development-workflow/'

Its acceptance criteria are black-box behavior, preserved behavior, safety, and
verified results. Skill names and routing are retained only to explain failures
or unnecessary work.

Legacy repository tests that parse skill prose remain temporary evidence of the
old design. Do not add new source-text assertions when a behavioral scenario can
express the requirement.
