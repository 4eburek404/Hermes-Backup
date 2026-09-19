---
name: ponytail
description: "Use when choosing a minimal complete implementation."
homepage: https://github.com/DietrichGebert/ponytail
license: MIT
---

# Ponytail

Ponytail is an implementation constraint, not a development workflow. It
chooses the least complex implementation shape that completely satisfies an
already-defined target and its mandatory safeguards.

## Scope of application

Apply Ponytail while selecting or changing implementation. It is a
cross-cutting constraint on implementation choices, not a separate mandatory
workflow. Do not use it to discover requirements, define the target, plan work
before an implementation decision, investigate a diagnosis, choose testing
policy, review code, or deliver/report work.

## Preconditions

Before using the ladder, confirm that:

- SDD or another authoritative handoff has defined the target behavior,
  including meaningful edge cases and non-goals;
- mandatory constraints and safeguards are known;
- when a bug fix needs diagnosis, systematic-debugging has supplied a sufficient
  root-cause handoff;
- the implementation must satisfy the confirmed target completely.

Ponytail does not decide the requirement's scope. It chooses how to implement
the confirmed scope.

## The implementation ladder

Stop at the first rung that provides the simplest complete implementation of
the confirmed target and safeguards:

1. **Does new code need to exist at all?** Meet the target with the current
   behavior or configuration when that is genuinely sufficient.
2. **Already in this codebase?** Reuse an existing helper, utility, type, or
   mechanism instead of creating a parallel one.
3. **Stdlib does it?** Use the standard library.
4. **Native capability covers it?** Prefer a built-in platform capability over
   a new library or application layer.
5. **Already-installed dependency solves it?** Use the existing dependency;
   do not add a new one for a small sufficient solution.
6. **Simple/direct solution?** Prefer the straightforward implementation over
   an abstraction whose complexity is not required by the target.
7. **Only then:** add the minimum new code and the fewest necessary files.

The ladder is an implementation choice, not a substitute for understanding the
confirmed target. Stop when the chosen shape fully satisfies it; do not stop at
a smaller shape that omits required behavior.

## Implementation rules

- Reuse existing mechanisms before introducing new ones.
- Apply YAGNI: do not add speculative abstractions, interfaces with one
  implementation, factories for one product, configuration for an immutable
  value, or scaffolding for an undefined future.
- Prefer the smallest sufficient diff and fewest necessary files, not the
  smallest diff regardless of completeness.
- Deletion or simplification is valid only when the confirmed target and its
  safeguards remain satisfied.
- If two complete solutions are similarly small, choose the one with the more
  correct edge-case behavior.
- Do not add a new architectural layer merely to make the implementation look
  reusable.

For a bug fix, systematic-debugging owns diagnosis and establishes root cause
when diagnosis is needed. Ponytail consumes that handoff. If the handoff shows
the defect is in a shared mechanism, fix the shared mechanism rather than using
a local symptom workaround solely because it produces a smaller diff.

## Completeness and safeguards

Implement the simplest **complete** version of the confirmed requirement. A
smaller diff is not acceptable if it omits required behavior, required edge
cases, changes a public contract, or defers mandatory validation or error
behavior.

Never simplify away safeguards for validation, security, privacy,
compatibility, accessibility, data integrity, error handling, or any other
explicitly required behavior. When a correct safeguard requires a larger diff,
the larger complete diff is the minimal valid implementation; minimize only the
remaining implementation complexity.

Non-goals may remain unimplemented only when the user or SDD has actually
defined them as non-goals.

## Boundaries

Ponytail owns:

- implementation minimality;
- mechanism and reuse choice;
- avoidance of speculative abstractions;
- selecting the smallest implementation that is complete and safeguarded.

Ponytail does not own:

- target requirements or specification;
- debugging, root-cause discovery, reproduction, hypotheses, data-flow, or
  caller investigation;
- TDD applicability or regression/testing policy;
- whether an assert, demo, test, fixture, or framework is appropriate;
- behavioral verification;
- code review;
- PR, CI, or delivery/reporting.

Those responsibilities remain with the applicable requirements, debugging, TDD,
and review/delivery workflows. Ponytail must not weaken SDD or TDD safeguards
in the name of implementation minimality.
