# Compound execution evidence audit

Standalone audit package for the `feature-shout` historical baseline/candidate runs. It contains no harness dependencies and never executes commands from the recorded traces.

## Reproduce

From this directory, using Python 3.11+ and the standard library only:

```sh
python3 reproduce.py
```

This parses the packaged event JSONL, checks event ordering and call/result pairing, verifies published event and score hashes, re-derives the applicable workflow evidence and trajectory reason, and compares the result with each `assessment.json`. It runs only the packaged, deliberately synthetic `counterexample/app.py`—not any recorded trace command—to verify the three individual process outputs/statuses, aggregate chain output, and evaluator's non-attribution. It does not use Hermes, LLMs, network access, repository files outside this directory, or the original temporary fixture paths. `python3 reproduce.py --write` regenerates the assessment JSON files from the included inputs.

## Contents

- `historical-manifest.json`: byte-for-byte manifest from commit `88a701a4ed6b28fff8ebf5bc54258e8895409c9e`.
- `historical-policy.json`: the `feature-shout` trajectory rules derived by the historical `run_eval.py` at that revision, with their source/config hashes.
- `additional-requirement.json`: a separate no-argument check. It is not a historical criterion and does not alter historical scores.
- `batch-identities.json`: expected and executed IDs from both batch manifests, plus original batch-manifest hashes.
- `runs/<run-id>/events.jsonl`: every tool call, parsed and raw argument representation, tool result, and final assistant result in captured order. `index` is zero-based; `call_id` joins each tool result to its invocation.
- `runs/<run-id>/original-score.json`: exact saved score file.
- `runs/<run-id>/metadata.json`: run/batch identity, relevant evaluation metadata, source hashes, published-copy hash, and recorded redactions.
- `runs/<run-id>/assessment.json`: recomputed historical and supplemental findings, application invocations, event references, and separate attribution decisions.

## Provenance and redactions

The six source runs are the three baseline runs in batch `20261003T035457Z` and the three candidate runs in `20261003T063844Z`. Both batch manifests list exactly the three expected/executed `feature-shout` run IDs; each run's `evidence.json` and `metadata.json` were cross-checked for scenario, version, model/provider, mode, prompt hash, and fixture hash.

The historical manifest bytes, original raw-session files, original evidence files, and original score files were SHA-256 hashed. Their hashes are in each run's `metadata.json`; original score bytes are included verbatim. The published event stream has its own SHA-256 because it is a normalized event projection of `raw_session.json`, not a byte copy of that JSON container. Its hash is separately recorded.

Redactions are limited to absolute environment paths: the source home, repository, scratch directory, and per-run fixture roots become `$HOME`, `$REPO`, `$SCRATCH`, and `$FIXTURE`. Relative paths and their relationships remain intact. No tool events, commands, arguments, results, stdout, or stderr were selectively omitted; parsed tool arguments are accompanied by their original JSON-encoded `raw_arguments` when available. The prompt is supplied by the included historical manifest. A secret-pattern scan was run on each original session and on each published event stream; it found zero matches. Patterns include common GitHub/API tokens, bearer credentials, private-key headers, and credential assignments.

## Attribution rule

A captured tool result has one aggregate stdout and exit status. In a multi-command invocation, including a successful `&&` chain, the final status can establish successful execution of the chained parts, but does not provide per-process stdout boundaries. Therefore the audit script records those launches as executed when supported by the chain/status, while leaving each process's output `UNCONFIRMED`. Only an isolated one-command execution with matching inputs, complete stdout, and status can confirm a specific probe. The parser intentionally supports only the harness's small command-list subset; unsupported syntax is reported and blocks an absence claim. It is not a shell interpreter and does not execute any recorded command.

## Limits

The original `evidence.json` and raw session-container bytes are not republished. Their exact source hashes and source-relative paths are retained. Full ordered tool interaction events, original scores, required metadata, the historical manifest, and recalculated audit outputs are included. No credentials or unrelated user files were found or published.
