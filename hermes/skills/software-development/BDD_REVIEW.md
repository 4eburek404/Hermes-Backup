# BDD review — software-development

Status: review completed against the mandatory BDD rule. The
software-development owner migration to BDD is implemented; remaining reviewed
cleanups are tracked below.

## Review rule

A development skill is acceptable when it helps Hermes reach and verify required
observable behavior without making internal implementation details part of the
contract. Skill names, private symbols, file layout, internal call order, and
wording inside SKILL.md are not acceptance criteria unless a public contract
explicitly exposes them.

## behavior-driven-development

**Status: owner migration implemented.**

The new owner retains the useful behavior identified by this review:

- inspect the existing system before changing it;
- separate observed state, required state, and unknowns;
- define observable inputs, outputs, errors, constraints, edge cases, and
  non-goals;
- map significant requirements to executable evidence;
- distinguish current behavior from desired behavior;
- avoid treating existing green tests as automatically authoritative.

The migration also establishes the target model:

- BDD is mandatory for behavior-changing development work;
- target behavior is expressed through concrete observable examples before
  implementation;
- executable specifications exercise the closest useful public/observable
  boundary;
- checks accept different internal implementations that satisfy the same
  behavior;
- BDD owns behavior, examples, preserved behavior, and acceptance evidence, not
  implementation structure;
- the absent executable-spec-review owner is not a required route.

The historical `spec-driven-development` skill remains only as a temporary
compatibility alias until dependent GitHub workflows are migrated.
## test-driven-development

**Status: BDD ownership handoff clarified; broader heuristic cleanup remains.**

Keep:

- regression-capable RED before implementing new/changed non-trivial behavior;
- GREEN and refactor with evidence;
- reuse/update/delete existing tests instead of accumulating stale tests;
- real behavior over mocks where practical;
- revert-to-red for bug fixes to prove a regression check is effective.

Change:

- TDD consumes BDD behavior; it does not define the requirement;
- engagement is triggered by behavior needing regression protection, not by
  whether a function/method/component happens to contain branching;
- permanent tests must protect observable behavior/public contracts rather than
  private symbols or chosen architecture;
- "one test per feature-group" and test-count guidance remain heuristics, not
  externally enforced contracts;
- subagent delegation is an optimization, not a correctness requirement;
- documentation/eval references must point to files that actually exist.

BDD relationship:

BDD scenario -> regression representation -> RED -> implementation -> GREEN ->
refactor -> scenario still GREEN.

## systematic-debugging

**Status: compatible; BDD handoff updated.**

Keep:

- diagnostic reproducer;
- root-cause evidence before a production bug fix;
- one-variable hypothesis testing where diagnosis is non-obvious;
- explicit handoff of confirmed cause and invariants.

Change:

- diagnosis does not define target behavior;
- the target behavior comes from BDD;
- a diagnostic reproducer may inspect internals, because it is diagnostic
  evidence, but permanent regression protection must return to the observable
  BDD boundary where practical;
- SDD references must become BDD references;
- absent related-skill references must not be mandatory for correctness.

## ponytail

**Status: structurally compatible; BDD target source updated.**

Keep:

- implementation minimality only after target behavior is known;
- reuse existing mechanisms;
- YAGNI;
- smallest complete implementation, not smallest diff at the cost of behavior.

Change:

- replace SDD as authoritative target source with BDD;
- make explicit that minimality cannot narrow an executable scenario or public
  acceptance behavior.

## plan

**Status: requires substantial cleanup.**

Problems:

- current plan template starts from architecture/files/code before a behavioral
  acceptance model;
- it requires exact paths and complete code too early for tasks where
  implementation should remain undecided until behavior/current mechanisms are
  understood;
- it hard-depends on currently absent subagent-driven-development and
  requesting-code-review skills.

Required behavior:

- when planning a behavior-changing task, start with target behavior/examples,
  preserved behavior, acceptance evidence, and constraints;
- only then describe the likely implementation route;
- implementation details in a plan are proposals, not acceptance criteria;
- remove mandatory references to owners that do not exist in the repository;
- planning must not force tests to encode planned private structure.

## Verification mapping

The current BDD eval protects:

- feature-shout: new behavior plus preserved old behavior;
- bug-boundary: changed boundary behavior plus neighboring preserved behavior;
- refactor-preserve: implementation may change while behavior remains stable;
- behavior-equivalent substitution: generated tests must accept a different
  implementation with the same observable behavior.

The next missing behavioral coverage is:

- trivial/mechanical change without unnecessary test ceremony;
- review-only task that must not mutate the checkout;
- issue-to-development orchestration;
- PR/CI/delivery behavior.

Do not rewrite production skills until the current baseline for these scenarios
has been captured.
