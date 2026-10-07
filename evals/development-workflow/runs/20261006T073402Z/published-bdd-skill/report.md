# Controlled BDD skill-behavior evaluation — 2026-10-06

## Assessment status

This initial report is superseded by the verified pytest-linked reassessment in [`reassessment-96ee449/report.md`](reassessment-96ee449/report.md). The earlier trajectory scores and r2/r3 process claims must not be used as current results. The new report re-extracts evidence from the immutable raw traces with the corrected evaluator; it does not change or repeat the LLM runs.

The repository branch and run setup described below remain the setup record. For current scores, event references, and offline reproduction, use the reassessment bundle.

## Connection and historical runs

- Requested branch/revision at experiment start: `SDD-skill`, `68a62b3fd5864f9178c3ace44bc61b23fb8cfcaa`; installed Hermes: `0.21.4 (2026.9.21)`, upstream source `d3b25b52ad1318c526bdb259b600eeca3d5f38e6`.
- Current candidate file: `hermes/skills/software-development/behavior-driven-development/SKILL.md`, skill version `1.0.1`, file SHA-256 `7ce03d921f3d673f47605a3913d7005c27037296a0f54b23ec96834de79bdc6c`. The temporary legacy `spec-driven-development` alias is a distinct file, SHA-256 `7d88411e6bafe6bc5c942d267c9149600b772147d308cdbe39e58ecc236e547b`.
- For each launch, the runner built the skills tree under a temporary skill root and linked it as `$HERMES_HOME/skills`. Metadata records the selected BDD source as `working_tree`, resolved commit `68a62b3fd5864f9178c3ace44bc61b23fb8cfcaa`, clean source, and tree content SHA-256 `64432fe89de2213715133e56870576795cd7a1615932b3533c9816f7b4354a55`.
- The exact CLI argv contains `--skills behavior-driven-development`. The installed `hermes chat --help` accepts `--skills`; installed code `hermes_cli/oneshot.py` calls `_build_preloaded_skills_prompt`, which delegates to `build_preloaded_skills_prompt` and passes the rendered skill text as `AIAgent(ephemeral_system_prompt=skills_prompt)`. Before the first model run, a local preflight materialized the same skill in a temporary `HERMES_HOME`, called that installed preload builder, and asserted that the complete repository `SKILL.md` text was present in its returned prompt (8,745 rendered chars). This establishes content resolution and prompt assembly; it is not a capture of provider-wire request bytes. No Hermes core files were changed.
- The expected local `hermes_agent_official_docs_links.md` was not present in the checkout or installed Hermes source at verification time. I therefore checked Hermes' official public docs directly: the CLI guide states that `--skills` preloads named skills into the session prompt before the first turn and applies to single-query mode; the CLI reference documents `-s/--skills` as preloading one or more skills. These confirm the supported contract. The installed `0.21.4` implementation was separately inspected and the local preflight tested this exact version's prompt builder against the materialized BDD text. Public docs: `https://hermes-agent.nousresearch.com/docs/user-guide/cli/` and `https://hermes-agent.nousresearch.com/docs/reference/cli-commands/`.
- The three old runs in `20261003T063844Z` are not evidence for this BDD experiment: their recorded mode is `natural-routing`, `forced_owner_skill` is null, and argv has no `--skills`; their only observed `skill_view` was `ponytail`. That batch's candidate skill source resolved to `709b4f5bbc71f4aa02d5c08eb8102adc8f4d7222`, and its skills tree lacked `behavior-driven-development`. The migration commit `29745b940161be962d0dd52b6fbb3610711c48e5` is dated `2026-10-03T14:39:37+05:00` (09:39:37Z), after those runs began at 06:38Z. The branch history and timestamps therefore explain the mismatch as pre-migration natural-routing evidence, not a demonstrated connection defect.

## Frozen conditions and identity

- Scenario: `feature-shout`; mode: `skill-behavior`; candidate only; original prompt unchanged: “Добавь в этот небольшой Python-проект необязательный режим `--shout`, чтобы `python3 app.py Alice --shout` печатал `HELLO, ALICE!`. Существующее поведение без `--shout` должно сохраниться.”
- Prompt SHA-256: `368ef8b6c84e14164cf4ea25df042371242b8ad57f8f0d0e06b16a7359d5b1c5`.
- Scenario/fixture fingerprint: `908f3a8245ab3943584f34fc8ce41bfe6c1a5d0154ea2c22ea5f018e77c79004`.
- Evaluator/orchestrator revision: `68a62b3fd5864f9178c3ace44bc61b23fb8cfcaa`. SHA-256: `manifest.json` `f3e45ad04f0620fc0743681d217978ab066db59cb49db28a8fefa1899ab0c66c`; `run_eval.py` `a4b15481274b52ace240bec0f563cb7bd99f04c207ff187ce8a8d44ff538953a`; `consumer.py` `63fc54218e2268eb2f3605e542fe6a90a99079ec4ee41dae3015129211f7ddfd`; `evals/harness/skill_source.py` `7b24c907b0a93cf3f28370a2164a12f5eb66df22a6c9d61c0b3243ef8db1ee01`.
- Same for all runs: runtime/model/provider; `terminal,file,skills`; max turns `36`; run budget `240s`; evaluator timeout `300s`; `--yolo`; source `eval`; fixture baseline commit `59f300ee5512b86d9530d197071ae2cf241030c4`; manifest and skill remained unchanged. Candidate source was clean. No diagnostic connection-failure runs occurred.
- Actual launch form: `hermes chat --query-file <run>/prompt.txt --oneshot --quiet --format stream-json --model gpt-6-luna --provider openai-codex --toolsets terminal,file,skills --max-turns 36 --run-budget 240 --skills behavior-driven-development --yolo --source eval`.

## Results

| Run | Started UTC | Duration | Outcome | Trajectory | Provider-reported tokens* |
|---|---|---:|---|---|---:|
| r1 (diagnostic) | 2026-10-06 07:34:02 | 53.504 s | PASS | PASS | 90,902 |
| r2 | 2026-10-06 07:35:41 | 82.527 s | PASS | PASS | 124,127 |
| r3 | 2026-10-06 07:37:05 | 52.487 s | PASS | FAIL | 84,256 |

\* Token data is present in each saved result event (input/output/cache fields); no trustworthy cost amount was present.

### r1

- The compound baseline invocation is not split into per-process stdout. The subsequent pytest run links the exact test source and identifies shout-only RED while regular and default checks are GREEN before production. After the `app.py` change, the test suite passes and both preserved cases have post-change GREEN evidence.
- **Reassessed trajectory: PASS.**

### r2

- Before production change, the trace adds both shout and no-argument tests; pytest reports **`1 failed, 2 passed`**, and identifies shout as the only failing test. The two passing checks cover the existing regular greeting and default-name behavior. The production change follows, then pytest reports `3 passed`.
- **Reassessed trajectory: PASS.** The no-argument test was not added after production; no artificial RED is required for preserved behavior.

### r3

- The pre-change pytest run confirms regular GREEN and shout RED. The default-name test is added after the production change; the earlier default CLI invocation is compound, so its aggregate stdout is not attributed to that process. After the change, pytest reports `3 passed` and final behavior is correct.
- **Reassessed trajectory: FAIL** because pre-change evidence for all required current behavior is incomplete. This is insufficient evidence, not a confirmed ordering violation: the test's later addition alone does not prove the agent violated the preserved-behavior workflow.

The final application outcomes passed in all three runs. The corrected trajectory scores are r1 PASS, r2 PASS, r3 FAIL. r1/r2 have test-linked evidence of both preserved cases before and after implementation. r3 has post-change preservation evidence but lacks attributable pre-change evidence for default behavior; this is an evidence gap, not proof of a process violation. See the reassessment bundle for the extractor, trace references, hashes, and exact reasons.

## Replay evaluation without model calls

From repository root, run the published offline extractor and rescoring script:

```bash
python3 evals/development-workflow/runs/20261006T073402Z/published-bdd-skill/reassessment-96ee449/reassess.py
```

It verifies pinned input checksums, freshly extracts workflow evidence from each raw JSONL trace, and writes separate evidence, score, and raw event-reference files. It performs no Hermes/model/API invocation. The report and individual results are in [`reassessment-96ee449/`](reassessment-96ee449/).

## Publication and sanitization

The bundle contains the exact scenario manifest and BDD/alias source copies, exact prompt, metadata, evidence, saved scores/reasons, final diffs, stderr and complete ordered JSONL event streams for all three runs: [r1](runs/r1/raw_stream.jsonl), [r2](runs/r2/raw_stream.jsonl), [r3](runs/r3/raw_stream.jsonl). Originals remain unchanged in their run directories. Publication copies replace the user home/repository/temporary fixture/Hermes executable paths with `$HOME`, `$REPO`, `$FIXTURE`, `$HERMES_BIN`, and replace session IDs with per-run placeholders; sanitizer substitutions are recorded in `sanitization.json`. A credential-pattern scan of each raw stream found no matches. Token counts and commands were retained. No independent-evaluation materials remain only local.

## Next justified step

For r3, if stronger classification is needed, capture each preserved CLI invocation and its stdout in separate tool events or add a pre-change default-name test in a future run. The current historical record is immutable; do not change its prompt or infer outcomes from bundled output. No additional LLM runs are part of this reassessment.
