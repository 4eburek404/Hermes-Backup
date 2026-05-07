# Verification Claims — Distinguish implementation, smoke, and production-shaped benchmark

Session lesson from 2026-05-07 DeepSeek/native Ollama distillation work.

## Trigger

User challenged the report: “так ты проверил его или просто сделал?” after the assistant said the Step 1 worker change was verified.

## Durable lesson

For model/provider/worker changes, do not collapse different verification levels into a single word like “checked” or “verified”. Report the highest verification level actually performed and explicitly name what was not tested.

## Verification levels

1. **Implemented only**
   - Code patched.
   - No tests or runtime invocation yet.

2. **Static/unit verified**
   - Syntax/import/unit tests pass.
   - Request mapping and parsing may be tested with mocks.
   - This proves implementation shape, not live provider behavior.

3. **Live smoke verified**
   - Real provider/endpoint called with a small controlled payload.
   - Confirms endpoint, request fields, response shape, and basic parseability.
   - Does not prove production reliability or quality.

4. **Production-shaped benchmark verified**
   - Realistic payload size, timeout, token budget, prompt/contract, and comparison set.
   - Metrics include parse success, candidate quality, latency, truncation/empty content, timeout behavior, and relevant token/thinking counters.
   - This is the threshold for reintroducing a model into a production worker pool.

## DeepSeek/native Ollama example

For `deepseek-v4-pro:cloud` in `distillation_worker.py`:

- Unit/mocked verification confirms it routes to `/api/chat` with `format:"json"`, `think:false`, `stream:false`, `options.num_predict`, and parses `message.content`.
- Live smoke with a tiny payload can confirm native Ollama returns valid worker JSON.
- It still must not be reported as production-ready until it passes a cron-shaped 8k–12k snippet benchmark with the same timeout/token budget and is compared against current production workers.
- A 2026-05-07 production-shaped benchmark showed the important nuance: native `/api/chat` + `think:false` removed hidden reasoning; with the old verbose worker prompt DeepSeek truncated visible JSON at `num_predict=3000`, but a tuned output contract (`max 10 candidates`, concise claim/reason) passed repeated production-shaped runs even at `num_predict=3000`. Verification must therefore report endpoint, thinking control, prompt/output cap, budget, `done_reason`, parse success, and valid candidate count — and must attribute failures to settings unless evidence proves a model capability issue.

## Reporting template

Use this wording pattern:

```text
Done and verified at level: <unit/mocked | live smoke | production-shaped benchmark>.
Verified: <specific evidence, including endpoint/request shape, timeout, token budget, done/finish reason, parse success, valid candidates, and comparison set when relevant>.
Not verified: <specific remaining gaps>.
Production impact: <changed/not changed>.
```

If the model remains excluded from production, say that directly even if smoke tests passed.