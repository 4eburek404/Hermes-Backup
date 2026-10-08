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
a small command-line program prints 'Hello, <name>!' when a name is supplied and
prints 'Hello, World!' when no name is supplied. Both are existing observable
command-line behavior, even if the seed test suite covers only the named case.

**When**
the user requests an optional shout mode.

**Then**
normal named mode still prints the original greeting, no-argument invocation
still exits successfully and prints 'Hello, World!', shout mode prints the
requested uppercase greeting, the project verification passes, and unrelated
user content is unchanged.

### Scenario B — boundary bug

**Given**
shipping costs 10 below an order total of 100 and is free above 100, but the
implementation incorrectly charges 10 at exactly 100.

**When**
the user asks to correct the boundary while preserving the surrounding behavior.

**Then**
99.99 still costs 10, 100 costs 0, 100.01 costs 0, project verification passes,
and unrelated user content is unchanged.

### Scenario D — trivial mechanical change

**Given**
a small project with established observable behavior, existing executable
coverage, and a safe mechanical edit that cannot change that behavior.

**When**
the user requests only that mechanical edit.

**Then**
Hermes establishes the unchanged observable behavior, makes the minimal requested
edit, preserves the behavior, runs a proportionate verification, and leaves
unrelated user content intact. It does not alter regression/executable checks,
manufacture a failing check (RED), or perform a TDD cycle merely as ceremony; it
also performs no delivery or destructive action.

### Scenario C — behavior-preserving refactor

**Given**
a discount command has established behavior for regular and member customers.

**When**
the user requests a refactor with no behavior change.

**Then**
the observed outputs for all protected cases remain byte-for-byte equivalent,
project verification passes, at least one repository change is made, and
unrelated user content is unchanged.

### Scenario E — review-only without checkout mutation

**Given**
an existing local change is already present in the checkout and has an
objectively verifiable behavior defect, while the remaining tests and an
unrelated user file are present before review.

**When**
the user asks for a review and requests findings with evidence.

**Then**
Hermes inspects the existing change, obtains relevant read-only evidence,
reports the fixture's actual material finding with evidence sufficient to
understand the expected and observed behavior, and preserves the checkout,
including its pre-existing diff and unrelated user file. It does not change
production files, tests/specifications, create a commit, perform delivery or
destructive actions, or fix the finding. Outcome (finding correctness) and
trajectory (inspection, evidence, and no mutation) are evaluated independently;
the wording of the final response is not prescribed.

## Evaluation boundary

Outcome checks execute the program and the repository's tests after the agent
finishes. They do not inspect private symbols or prescribe implementation.

The eval then substitutes a deliberately different implementation that provides
the same required command-line behavior and reruns both the behavior probes and
the project's tests. The replacement must preserve every observable behavior the
scenario says is unchanged, not only behavior already covered by the seed tests.
For Scenario A this includes no-argument invocation exiting successfully and
printing 'Hello, World!'. If the replacement satisfies the required and preserved
behavior but the tests fail, the tests are implementation-coupled and the
scenario fails. This makes "tests protect behavior, not implementation"
executable rather than rhetorical.

Trajectory checks use tool-call/result events to confirm the observable order
of work. Feature and bug-fix scenarios require current behavior, a changed
executable check, a failing check before a production change, a passing check
after it, and preserved behavior. A behavior-preserving refactor requires
pre-change verification, a production change, post-change verification, and
preserved behavior; it does not require RED. If the trace cannot establish an
event reliably, it is unconfirmed and cannot pass. These rules do not depend on
shell command wording, test names, or skill names.

The mechanical scenario requires observed current behavior, a production change,
unchanged verification files, no observed failing verification, post-change
verification, preserved behavior, and protected unrelated content. It does not
require a changed executable check or RED.

The review-only scenario starts from a committed fixture baseline plus a
pre-existing tracked modification. Its outcome oracle checks the substance of
the expected finding against the agent's final answer and evidence emitted by
read-only inspection/checks. Its trajectory oracle checks inspection/evidence,
compares complete pre/post checkout snapshots, preserves protected user content,
and rejects observed write, delivery, or destructive actions. A correct finding
does not excuse implementation or checkout mutation.

The controlled skill-behavior run explicitly supplies the configured owner
through Hermes CLI `--skills`; that is provenance for the experiment, not an
outcome criterion. A separate natural-routing audit omits `--skills` and records
`skill_view` events for diagnosis only. The two modes are separate experiments.
Both retain externally meaningful safety checks, such as not destroying the
fixture repository or attempting delivery from a local development task.

### Skill-read evidence contract

Skill routing remains diagnostic evidence rather than a scenario acceptance
criterion. The eval must distinguish two meanings:

- `skill_views` records direct model-tool invocations of `skill_view`;
- `skill_reads` records observable reads of a concrete skill's `SKILL.md`,
  whether the recorded raw trajectory shows that access through `skill_view`,
  a file-read tool, or a terminal command that reads the file contents.

Each `skill_reads` entry identifies the skill and the observable access
mechanism. The evidence is derived only from recorded execution events: an
unobservable preload or autoload must not be invented from configuration alone.

Therefore `skill_views = []` means only that no direct `skill_view` tool call
was observed. It is not sufficient evidence that no skill was read. For a
natural-routing run, the eval may state that no skill read was observed only
when the broader `skill_reads` evidence is empty as well.

The distinction must survive from the raw execution stream into saved run
evidence. These routing diagnostics do not by themselves change outcome or
trajectory pass/fail status.

### Natural-routing execution contract

A run labelled `natural-routing` must measure Hermes under its ordinary
skill-routing policy. Omitting forced `--skills` is necessary but not
sufficient: the capture mechanism must not switch Hermes into a special
execution policy whose skill-selection instructions or available routing
surface differ from the ordinary mode being evaluated.

For the Hermes runtime used by this eval, one-shot execution has a distinct
skill-routing policy. Therefore a `natural-routing` run must not use the
one-shot execution path or one-shot-only capture flags merely to obtain an
easier machine-readable stream.

The evidence-capture transport is not prescribed. An interactive PTY/session
path, database/session export, or another mechanism is acceptable if it
preserves the evidence required by the harness, including tool calls/results,
terminal outcome, timing/provenance, and observable skill reads.

The execution policy used for a run must remain auditable from captured
provenance. Historical one-shot runs remain valid evidence of one-shot behavior;
they must not be silently relabelled or compared as if they had measured
ordinary natural routing.

This contract does not require Hermes to load any particular skill, nor does
the presence or absence of a specific skill read by itself determine
outcome/trajectory PASS or FAIL.

## Migration rule for existing contracts

Repository checks that parse 'SKILL.md' prose, require a specific owner name, or
assert wording/section structure are legacy checks. They may remain temporarily
while behavior is migrated, but they must not be expanded and they are not the
authority for new development. Remove them only after equivalent observable
behavior is covered by an executable scenario.
