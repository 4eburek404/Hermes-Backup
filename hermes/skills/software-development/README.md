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

## Ownership model under review

The existing skills remain usable while the BDD migration is performed, but
their boundaries are being revalidated from behavior first:

- behavior/specification owner — defines target observable behavior and examples;
- 'systematic-debugging' — establishes root cause when diagnosis is required;
- 'test-driven-development' — implements changed behavior through a
  regression-capable RED/GREEN/REFACTOR loop where appropriate;
- 'ponytail' — constrains implementation to the smallest complete shape;
- 'plan' — creates a planning artifact when planning is actually requested.

The existing 'spec-driven-development' wording is legacy during this migration
because it explicitly states that BDD is optional. Do not treat that statement
as the target architecture.

## Verification

The canonical migration eval is:

'evals/development-workflow/'

Its acceptance criteria are black-box behavior, preserved behavior, safety, and
verified results. Skill names and routing are retained only to explain failures
or unnecessary work.

Legacy repository tests that parse skill prose remain temporary evidence of the
old design. Do not add new source-text assertions when a behavioral scenario can
express the requirement.
