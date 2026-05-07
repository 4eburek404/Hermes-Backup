# Model Benchmark for Knowledge Distillation Plan

**Goal:** Compare `glm-5.1:cloud`, `gpt-5.5` via OpenAI Codex, `gemma4:31b-cloud`, and `gpt-oss:120b-cloud` on the exact task of proposing curated knowledge-base changes without editing files.

**Context:** Konstantin challenged the earlier model recommendation as partly speculative. The test must separate checked results from hypotheses and use the same source material and scoring rubric for all models.

**Non-goals:**
- Do not change `/home/konstantin/docs/` content based on model outputs during the benchmark.
- Do not update cron model pinning during this benchmark.
- Do not store raw model outputs in long-term docs.

**Steps:**
1. Read current docs and the `daily-knowledge-distillation` skill.
2. Prepare one fixed benchmark packet: docs excerpts + mixed source facts containing duplicates, durable facts, low-durability items, and unsafe/irrelevant items.
3. Ask every candidate model to return only a proposed change plan: `add/update/remove/skip`, destination, rationale, and confidence.
4. Capture raw outputs, latency, output size, and failure modes.
5. Score outputs manually against the same rubric: curation quality, duplicate detection, routing, caution, instruction following, concision, and practical usefulness.
6. Report raw outputs plus analysis to Konstantin.

**Verification:**
- Same prompt and source packet used for all models.
- No candidate model edits files.
- Report distinguishes measured facts from interpretation.

**Risks / pitfalls:**
- `session_search` may not contain the current Telegram session yet; use an explicit source packet instead of pretending current history is indexed.
- Codex provider may behave differently from raw Ollama endpoint because it is accessed through Hermes CLI.
- One benchmark packet is indicative, not statistically conclusive.

**Status:** superseded. The benchmark was not completed as designed (see archived plan `../done/2026-04-28-real-knowledge-distillation-gpt55.md` for the actual distillation run by gpt-5.5, which is `done`). The model comparison portion remains incomplete; no final comparative benchmark of all four candidates on the same packet was produced.
