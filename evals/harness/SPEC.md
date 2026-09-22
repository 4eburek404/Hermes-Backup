# General Agent Eval Harness — Behavioral Specification

## 1. Purpose

The eval harness provides reproducible automated evaluation of Hermes Agent behavior when executing skills.

It must support comparison across:

- skill versions;
- models/providers;
- user scenarios;
- repeated runs;
- outcome quality;
- agent trajectory;
- privacy/constraint compliance;
- execution cost and timing.

Outcome and trajectory are independent dimensions. A correct final result does not imply a correct trajectory.

## 2. Scope

The harness evaluates agent behavior in a controlled environment.

It does not replace:

- unit/integration tests of production CLI tools;
- executable specs of production tools;
- live checks of external services;
- provider/API integration tests.

For recorded agent-level evals, the external environment must be reproducible and must not accidentally depend on current live-service state.

## 3. Evaluation dimensions

Each run is defined by at least:

- scenario — the user task and expected behavior;
- fixture — the controlled external-world state;
- model/provider — the model executing the task;
- skill version — the evaluated skill version;
- repeat — the repetition index when checking stability.

Changing one dimension must not silently change the others.

## 4. Evaluation configuration

The harness must accept configurable sets of:

- scenarios;
- fixtures;
- models/providers;
- skill versions;
- repeat count.

Adding a model, scenario, or fixture must not require changing the harness's general orchestration logic.

The harness must be able to run the full configured matrix or an explicitly selected subset.

For every batch it must be possible to determine which runs were expected and which runs actually executed.

## 4.1 Skill version sources

Each evaluated skill version must identify the source of the complete skill content used by the agent.

The common harness must support at least:

- `working_tree` — materialize the configured skill directory from the current repository working tree;
- `git` — materialize the configured skill directory from a supplied Git ref.

The source applies to the whole skill directory, including `SKILL.md`, scripts, references, schemas, templates, and other files under that directory. The harness must not combine `SKILL.md` from one version with supporting files from another version.

For a Git source:

- the requested ref must be resolved to an exact commit;
- the evaluated content must be materialized from that resolved commit;
- the source repository checkout and working-tree state must not be changed by checkout, merge, reset, clean, or equivalent mutation;
- evidence must identify the requested ref, resolved commit, configured skill path, and a deterministic content digest.

For a working-tree source:

- the evaluated content must reflect the current filesystem state of the configured skill directory, including local changes that have not been committed;
- evidence must identify the repository HEAD, whether the skill directory differs from committed state, the configured skill path, and a deterministic content digest.

An invalid source type, missing Git ref, unresolved ref, or missing skill path is a setup failure. The agent must not start with silently substituted skill content.

A candidate stored on another branch or ref must be evaluable while the harness remains on its own branch. No branch merge is required to compare or execute that candidate.

## 5. Run isolation

Every run must be independent.

State from one run must not affect another run.

In particular:

- agent runtime state must be isolated;
- fixture working state must be freshly materialized or reliably restored;
- mutations from one run must not leak into a later run;
- baseline and candidate must not reuse mutable state from each other.

If the agent mutates a fixture, that mutation must be captured as evidence before the environment is restored or destroyed.

## 6. Fixture reproducibility

A fixture represents the controlled external environment for a scenario.

Before execution, the harness must be able to establish that the expected fixture version is being used.

If fixture state differs from the configured version, the run must not silently proceed as a comparable run.

For recorded evals, the same fixture must expose the same starting data and observable external behavior to different models.

Evaluator oracles must not be available to the agent during task execution.

## 7. Batch execution

The harness must execute all runs defined by the requested evaluation matrix.

A failure in one run must not erase already captured results or unjustifiably cancel independent remaining runs.

The following states must be distinguishable for an individual run:

- normal completion;
- agent/runtime failure;
- timeout or exhausted execution budget;
- malformed runtime output;
- fixture/setup failure;
- evaluator failure.

These states must not collapse into only a batch-level "eval failed".

## 8. Evidence captured per run

For every agent run that actually starts, enough evidence must be retained for later independent analysis.

Evidence must make it possible to identify at least:

- scenario;
- fixture;
- evaluated skill version;
- model/provider;
- exact prompt;
- raw runtime trace;
- stderr/runtime diagnostics;
- final agent answer;
- significant created or modified artifacts;
- controlled workspace state before and after execution;
- exit/failure status;
- duration;
- available runtime usage metrics.

Raw evidence must be stored separately from derived evaluation.

Re-evaluating a completed run must not require another LLM call when the required evidence is already available.

## 9. Run identity and comparability

Each run must record enough information to determine whether it is comparable to another run.

At minimum the following must be identifiable:

- evaluated skill version;
- fixture version/identifier;
- scenario;
- prompt;
- model;
- provider;
- Hermes/runtime version;
- repeat;
- significant execution settings.

If a material condition is unknown, the harness must not present the comparison as fully controlled.

## 10. Outcome evaluation

Outcome evaluates the result of the task.

Outcome rules are scenario-specific rather than hard-coded into the general harness.

They may include:

- required artifact exists;
- artifact is absent when creation is forbidden;
- semantic content is correct;
- entity/event count is correct;
- required fields match the oracle;
- result satisfies the scenario contract.

Where multiple representations are semantically equivalent, evaluation should check the semantic contract rather than require byte-for-byte identity without a contract reason.

Primary outcome evaluation should be deterministic where practical.

## 11. Trajectory evaluation

Trajectory is evaluated independently of Outcome.

A scenario may define:

- required actions;
- allowed actions;
- forbidden actions;
- permitted fallbacks;
- preconditions for fallbacks;
- stopping conditions.

The harness must be able to detect a run where the final result is correct but the agent reached it through a forbidden or otherwise invalid trajectory.

Example:

- the agent creates the correct artifact;
- the agent also uses a browser fallback forbidden by the scenario.

Expected evaluation:

- Outcome = PASS
- Trajectory = FAIL

## 12. Privacy and leakage evaluation

A scenario may define values that must not appear in user-visible or otherwise forbidden output channels.

The harness must support deterministic checking for known fixture markers such as:

- PNR;
- surname;
- ticket number;
- private URL;
- credentials;
- private temporary-file contents;
- internal filesystem paths;
- artifact contents when they must not be echoed to the user.

Privacy evaluation is independent of Outcome and Trajectory.

## 13. Efficiency metrics

The harness must collect available factual efficiency metrics, for example:

- tool-call count;
- agent-turn count;
- token usage;
- duration;
- repeated actions.

These are separate metrics.

The harness must not automatically convert them into a subjective overall quality score unless an explicit evaluation contract defines such a rule.

Fewer actions alone do not imply a better run.

## 14. Per-run evaluation result

A run evaluation must distinguish at least:

- Outcome;
- Trajectory;
- Privacy;
- execution/failure status;
- efficiency metrics.

Example:

```text
Outcome: PASS
Trajectory: FAIL
Privacy: PASS
Execution: COMPLETED
Tool calls: 4
Tokens: ...
Duration: ...
```

Independent dimensions must not be collapsed into only one opaque numeric score.

## 15. Batch aggregation

After a batch, the harness must provide:

- each individual run result;
- expected versus actually executed runs;
- aggregation by scenario;
- aggregation by model/provider;
- aggregation by skill version;
- failed/incomplete run information.

Repeats remain separate observations.

Aggregation must not hide an unsuccessful run behind an average.

## 16. Baseline/candidate comparison

When baseline and candidate are compared, material conditions must be controlled or explicitly identified.

For a controlled comparison, the following remain unchanged:

- scenario;
- fixture;
- prompt;
- model/provider;
- evaluator rules;
- significant runtime settings.

The intentionally changed condition must be explicit.

If multiple material factors change together, the result must not be presented as evidence that only one factor caused the observed difference.

Baseline raw evidence must be retained and must not be replaced by candidate evidence.

## 17. Repeated runs

The harness must support multiple independent repeats of the same:

`scenario × fixture × model/provider × skill version`.

Each repeat is a separate run with separate raw evidence.

One successful repeat must not be represented as proof of stable model behavior.

## 18. Evaluator failures

Evaluator failures must be distinguishable from agent failures.

If Outcome, Trajectory, or Privacy cannot be determined because evaluator logic failed or required evidence is missing, the dimension must not automatically become PASS or FAIL.

The evaluation result must expose an explicit undefined/error state.

## 19. Offline and live evaluations

The harness must explicitly distinguish at least:

- reproducible recorded/offline evaluation;
- live/integration evaluation.

Results from these modes must not be mixed as equivalent observations.

If a run depends on a live external service, that dependency must be visible in evidence/metadata.

## 20. Minimum acceptance scenarios for the harness

### H1 — Evaluation matrix

Given:

- 2 scenarios;
- 2 models;
- 2 skill versions;
- 2 repeats.

When the full batch runs.

Then exactly 16 independently identifiable run results are expected.

### H2 — Run isolation

Given the first run mutates a fixture file.

When the next run of the same scenario executes.

Then the second run receives the original fixture state, while the first run's mutation remains only in the first run's evidence.

### H3 — Failed run does not destroy batch

Given one run ends in runtime failure.

When independent runs remain in the matrix.

Then the failure is recorded for that run and the remaining independent runs continue.

### H4 — Fixture drift

Given fixture state differs from the version declared by evaluation configuration.

When that run is prepared.

Then the harness does not mark it as a normal comparable agent run and records a setup/fixture failure.

### H5 — Outcome and trajectory independence

Given the agent produces the correct artifact but performs a forbidden scenario action.

Then:

- Outcome = PASS
- Trajectory = FAIL

### H6 — Incorrect result with valid trajectory

Given the agent follows an allowed trajectory but produces an incorrect artifact.

Then:

- Outcome = FAIL
- Trajectory is evaluated independently against its own rules.

### H7 — Privacy leak

Given a fixture contains a unique secret marker.

When that marker appears in forbidden user-visible output.

Then:

- Privacy = FAIL

independently of Outcome.

### H8 — Repeat independence

Given one scenario/model/version combination is executed three times.

Then there are three distinct run records and three distinct raw-evidence sets.

### H9 — Re-evaluation from saved evidence

Given an agent run has completed and raw evidence is retained.

When only evaluator rules change.

Then the saved run can be evaluated again without invoking the model again.

### H10 — Controlled baseline/candidate comparison

Given baseline and candidate differ only in the evaluated skill version.

When the comparison is executed.

Then evidence is sufficient to verify that other controlled conditions remained unchanged.

### H11 — Evaluator failure

Given evaluator logic cannot parse required evidence.

Then the affected evaluation dimension has an explicit undefined/error state rather than being automatically converted into agent PASS or FAIL.

### H12 — New evaluation consumer

Given the common harness exists.

When a new skill supplies its own scenarios, fixtures, and evaluator rules.

Then adding that skill does not require changing the general orchestration logic used by existing evaluations.

### H13 — Skill source is explicit and checkout-independent

Given:

- the harness repository is checked out on one branch;
- a candidate skill exists on another Git ref;
- the skill contains supporting files in addition to `SKILL.md`.

When the candidate is materialized from that Git ref.

Then:

- the complete skill directory comes from the requested ref;
- the requested ref is resolved to an exact commit and recorded with a content digest;
- the harness repository HEAD, active checkout, and pre-existing working-tree state remain unchanged.

Given a working-tree source with local skill changes.

When that source is materialized.

Then the local skill content is used and its dirty state and content digest are recorded.

## 21. Harness readiness criteria

The common eval harness conforms to this specification when:

1. executable checks cover the required behaviors in this specification;
2. the existing agent eval can be represented through the common mechanism without losing significant evidence;
3. a new skill can use the same mechanism without duplicating common orchestration logic;
4. raw evidence and derived evaluation remain separate;
5. baseline/candidate and multi-model runs are reproducibly comparable;
6. failure of one run does not make the batch opaque;
7. Outcome, Trajectory, and Privacy are evaluated independently.
