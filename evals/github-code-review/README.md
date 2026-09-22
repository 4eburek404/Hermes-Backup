# github-code-review agent-level evaluation

This evaluation is now a consumer of the common harness in `evals/harness/`.

It remains an offline, local-diff behavioral evaluation of `github-code-review`.
The fixture repositories and review tools have no network path; the model provider
call is the only expected network dependency during a real run.

## Layout

- `prompt/` — exact prompts passed to every run.
- `fixtures/` — versioned source snapshots and fixed patches.
- `expected/` — evaluator-side oracle; never copied into the agent fixture/home.
- `manifest.json` — models, skill versions, scenarios, fixture identities and execution settings.
- `consumer.py` — github-code-review-specific fixture/runtime/evidence behavior.
- `run_eval.py` — thin CLI that builds a data-driven case and delegates orchestration to `evals/harness/core.py`.
- `runs/` — immutable run evidence and derived scores.

## Run

```bash
python evals/github-code-review/run_eval.py
```

The default matrix comes from `manifest.json`.

Useful subsets:

```bash
python evals/github-code-review/run_eval.py --version candidate
python evals/github-code-review/run_eval.py --runs 1
python evals/github-code-review/run_eval.py --repeat 3
python evals/github-code-review/run_eval.py --model MODEL --provider PROVIDER
python evals/github-code-review/run_eval.py --prepare-only
```

## Evidence

The migrated consumer preserves the previous raw evidence contract:

- exact prompt copy;
- `raw_stream.jsonl`;
- `raw_stderr.txt`;
- `raw_final_answer.txt`;
- `metadata.json`;
- fixture pre/post/restored snapshots;
- mutation evidence;
- skill/model/provider/runtime identity.

The common harness additionally writes:

- `evidence.json`;
- `score.json`;
- batch expected/executed run identities;
- explicit baseline/candidate comparability data.

Outcome scoring for this review consumer is intentionally still `UNDEFINED`:
the historical review oracle requires semantic judgment and has not been replaced
with a brittle keyword approximation. Trajectory is deterministic for the
currently defined mutation/forbidden-command rules. Flight-calendar evaluation
can use deterministic artifact semantics for Outcome.
