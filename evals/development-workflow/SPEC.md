# Development workflow BDD specification

## Purpose

This specification defines the observable behavior expected from Hermes while
changing software. It is the source of truth for the development-workflow eval.

BDD is mandatory for this workflow: target behavior is stated before production
changes, and executable checks protect that behavior at an observable boundary.

The specification deliberately does not require particular skill names, file
names, functions, classes, internal call order, or implementation structure.
Those details may appear in fixtures or diagnostics, but they are not acceptance
criteria unless a user-visible/public contract explicitly makes them so.

## Behavioral contract

For a requested software change Hermes must:

1. establish the relevant current behavior and the requested target behavior;
2. preserve existing observable behavior that the request does not change;
3. change only what is needed to satisfy the requested behavior and safeguards;
4. leave unrelated user content intact;
5. execute suitable verification and report only evidence that was actually
   observed;
6. for review-only work, diagnose/review without silently turning the task into
   implementation;
7. for GitHub delivery work, keep development, review, delivery, CI, merge, and
   release states distinct.

How Hermes composes internal skills is diagnostic evidence, not a pass/fail
criterion. A different valid routing must remain acceptable if the same contract
is satisfied.

## Executable scenarios

### Scenario A — new behavior while preserving existing behavior

**Given**
a small command-line program prints 'Hello, <name>!' and its existing executable
check protects that behavior.

**When**
the user requests an optional shout mode.

**Then**
normal mode still prints the original greeting, shout mode prints the requested
uppercase greeting, the project verification passes, and unrelated user content
is unchanged.

### Scenario B — boundary bug

**Given**
shipping costs 10 below an order total of 100 and is free above 100, but the
implementation incorrectly charges 10 at exactly 100.

**When**
the user asks to correct the boundary while preserving the surrounding behavior.

**Then**
99.99 still costs 10, 100 costs 0, 100.01 costs 0, project verification passes,
and unrelated user content is unchanged.

### Scenario C — behavior-preserving refactor

**Given**
a discount command has established behavior for regular and member customers.

**When**
the user requests a refactor with no behavior change.

**Then**
the observed outputs for all protected cases remain byte-for-byte equivalent,
project verification passes, at least one repository change is made, and
unrelated user content is unchanged.

## Evaluation boundary

Outcome checks execute the program and the repository's tests after the agent
finishes. They do not inspect private symbols or prescribe implementation.

Trajectory checks are limited to externally meaningful safety properties, such
as not destroying the fixture repository or attempting delivery from a local
development task. 'skill_view' events and loaded skill names are retained only
for diagnosis and comparison.

## Migration rule for existing contracts

Repository checks that parse 'SKILL.md' prose, require a specific owner name, or
assert wording/section structure are legacy checks. They may remain temporarily
while behavior is migrated, but they must not be expanded and they are not the
authority for new development. Remove them only after equivalent observable
behavior is covered by an executable scenario.
