# Controlled BDD skill-behavior evaluation — 2026-10-06

## Verdict

Three valid, comparable `skill-behavior` candidate runs completed with `gpt-6-luna` via `openai-codex`. In every run the observable feature outcome passed. The development trajectory score is **FAIL (0/3)**. No setup/preload failure occurred. Do not interpret `skill_reads=[]` as a missing preload: these runs used Hermes' explicit `--skills` startup preload, not a model `skill_view` call.

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
| r1 (diagnostic) | 2026-10-06 07:34:02 | 53.504 s | PASS | FAIL | 90,902 |
| r2 | 2026-10-06 07:35:41 | 82.527 s | PASS | FAIL | 124,127 |
| r3 | 2026-10-06 07:37:05 | 52.487 s | PASS | FAIL | 84,256 |

\* Token data is present in each saved result event (input/output/cache fields); no trustworthy cost amount was present.

### r1

- Observed both named and no-argument greetings before implementation in a compound terminal call. Added the shout check and a default-name preservation check before production code; pytest then reported the expected shout-only RED (`1 failed, 2 passed`). Changed `app.py`; later verification reported `3 passed`, and the final CLI probes plus `notes.txt` preservation passed.
- **Evaluator trajectory FAIL reason:** current behavior and preserved behavior after the source change were `UNCONFIRMED`. The relevant shell invocations combined several commands, so the evaluator intentionally did not assign aggregate stdout to individual probes. This is insufficient attribution, not evidence that the observed greetings were wrong. The required check-change → RED → production-change → GREEN sequence is visible in the raw trace.

### r2

- Observed named/default greetings pre-change in one compound command. Added the shout test and observed expected RED (`1 failed, 1 passed`), changed production code, then added the no-argument preservation test after that source change. The later suite reported `3 passed`; final feature/preservation probes and protected note passed.
- **Evaluator trajectory FAIL reason:** current and post-change preserved observations were unconfirmed because output was bundled. **Concrete sequence gap:** the no-argument preservation test was added after production code and did not have a pre-change RED/GREEN cycle. This is a BDD trajectory omission even though final behavior passed.

### r3

- Observed named/default greetings pre-change in one compound command. Added shout test and observed expected RED (`1 failed, 1 passed`); changed production code; then added the no-argument preservation test after the source change. Final suite reported `3 passed`, all three CLI probes matched, and `git diff --check` passed.
- **Evaluator trajectory FAIL reason:** current and post-change preserved observations unconfirmed due bundled output. **Concrete sequence gap:** as in r2, the default preservation test was introduced only after production change; no pre-change RED was observed for that preserved case. Final behavior is correct; trajectory is not.

All three resulting fixture repositories passed the final observable probes and their tests, including a different behavior-equivalent implementation; protected `notes.txt` remained unchanged. The evaluator's exact saved trajectory reason for all three is `current observable behavior is UNCONFIRMED; required preserved behavior is UNCONFIRMED after production change`. Separate the evaluator's attribution limitation (r1–r3) from the actual test-order gap (r2–r3).

## Replay evaluation without model calls

From repository root, run:

```bash
python3 evals/development-workflow/runs/20261006T073402Z/published-bdd-skill/reproduce_scores.py
```

This reads the published `evidence.json`, `score.json`, and frozen `source/manifest.json`, invokes the deterministic outcome/trajectory evaluator, verifies each recomputed score against the saved score, and makes no Hermes/model/API invocation. Verified locally: r1–r3 each recompute to outcome `PASS`, trajectory `FAIL`, privacy `UNDEFINED` with the saved reason above.

## Publication and sanitization

The bundle contains the exact scenario manifest and BDD/alias source copies, exact prompt, metadata, evidence, saved scores/reasons, final diffs, stderr and complete ordered JSONL event streams for all three runs: [r1](runs/r1/raw_stream.jsonl), [r2](runs/r2/raw_stream.jsonl), [r3](runs/r3/raw_stream.jsonl). Originals remain unchanged in their run directories. Publication copies replace the user home/repository/temporary fixture/Hermes executable paths with `$HOME`, `$REPO`, `$FIXTURE`, `$HERMES_BIN`, and replace session IDs with per-run placeholders; sanitizer substitutions are recorded in `sanitization.json`. A credential-pattern scan of each raw stream found no matches. Token counts and commands were retained. No independent-evaluation materials remain only local.

## Next justified step

Before any new model batch, add/verify a deterministic evaluator contract that can recognize preservation evidence from compound terminal calls without requiring a special command style, while separately marking a preserved-case test first introduced after production as a trajectory failure. Keep the current three-run result unchanged; do not tune prompts or run another candidate series.
