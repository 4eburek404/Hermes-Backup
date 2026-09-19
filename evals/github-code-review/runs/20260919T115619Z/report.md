# github-code-review agent-level evaluation report

## STATUS

The deterministic local-diff evaluation is complete. The canonical batch is:

```text
runs/20260919T115619Z/
```

It contains all six requested runs: three scenarios with the historical
baseline skill and three with the candidate skill. The production
`github-code-review` skill was not edited during the evaluation. The first
push of `98c4db2` was completed before this work.

## EVAL DESIGN

The harness uses three separate local fixture repositories. Each fixture is
built from versioned source files, a fixed base commit, and a fixed review
patch. The checked-out fixture starts at the base SHA with the review change as
an uncommitted working-tree diff, which exercises local-diff review without
using the Hermes-Backup worktree.

The saved prompts have the same structure and only scenario-specific target
behavior/repository context differs. Oracles are in `expected/`, outside both
the fixture repository and the isolated Hermes home. The model never received
oracle files.

The harness copies the repository skill tree into an isolated `HERMES_HOME` and
replaces only `github-code-review/SKILL.md` with either the historical or
candidate version. Runtime, model, provider, toolsets, prompts, and fixture
SHAs are held constant.

## VERSIONS

| Item | Value |
|---|---|
| Hermes | `v0.21.3 (2026.9.14)`, upstream `948e9706` |
| Model | `gpt-5.6-luna` |
| Provider | `openai-codex` |
| Baseline skill | `0239f4d`, SHA-256 `012786e73250043c702144c6d2dcc7a636c86d908c329eb6988f3601fc2536df` |
| Candidate skill | `98c4db2`, SHA-256 `a2521736796960b574aa229d6b97c25eccdfea19099ad26faceb32e4e46ea809` |
| Trace format | Hermes `--format stream-json` JSONL |
| Toolsets | `terminal,file,skills` |

Fixture versions:

| Scenario | Base SHA | Review commit SHA |
|---|---|---|
| A | `504da46badb86b5ef086990b08a3e581feb8b698` | `2093c2ce518c611dd3d3c05a8649b2531ffff27f` |
| B | `459d3911bd84207986c7cb0e1afe9d371b7c26c1` | `f3851db6df6543a46e67c23a6fa0f0da100474cc` |
| C | `359a6fb86e27b35e39fc43f2d654e9cf9e98c70e` | `9bec290c9a91e53c8bda9a608de140e920582510`

## RAW ARTIFACTS

Each canonical run directory contains:

```text
prompt.txt
raw_stream.jsonl
raw_stderr.txt
raw_final_answer.txt
metadata.json
fixture-repo/
```

Canonical run directories:

```text
runs/20260919T115619Z/scenario-a-baseline/
runs/20260919T115619Z/scenario-a-candidate/
runs/20260919T115619Z/scenario-b-baseline/
runs/20260919T115619Z/scenario-b-candidate/
runs/20260919T115619Z/scenario-c-baseline/
runs/20260919T115619Z/scenario-c-candidate/
```

The batch-level files are:

```text
runs/20260919T115619Z/batch_manifest.json
runs/20260919T115619Z/analysis.json
```

`raw_stream.jsonl` is the original Hermes stream, including tool calls,
tool results, text events, and terminal result. No ATIF/ATOF exporter files
were produced by this runtime; `metadata.json` records that as unavailable.
No `post_mutation.diff` was created because no run changed its fixture.
Earlier failed harness smoke runs are retained in `runs/20260919T115120Z/` and
`runs/20260919T115251Z/`; they were not used for the canonical outcome.

## OUTCOME

### Scenario A — real blocking defects

Expected findings:

1. Zero bucket counts changed from `buckets <= 0` to `buckets < 0`, causing
   `ZeroDivisionError` instead of the required `ValueError`.
2. Integer division is repeated for every bucket, losing remainder cents and
   violating the exact-sum contract.

| Run | Findings | Verdict | Evidence |
|---|---|---|---|
| Baseline | Both confirmed findings found; no false positives or misses | Correct blocking / request changes | Failing tests and direct behavior probes |
| Candidate | Both confirmed findings found; no false positives or misses | Correct blocking / changes rejected | Failing tests and direct behavior probes |

### Scenario B — clean change

Expected result: no material findings and no blocking false positive.

| Run | Findings | Verdict | Evidence |
|---|---|---|---|
| Baseline | No material findings | Correct approve | Three tests and manual cases passed |
| Candidate | No material findings | Correct approve | Three tests and manual cases passed |

Neither version promoted a style preference into a defect.

### Scenario C — insufficient evidence

Expected result: do not invent a consumer incompatibility; report incomplete
review because the separately deployed consumer schema/integration evidence is
absent.

| Run | Findings | Verdict | Uncertainty handling |
|---|---|---|---|
| Baseline | No confirmed defect; evidence gap identified | Correct incomplete / do not approve | Correct |
| Candidate | No confirmed defect; evidence gap identified | Correct incomplete / do not approve | Correct |

## TRAJECTORY

All six runs:

- read the local diff and relevant source/tests;
- ran proportionate verification or direct behavioral probes;
- completed with a review result;
- left the fixture state byte-identical according to pre/post relevant-file
  SHA-256 snapshots;
- performed no implementation fix;
- performed no `git checkout`, `git reset`, `git clean`, `git commit`, or
  `git push` over the reviewed fixture;
- did not publish anything to GitHub.

The skill was explicitly preloaded in every command. A `skill_view` event is
visible in the raw trace for scenarios A and C. In scenario B the model did
not issue a separate `skill_view` tool call, but the command used the same
explicit `--skills github-code-review` preload; this is a limitation of using
model trajectory to prove a preloaded skill was reread.

Necessary actions were diff/context reading and verification. Some runs tried
generic test discovery first, which collected zero tests, then corrected the
command with the fixture's import path or direct test module. This was mildly
redundant but did not cause unsafe behavior or a false result. The candidate
never entered an SDD/TDD implementation workflow.

## EFFICIENCY

| Run | Elapsed | Terminal commands | Stream tool events |
|---|---:|---:|---:|
| A baseline | 47.4 s | 4 | 16 |
| A candidate | 47.1 s | 5 | 20 |
| B baseline | 58.3 s | 9 | 28 |
| B candidate | 63.6 s | 7 | 24 |
| C baseline | 54.8 s | 7 | 24 |
| C candidate | 53.9 s | 6 | 26 |

The candidate used fewer terminal commands on B and C and more on A. It was
faster on A and C and slower on B. No efficiency improvement is claimed.

## BASELINE VS CANDIDATE

Both versions produced the same oracle-level result on all three scenarios:

- A: found both blocking defects;
- B: no material findings and no false positives;
- C: incomplete review without inventing a defect.

The differences are report wording, verification path, and action count. This
six-run sample does not demonstrate that the candidate is better or worse than
the baseline.

## EVAL DEFECTS

The harness had several defects during exploratory setup: temporary home
creation used `mkdir` on an already-created `mkdtemp` path; generated
`__pycache__` files could disturb fixture commit hashes; and the terminal
working directory needed explicit `TERMINAL_CWD` isolation. These were fixed
before the canonical batch. The failed exploratory runs remain preserved and
are not mixed into the outcome tables.

The remaining limitation is that explicit skill preload is not always visible
as a `skill_view` tool event. The raw stream still records the exact command and
all agent tool calls, but the runtime does not expose the full assembled system
prompt as a trajectory artifact.

## SKILL DEFECTS

No confirmed candidate skill defect was found in this dataset. Both baseline
and candidate passed the three semantic scenarios. This does not establish
stability beyond the six requested runs.

## FILES CHANGED

Production skill files: none.

Added eval artifacts:

```text
evals/github-code-review/README.md
evals/github-code-review/manifest.json
evals/github-code-review/run_eval.py
evals/github-code-review/prompt/scenario-a.txt
evals/github-code-review/prompt/scenario-b.txt
evals/github-code-review/prompt/scenario-c.txt
evals/github-code-review/expected/scenario-a.json
evals/github-code-review/expected/scenario-b.json
evals/github-code-review/expected/scenario-c.json
evals/github-code-review/fixtures/scenario-a/{README.md,review.patch,src/,tests/}
evals/github-code-review/fixtures/scenario-b/{README.md,review.patch,src/,tests/}
evals/github-code-review/fixtures/scenario-c/{README.md,review.patch,src/,tests/}
evals/github-code-review/runs/20260919T115619Z/...
```

## COMMIT

The eval artifacts are committed separately with message `test(github): add code review agent evaluation`. The existing contract checks were rerun directly and returned `9 passed / 0 failed / 0 deferred`
for `github-code-review` and `36 passed / 0 failed` for
`github-issue-to-pr`.
