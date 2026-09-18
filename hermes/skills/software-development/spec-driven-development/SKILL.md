---
name: spec-driven-development
description: Use for features, bug fixes, contract changes, or refactors.
version: 1.0.0
author: Konstantin Orlov + Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: software-development
    tags: [specification, development, behavior, contract, testing]
---

# Specification-Driven Development

## Goal

Define and verify the behavior that an existing software system must have before
changing its implementation. SDD owns the target specification and its coverage;
it is not TDD, BDD, planning mode, code review, or evaluation.

## When to Use

Use for changes that may affect observable behavior, correctness, data
integrity, compatibility, security, privacy, validation, errors, or a public
contract:

- new features;
- bug fixes;
- behavior or API/CLI/schema changes;
- behavior-sensitive refactors;
- legacy code with misleading or insufficient tests;
- changes to an executable specification that represent a contract change.

Do not run the full SDD process for documentation-only, formatting, or purely
mechanical changes after confirming they cannot change behavior. Do not use it
as the sole skill for pure code review, executable-spec review, planning, or
evaluate tasks.

## Steps

### 1. Inspect before changing

Read the relevant requirements and constraints, code and callers, tests/specs,
public contract/schema, runtime or integration boundaries, and existing
mechanisms. Trace the real path before proposing a design. Do not invent a
system shape or reimplement a mechanism that already exists.

### 2. Separate current state from target state

Record the smallest useful distinction between:

- **observed:** what the current code, runtime, and checks actually show;
- **required:** what the latest confirmed requirement says must be true;
- **unknown:** unresolved facts or bounded assumptions.

Current code, runtime behavior, and green tests are evidence of the current state,
not automatically the desired behavior. A new confirmed requirement that changes
an existing contract is a behavior change.

Ask for clarification only when an unresolved choice materially changes the
observable contract, correctness, or safety and cannot be resolved from the
requirements, code, existing contract, or other authoritative evidence. Otherwise
use the smallest bounded assumption and state it.

### 3. Define target behavior

Before changing production code, define only the relevant target behavior:
inputs, observable outputs, errors, constraints, meaningful edge cases, public
contract, and non-goals. Specify behavior rather than private function names,
class layout, call order, file layout, or framework choice. Given/When/Then is
optional; BDD is not required.

### 4. Map requirements to checks

Treat a requirement as significant when violating it changes observable behavior,
public contract, correctness/data integrity, compatibility, security/privacy, or
reproduces a real defect. Map every significant requirement to an existing
executable check, a new/changed executable check, or an explicitly named manual
or integration verification when automation is impractical.

Audit existing tests/specs against the target behavior. Classify them as correct,
partial, irrelevant, stale, contradictory, or implementation-coupled. A green
suite that does not prove the target behavior is not sufficient.

### 5. Choose the mode and baseline

Use the change map below. Do not impose one RED-first or full-suite ritual on all
changes.

| Change | Minimum evidence | Supporting skill when needed |
|---|---|---|
| Feature | target behavior and relevant current boundary | `test-driven-development` for non-trivial implementation; `ponytail` |
| Bug fix | reproduction of the defect and target behavior | `test-driven-development`; `systematic-debugging` when root cause is unclear |
| Behavior change | current boundary, target boundary, compatibility impact | `test-driven-development`; `executable-spec-review` when runnable spec quality matters |
| Behavior-preserving refactor | evidence of behavior that must remain | `ponytail`; TDD only when checks must change |
| Trivial/mechanical | minimal evidence of no behavioral change | no specialized workflow by default |
| Legacy with insufficient coverage | observed behavior, characterization evidence where needed, target behavior | TDD for changed behavior; `executable-spec-review` for a doubtful runnable spec |

A full test suite is not the default baseline. Use a baseline proportional to the
change: defect reproduction for bugs, preservation evidence for refactors,
current/target boundaries for behavior changes, a relevant current boundary for
new features, and a minimal no-change check for mechanical work.

### 6. Implement the smallest sufficient change

After the target behavior and missing checks are known, prefer existing mechanisms,
stdlib/native features, and already-installed dependencies. Add no unnecessary
abstraction and fix the root cause rather than only the named symptom. Preserve
required validation, security, privacy, compatibility, and error handling even
when a smaller diff would omit them.

### 7. Verify against the target

Run the checks that prove the changed behavior, the required regression protection,
and any relevant preserved behavior. Re-run the selected baseline when needed.
Do not report only “tests passed” unless those tests establish the required
behavior. Record material assumptions, manual checks, and remaining gaps; no
separate traceability document is required.

## Input

Use the existing task/issue/specification and repository evidence. Do not create a
separate specification document unless the project already uses one, the task is
complex enough to need one, or the user explicitly requests it.

## Output

Before completion, the agent must be able to state:

- the target behavior that was implemented or preserved;
- which significant requirements are covered and by which checks;
- which baseline was used and why it was proportionate;
- which assumptions, manual checks, or gaps remain;
- which supporting skills were used, if any.

## Composition with Other Skills

- **`test-driven-development`:** use for the implementation loop when new or
  changed behavior is non-trivial. SDD supplies the target behavior and checks;
  TDD owns RED/GREEN/REFACTOR and regression-test proof.
- **`executable-spec-review`:** use when a significant runnable specification is
  doubtful or needs an independent quality audit. SDD may create or update the
  required check but does not copy the review workflow.
- **`ponytail`:** apply after target behavior is known to minimize code and reuse
  existing mechanisms. It cannot remove required contract or safety behavior.
- **`plan`:** use only when a separate planning artifact, decomposition, or an
  explicit user-requested plan is needed.
- **Evaluate:** outside the ordinary SDD lifecycle; do not analyze trajectory,
  ATOF/ATIF, benchmarking, or efficiency by default.

## Check

Before claiming completion, confirm:

- current behavior was inspected before the production change;
- observed behavior is distinct from target behavior and assumptions;
- target behavior is observable and implementation-independent where possible;
- every significant requirement has an appropriate check or named manual verification;
- misleading, stale, or implementation-coupled tests were not treated as proof;
- the selected mode and baseline fit the change;
- the implementation is minimal without removing required safeguards;
- the changed behavior was verified against the target specification.

## Stop

Stop or ask for clarification when the target contract, correctness, or safety
cannot be determined from available evidence. Do not silently invent behavior.
Do not add a specification document, acceptance-template ceremony, Given/When/Then
format, full-suite run, new executable spec, TDD cycle, executable-spec review,
plan, or long report unless the change actually needs it.

Never:

- encode a known defect as desired behavior;
- treat existing green tests as an authoritative specification without checking them;
- replace public behavior checks with private implementation assertions without cause;
- use minimalism to remove validation, security, privacy, compatibility, or error handling;
- rewrite correct existing behavior merely to satisfy SDD.

## References

Use the existing skills for their owned procedures rather than copying them here:
`test-driven-development`, `executable-spec-review`, `ponytail`, and `plan`.
