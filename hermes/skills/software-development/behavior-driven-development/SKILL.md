---
name: behavior-driven-development
description: Primary development workflow for features, bug fixes, behavior/contract changes, and behavior-sensitive refactors; define observable examples and acceptance evidence before implementation.
version: 1.0.0
author: Konstantin Orlov + Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: software-development
    tags: [bdd, behavior, examples, acceptance, development, contract, testing]
---

# Behavior-Driven Development

## Goal

Define the observable behavior a software system must provide before changing its
implementation, express significant behavior through concrete examples, and
verify those examples at the closest useful public or observable boundary.

BDD owns target behavior, examples, acceptance evidence, and preserved behavior.
It does not own private implementation structure, debugging diagnosis, the
RED/GREEN/REFACTOR mechanics, code review, delivery, or evaluation.

## When to use

Use this workflow for changes that may affect observable behavior, correctness,
data integrity, compatibility, security, privacy, validation, errors, or a public
contract:

- new features;
- bug fixes;
- behavior or API/CLI/schema changes;
- behavior-sensitive refactors;
- legacy code where the behavior to preserve or change is not adequately proven.

For documentation-only, formatting, or genuinely mechanical work, first confirm
that observable behavior cannot change. Then use only proportionate verification;
do not manufacture BDD/TDD ceremony.

Pure review, planning, evaluation, CI/delivery, and release work have their own
owners. They may consume BDD evidence but are not owned by this skill.

## Workflow

### 1. Inspect the current system

Before production changes, inspect the relevant requirements, code path, callers,
existing tests/specifications, public contract or schema, runtime boundaries, and
existing mechanisms.

Establish the relevant current behavior by executing the system or a suitable
existing check at an observable boundary when practical. Source inspection alone
is not proof of runtime behavior.

### 2. Separate observed, required, and unknown

Keep three facts distinct:

- **observed** — what the current system and checks actually demonstrate;
- **required** — what the latest confirmed user or contract requirement demands;
- **unknown** — unresolved facts or bounded assumptions.

Existing code and green tests are evidence of the current state, not automatic
authority for the desired state. Never encode a known defect as required
behavior.

Ask for clarification only when an unresolved choice materially changes the
observable contract, correctness, or safety and cannot be resolved from available
evidence.

### 3. Define behavioral examples

Before changing production implementation, describe the smallest set of concrete
examples needed to distinguish required behavior from current behavior.

Each relevant example identifies:

- the starting context or input;
- the observable action/event;
- the expected observable result;
- preserved behavior that must remain true;
- meaningful error, boundary, safety, or compatibility cases when relevant.

Given/When/Then is optional. The examples must not prescribe private function
names, classes, file layout, call order, framework choice, or an algorithm unless
that detail is itself part of the public contract.

### 4. Map examples to acceptance evidence

For each significant example, use the closest useful executable public/observable
boundary.

Prefer, in order:

1. an existing executable check that already proves the example;
2. an existing check updated to the new target;
3. a new executable check when coverage is genuinely missing;
4. an explicitly named manual/integration verification when automation is
   impractical.

A check is valid only if another internal implementation that provides the same
required behavior could still pass it.

Audit existing checks against the target. Do not treat stale,
implementation-coupled, or irrelevant tests as acceptance evidence merely because
they are green.

### 5. Select the change path

**New or changed behavior requiring regression protection**

1. Observe the relevant current behavior.
2. Define the target example and executable acceptance check.
3. Run the check against the current implementation and observe the expected RED.
4. Hand implementation to `test-driven-development`.
5. Verify GREEN on the same behavior and confirm required preserved behavior.

**Bug fix**

BDD defines the required behavior. If the cause is not already established,
`systematic-debugging` owns diagnosis and returns root-cause evidence and
invariants. Then TDD owns the regression RED, implementation, GREEN, refactor, and
revert-to-red proof where appropriate.

**Behavior-preserving refactor**

Do not manufacture RED. Establish the behavior to preserve with existing or
characterization checks, refactor, then verify the same behavior again.

**Trivial/mechanical work**

Establish enough current behavior to show the change is non-behavioral, make the
minimal edit, and run proportionate verification. Do not change executable
specifications or create an artificial RED merely to satisfy a workflow ritual.

### 6. Implement through the applicable supporting workflow

Once target behavior and acceptance evidence are established:

- `test-driven-development` owns regression representation and
  RED/GREEN/REFACTOR for non-trivial new or changed behavior;
- `systematic-debugging` owns diagnosis when root cause is not sufficiently
  known;
- `ponytail` constrains implementation to the smallest complete solution after
  the target is known;
- `plan` is used only when a separate planning artifact is actually needed.

BDD must not prescribe implementation structure merely to make the work easier to
test.

### 7. Verify against the behavior

Before completion, verify the examples that prove the changed behavior and the
required preserved behavior. Use a verification scope proportional to the change.

Do not report only “tests passed” unless those tests actually establish the
required behavior. State material assumptions, manual checks, and unresolved gaps.

## Output handoff

For implementation work, the BDD handoff contains only what downstream workflows
need:

- observed behavior relevant to the change;
- required behavioral examples;
- preserved behavior and constraints;
- executable acceptance evidence and its current result;
- material unknowns or assumptions.

It does not require a separate specification document unless the project already
uses one, the task is complex enough to need one, or the user requests it.

## Completion check

Before claiming completion, confirm:

- relevant current behavior was established before production changes;
- observed and required behavior were kept distinct;
- target behavior was expressed through concrete observable examples;
- significant examples have executable or explicitly named manual evidence;
- checks protect behavior rather than a chosen implementation;
- RED preceded implementation where changed behavior requires regression
  protection;
- refactors and mechanical work did not manufacture unnecessary RED;
- changed and preserved behavior were verified after implementation;
- supporting skills stayed within their own responsibilities.

Stop and ask for clarification when the required observable contract,
correctness, or safety cannot be established from available evidence.
