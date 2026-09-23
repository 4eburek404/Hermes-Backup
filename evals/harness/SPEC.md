# General Agent Eval Harness — Behavioral Specification

Status: target contract for the common eval harness.

This document defines observable behavior. It does not prescribe internal module names,
functions, file layout, or a particular test framework.

## 1. Purpose

The harness evaluates Hermes Agent behavior reproducibly across:

- scenario;
- fixture;
- model/provider;
- evaluated skill version;
- repeat.

It must keep three questions separate:

1. **Outcome** — was the requested result correct?
2. **Trajectory** — did the agent reach it through an allowed sequence of actions?
3. **Efficiency** — what factual resources did the run consume?

Privacy/constraint compliance is an independent verdict.

The harness complements production CLI/spec tests. It does not replace them.

## 2. Core invariants

### EH-CORE-01 — Execution and evaluation are separate

Running an agent produces evidence. Evaluation consumes evidence.

A runner must not decide semantic Outcome/Trajectory/Privacy while capturing the run.
An evaluator must not need to execute the agent in order to score already captured evidence.

### EH-CORE-02 — Raw evidence is immutable

Evidence captured from an execution is the source record for that execution and must not be
rewritten by evaluation or re-evaluation.

Derived representations, scores, and reports are replaceable outputs and must remain
distinguishable from raw evidence.

### EH-CORE-03 — One source of facts

A factual run property must have one authoritative source in captured or normalized evidence.
Later layers may reference or aggregate it but must not independently reinterpret the raw trace
using different rules.

### EH-CORE-04 — Deterministic re-evaluation

Given the same raw evidence and the same evaluator/rules version, re-evaluation must produce the
same verdicts and metrics without invoking Hermes, an LLM/provider, production fixture setup, or
live external services.

### EH-CORE-05 — Relay telemetry is optional

ATOF, ATIF, or other external observability streams may be retained for diagnostics, but the
eval harness must not require them for execution, scoring, or re-evaluation. Evidence required
by the evaluator must be captured by the eval run itself.

## 3. Run identity and evaluation matrix

### EH-MATRIX-01 — Run dimensions are explicit

Every expected run is identified by:

- scenario;
- fixture identity/version;
- model;
- provider;
- evaluated skill version/source;
- repeat index.

Changing one dimension must not silently change another.

### EH-MATRIX-02 — Matrix expansion is generic

The harness must support configured sets of scenarios, models/providers, skill versions, and
repeats, and must be able to run the full matrix or an explicit subset without changing common
orchestration logic.

For every batch, expected runs and actually executed runs must be distinguishable.

### EH-MATRIX-03 — Repeats remain observations

Repeated runs are separate observations with separate evidence. One successful repeat must not
be represented as proof of stable behavior.

## 4. Evaluated skill source

### EH-SOURCE-01 — The complete skill is evaluated

An evaluated skill source applies to the whole configured skill directory, including instructions,
scripts, schemas, references, and templates. The harness must not combine parts from different
versions.

### EH-SOURCE-02 — Git sources are exact and non-mutating

A Git source must resolve the requested ref to an exact commit and materialize the complete skill
from that commit without switching, merging, resetting, cleaning, or otherwise mutating the
harness repository checkout.

Evidence must identify the requested ref, resolved commit, configured skill path, and deterministic
content digest.

### EH-SOURCE-03 — Working-tree sources reflect actual content

A working-tree source must evaluate the current configured skill directory, including uncommitted
changes. Evidence must identify repository HEAD, whether the evaluated skill differs from committed
state, configured skill path, and deterministic content digest.

An invalid source, missing ref, unresolved ref, or missing skill path is a setup failure; the agent
must not start with substituted content.

## 5. Fixture and run isolation

### EH-FIXTURE-01 — Starting state is reproducible

A recorded/offline fixture must expose the same configured starting data and external behavior to
comparable runs.

The harness must verify the configured fixture identity/version before agent execution. Drift must
not silently proceed as a comparable run.

### EH-FIXTURE-02 — Runs are isolated

Mutable runtime, workspace, cache, and fixture state from one run must not affect another run.

If a run mutates controlled state and that mutation is relevant evidence, it must be captured before
cleanup.

### EH-FIXTURE-03 — Oracles are private from the agent

Expected answers, evaluator-only rules, and oracle data must not be exposed to the evaluated agent
unless they are explicitly part of the user-visible scenario.

## 6. Execution lifecycle

Execution status is independent from Outcome/Trajectory/Privacy.

### EH-EXEC-01 — Setup failures occur before agent start

Failures preparing the evaluated skill or execution environment are **SETUP_FAILURE**.

Failures establishing or validating the configured fixture are **FIXTURE_FAILURE**.

Neither status may be labelled PASS, and neither counts as an agent execution if Hermes was never
started.

### EH-EXEC-02 — Completed execution

**COMPLETED** means Hermes produced a valid terminal agent result and the runtime process completed
successfully.

A COMPLETED run may still have Outcome FAIL, Trajectory FAIL, or Privacy FAIL.

### EH-EXEC-03 — Agent failure

**AGENT_FAILURE** means Hermes produced a valid terminal agent result, but the agent/tool execution
ended unsuccessfully, for example after an unrecovered tool/CLI failure or a non-zero agent process
exit associated with that completed turn.

AGENT_FAILURE is not the same as an incorrect semantic result. A completed run with a wrong artifact
is still COMPLETED with Outcome FAIL.

### EH-EXEC-04 — Runtime failure

**RUNTIME_FAILURE** means execution terminated without a valid terminal agent result because the
Hermes/runtime process failed or its output could not establish a completed turn.

A non-zero process exit alone is insufficient to classify RUNTIME_FAILURE when a valid terminal
agent result exists.

### EH-EXEC-05 — Timeout

**TIMEOUT** means an eval-owned wall-clock deadline expired before a terminal execution state.

The eval deadline is independent from any agent/model budget. On timeout, available stdout/stderr
and partial runtime evidence must be retained, and the harness must attempt bounded cleanup of the
process tree.

### EH-EXEC-06 — One classification path

Initial evaluation and re-evaluation must derive execution classification from the same behavioral
rules. The same raw evidence must not be AGENT_FAILURE in one path and RUNTIME_FAILURE in another.

### EH-EXEC-07 — Independent runs survive failures

Failure of one run must not erase already captured evidence or cancel independent remaining runs
unless continuing would violate batch validity, such as evaluator preflight failure affecting all
remaining runs.

## 7. Evidence model

The harness has four conceptual layers:

1. **Raw evidence** — captured execution record.
2. **Canonical evidence** — deterministic normalization of raw evidence.
3. **Evaluation result** — verdicts produced from canonical/raw evidence plus evaluator rules.
4. **Report** — presentation and aggregation only.

These are behavioral layers; their physical storage layout is not specified here.

### EH-EVIDENCE-01 — Raw execution record

For every agent run that starts, raw evidence must retain enough information to establish:

- exact prompt presented to the agent;
- raw Hermes runtime event stream;
- stderr/runtime diagnostics;
- process exit status;
- start/end timestamps or equivalent elapsed-time evidence;
- terminal agent result when present;
- relevant produced artifacts and controlled-state observations;
- model/provider and execution parameters;
- evaluated skill identity;
- scenario/fixture identity.

Partial runs must retain the evidence captured before failure or timeout.

### EH-EVIDENCE-02 — Canonical normalization is loss-aware

Normalization must preserve known factual values and explicit absence.

Missing/unknown values must remain null/unknown. They must not be silently converted to zero, empty
text, success, or failure.

If multiple event types contain similarly named fields, normalization must not overwrite one fact
with a later unrelated event.

### EH-EVIDENCE-03 — Terminal result is authoritative

When a valid terminal result event exists, its terminal answer/result fields are the authoritative
source for the final agent answer. Tool results must not replace or shadow the terminal result.

### EH-EVIDENCE-04 — Derived data is reproducible

Canonical evidence must be reproducible from raw evidence by a deterministic normalization contract.
A report must not reparse raw runtime events to invent a second normalization path.

## 8. Evaluation semantics

Each evaluable dimension returns one of:

- **PASS**;
- **FAIL**;
- **UNDEFINED** — required evidence is legitimately unavailable or the dimension does not apply;
- **ERROR** — evaluator logic failed.

UNDEFINED and ERROR must never be presented as PASS.

### EH-EVAL-01 — Outcome

Outcome checks only the scenario's observable result contract, such as:

- required artifact presence/absence;
- semantic artifact content;
- required user-visible delivery protocol;
- other explicit scenario results.

Outcome must not require an implementation detail that production behavior does not promise.

Where multiple outputs are semantically equivalent, the oracle should evaluate semantics rather
than byte identity unless exact bytes are themselves contractual.

### EH-EVAL-02 — Trajectory

Trajectory checks only explicit scenario rules:

- required actions;
- allowed actions;
- forbidden actions;
- permitted fallback conditions;
- stopping conditions.

A correct final artifact does not excuse a forbidden trajectory.

A failed action followed by an allowed correction/retry is not automatically a trajectory failure.
Retry behavior is evaluated only when the scenario contract defines it.

Efficiency observations such as “fewer calls” must not be converted into trajectory quality without
an explicit rule.

### EH-EVAL-03 — Privacy

Privacy checks explicit secret markers against explicitly defined forbidden channels.

The meaning of Privacy PASS must identify its scope. For example, “no configured secret markers in
the final user-visible answer” does not imply that raw evidence or the generated artifact contains
no private fixture values.

Generic filenames or labels are not secrets unless the scenario explicitly declares them so.

### EH-EVAL-04 — Evaluator failure is not agent failure

If evaluator logic crashes or cannot interpret required evidence, the affected dimension is ERROR or
UNDEFINED as appropriate. It must not be converted to agent PASS/FAIL or RUNTIME_FAILURE.

### EH-EVAL-05 — Evaluator provenance is recorded

Every derived evaluation must identify the evaluator/rules used to produce it with sufficient
provenance to distinguish materially different evaluator versions.

For scenario-specific rules/oracles, provenance must include deterministic identifiers/digests of
the effective rules and oracle inputs.

Historical evidence may be re-evaluated under newer rules, but the new result must identify the new
evaluator provenance and must not overwrite or masquerade as the historical verdict.

## 9. Metrics

Metrics are factual observations, not a quality score.

### EH-METRIC-01 — Wall-clock time

Run elapsed time must be retained when measured. Tool-call duration may be retained when emitted by
the runtime.

Whole-run duration must not be labelled model/inference latency.

### EH-METRIC-02 — Token usage

When Hermes terminal usage provides token fields, canonical evidence preserves the factual fields
individually:

- input;
- output;
- total;
- cache-read;
- cache-write.

Unknown fields remain null.

If a derived prompt-token value is reported, it is:

input + cache-read + cache-write

only when all required source fields are known; otherwise it is null.

The harness must not infer provider token usage from text length or reinterpret total beyond the
runtime contract.

### EH-METRIC-03 — Tool usage

The harness may deterministically report:

- total tool calls;
- calls by tool type;
- tool-result errors;
- CLI/tool calls identified by an explicit scenario contract;
- actions after an explicit successful stopping event.

A “retry count” must not be fabricated from repeated tool names when the trace has no reliable retry
semantics.

### EH-METRIC-04 — Missing is not zero

For all efficiency metrics, missing/unsupported data is null/unknown, not zero.

### EH-METRIC-05 — Cost is optional and sourced

Monetary cost may be reported only when its source and status are explicit, such as provider actual
cost or Hermes estimated cost. Estimated cost must not be presented as invoiced cost.

Cost is not required for harness correctness.

## 10. Re-evaluation

### EH-REEVAL-01 — Zero-agent operation

Re-evaluation of saved evidence must not invoke Hermes, a model/provider, live fixture replay, or the
production skill.

### EH-REEVAL-02 — Source evidence remains unchanged

Re-evaluation writes new derived results separately. It must not modify source raw evidence or prior
derived results.

### EH-REEVAL-03 — Same evidence, same rules, same result

Two evaluations with identical source evidence and evaluator provenance must produce the same
execution classification, dimension verdicts, factual metrics, and deterministic diagnostics.

## 11. Reproducibility and comparability

### EH-REPRO-01 — Run provenance

A run must retain enough provenance to identify material conditions, including:

- scenario and exact prompt identity;
- fixture and relevant fixture-resource identities/digests;
- model/provider;
- skill source and exact content identity;
- harness version/commit;
- Hermes/runtime version;
- significant execution parameters;
- repeat;
- execution time.

### EH-REPRO-02 — Evaluation provenance

A score must retain evaluator provenance separately from execution provenance.

This allows old raw evidence to be scored under new rules without pretending that the original
evaluation used those rules.

### EH-COMPARE-01 — Controlled means one intended factor changed

A baseline/candidate comparison may be labelled controlled only when all material conditions other
than the explicitly changed factor are verified equal.

A batch containing only a candidate is not a controlled baseline/candidate comparison.

If material conditions are unknown or multiple factors changed, the report must say so rather than
claim causality.

## 12. Reporting

The report is a compact view of already evaluated data. It is not an evaluator.

### EH-REPORT-01 — Run visibility

Every expected/executed run remains visible. Failures, incomplete runs, UNDEFINED, and ERROR states
must not disappear behind aggregation.

### EH-REPORT-02 — Model summary

For comparable runs, the model summary should show only confirmed fields needed for comparison:

- model/provider;
- PASS count / run count;
- elapsed time;
- prompt, output, and total tokens when known;
- tool calls;
- tool errors.

Unknown metrics are shown as unknown, not zero.

### EH-REPORT-03 — Per-run summary

A compact per-run view must identify:

- scenario;
- model/provider;
- overall run result;
- execution classification;
- elapsed time;
- factual token metrics;
- tool calls/errors.

Outcome, Trajectory, and Privacy remain separately inspectable and must not be collapsed into an
opaque numeric score.

### EH-REPORT-04 — Failure diagnostics

Detailed diagnostics are shown primarily for failed/incomplete/error runs and include:

- execution classification;
- failed/undefined/error dimensions;
- concise deterministic reason;
- relevant failed tool/CLI observation when available;
- reference to retained evidence.

The human report must not dump raw traces or secret fixture values.

### EH-REPORT-05 — Presentation cannot change evaluation

Regenerating a report from an unchanged evaluation result must not change execution classification,
dimension verdicts, or factual metrics.

## 13. Offline and live modes

### EH-MODE-01 — Recorded and live runs are distinct

Recorded/offline evals and live/integration evals must be labelled distinctly and must not be mixed
as equivalent observations.

A recorded eval must not accidentally depend on current live external-service state.

## 14. Required executable specification

This behavioral specification is considered implemented only when executable checks map to the
requirements below.

The checks may use any suitable test framework; names and internal structure are not contractual.

### ES-01 — Terminal result survives tool events

Given a runtime stream containing tool use, tool result, and then a terminal result with final text,
normalization preserves the terminal result text as the final answer.

Covers: EH-EVIDENCE-02, EH-EVIDENCE-03.

### ES-02 — Non-zero exit with terminal result

Given a valid terminal agent result and a non-zero execution exit caused by agent/tool failure,
classification is AGENT_FAILURE, not RUNTIME_FAILURE.

Covers: EH-EXEC-03, EH-EXEC-04, EH-EXEC-06.

### ES-03 — No terminal result

Given runtime termination without a valid terminal agent result, classification is RUNTIME_FAILURE
unless a more specific setup/fixture/timeout state applies.

Covers: EH-EXEC-04.

### ES-04 — Setup and fixture failure cannot pass

Given setup or fixture validation fails before Hermes starts, the run is SETUP_FAILURE or
FIXTURE_FAILURE, agent execution count does not increase, and batch/result labelling cannot report
PASS.

Covers: EH-EXEC-01.

### ES-05 — Token fields are preserved

Given a terminal result containing input/output/total/cache-read/cache-write token fields,
canonical evidence preserves them exactly and derives prompt tokens only under EH-METRIC-02.

Covers: EH-METRIC-02, EH-METRIC-04.

### ES-06 — Null is not zero

Given a supported metric is absent from evidence, normalization/reporting preserves unknown/null and
does not emit a factual zero.

Covers: EH-EVIDENCE-02, EH-METRIC-04.

### ES-07 — Re-evaluation is deterministic and zero-agent

Given saved evidence, two re-evaluations with identical evaluator provenance produce identical
classification, verdicts, metrics, and diagnostics; neither launches Hermes/model execution.

Covers: EH-CORE-04, EH-REEVAL-01, EH-REEVAL-03.

### ES-08 — Re-evaluation does not mutate source

Given a saved batch, re-evaluation leaves source raw evidence byte-identical and writes derived
results separately.

Covers: EH-CORE-02, EH-REEVAL-02.

### ES-09 — Evaluator provenance distinguishes rule changes

Given the same raw evidence scored by materially different rules/oracles, both derived evaluations
identify different evaluator provenance and neither overwrites the other.

Covers: EH-EVAL-05, EH-REPRO-02.

### ES-10 — Outcome and trajectory are independent

Given a correct artifact produced through a forbidden action, Outcome is PASS and Trajectory is FAIL.

Given an incorrect artifact produced through an allowed trajectory, Outcome is FAIL and Trajectory
is evaluated from trajectory rules independently.

Covers: EH-EVAL-01, EH-EVAL-02.

### ES-11 — Allowed correction after failed action

Given a failed tool/CLI action followed by an allowed correction and successful stopping event,
Trajectory does not fail merely because the first action failed.

Covers: EH-EVAL-02.

### ES-12 — Actions after required stop fail trajectory

Given a scenario contract requires stopping after a successful event and the agent performs another
tool action afterward, Trajectory is FAIL.

Covers: EH-EVAL-02, EH-METRIC-03.

### ES-13 — Privacy scope is explicit

Given a configured secret marker appears in a forbidden user-visible channel, Privacy is FAIL.

Given a generic non-secret filename appears there, it does not fail privacy unless explicitly
declared secret.

Covers: EH-EVAL-03.

### ES-14 — Timeout retains partial evidence

Given a controlled subprocess exceeds the eval-owned deadline, status is TIMEOUT, available
stdout/stderr are retained, cleanup is bounded, and the batch can continue with independent runs.

Covers: EH-EXEC-05, EH-EXEC-07.

### ES-15 — Fixture drift blocks comparable execution

Given fixture content differs from the configured identity, the run is not started as a normal
comparable run and is recorded as FIXTURE_FAILURE.

Covers: EH-FIXTURE-01, EH-EXEC-01.

### ES-16 — Run isolation

Given one run mutates controlled state, the next comparable run starts from the configured original
state while the first run's relevant mutation remains in its evidence.

Covers: EH-FIXTURE-02.

### ES-17 — Matrix cardinality

Given 2 scenarios × 2 models × 2 skill versions × 2 repeats, the full matrix contains exactly 16
independently identifiable expected runs.

Covers: EH-MATRIX-01, EH-MATRIX-02, EH-MATRIX-03.

### ES-18 — Skill source is exact and checkout-independent

Given a candidate skill exists on another Git ref, the complete skill is materialized from that ref,
the ref resolves to an exact commit/content digest, and the harness checkout remains unchanged.

Covers: EH-SOURCE-01, EH-SOURCE-02.

### ES-19 — Candidate-only is not a controlled comparison

Given a batch has no baseline version, report/comparison metadata must not label it a controlled
baseline/candidate comparison.

Covers: EH-COMPARE-01.

### ES-20 — Report is presentation only

Given unchanged evaluation results, regenerating the human report does not reparse raw events to
change classification, verdicts, or factual metrics.

Covers: EH-CORE-03, EH-REPORT-05.

## 15. Acceptance gate

The harness is conformant only when:

1. every applicable requirement above has an executable check or an explicitly justified
   non-automated verification;
2. current known defects are represented by failing executable checks before implementation fixes;
3. raw evidence and derived evaluation are separated and re-evaluation is deterministic;
4. initial evaluation and re-evaluation share the same behavioral classification/evaluation rules;
5. failure states cannot be reported as PASS;
6. factual metrics preserve source semantics and unknown values;
7. a report can be regenerated without changing evaluation;
8. existing saved batches remain usable as regression evidence when their raw evidence is sufficient.

Until these gates are green, additional harness features are secondary to correctness.
