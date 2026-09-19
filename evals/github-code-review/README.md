# github-code-review agent-level evaluation

This is an offline, local-diff behavioral evaluation of `github-code-review`.
It compares the historical skill at `0239f4d` with the candidate at `98c4db2`
without checking out the repository or changing Hermes core.

## Layout

- `prompt/` — exact prompts passed to every run.
- `fixtures/` — versioned source snapshots and fixed patches for three local git repositories.
- `expected/` — evaluator-side oracle; never copied into a run repository.
- `runs/` — immutable per-run prompt, metadata, snapshots, raw stream-json trace, stderr, final answer, and derived analysis.
- `run_eval.py` — deterministic materialization, execution, evidence capture, and baseline/candidate orchestration.
- `manifest.json` — scenario, fixture, version, and controlled-comparison metadata.

## Run

From this repository worktree:

```bash
python evals/github-code-review/run_eval.py --runs 3
```

The runner uses the installed Hermes executable (`hermes --version`), the same
model/provider for all runs, an isolated `HERMES_HOME`, a copied skill tree with
only `github-code-review` replaced, and a fresh local fixture repository for
each run. It enables only `terminal,file,skills` toolsets. The model provider
call is the only expected network dependency; fixtures and review tools have no
network path.

`--runs 3` means candidate plus controlled baseline for each scenario. Use
`--version candidate` or `--version baseline` for a single side when needed.

The raw stdout is Hermes `--format stream-json` output: init, text, tool-use,
tool-result, and terminal result records. Stderr, exact command, runtime
settings, skill hashes, prompt, pre/post git snapshots, and any mutation diff
are saved alongside it. If ATIF/ATOF exporters are not available in the runtime,
`metadata.json` records that fact rather than synthesizing a trace.

The oracle is never placed under the fixture repository or the isolated Hermes
home. Derived classification belongs in `analysis.json`/`report.md`, separate
from raw execution evidence.
