# DeepSeek V4 Pro native Ollama distillation benchmark — 2026-05-07

## Why this exists

The user corrected the framing repeatedly: do **not** treat `deepseek-v4-pro:cloud` as “bad” when a worker benchmark fails. Attribute failures to the exact endpoint, prompt, budget, and output contract. In this session the failure was configuration-shaped, not a model-quality verdict.

## Benchmark class

Daily knowledge-distillation worker JSON extraction:

- payload: production-shaped session packet, 10,151 chars
- schema: `{candidates:[{claim,evidence_type,durability,destination,action,reason}]}`
- validation: installed `knowledge-architecture/scripts/distillation_worker.py` parser and enum validator
- timeout: 200s
- no production pool changes during benchmark

## Untuned results

### Legacy OpenAI-compatible `/v1/chat/completions`

Settings:

```text
model: deepseek-v4-pro:cloud
endpoint: /v1/chat/completions
response_format: {type: json_object}
max_tokens: 3000
```

Observed:

```text
elapsed: 72.1s
completion_tokens: 3000
content_length: 0
message.reasoning length: 14257
finish_reason: length
json_parse_success: false
valid_candidates: 0
```

Cause: hidden reasoning consumed the completion budget before visible JSON. This is endpoint/settings-specific.

### Native `/api/chat`, old verbose worker prompt

Settings:

```text
endpoint: /api/chat
format: json
think: false
num_predict: 3000
```

Observed twice:

```text
elapsed: 56.4s / 66.4s
eval_count: 3000
thinking fields: none
content_length: ~10.6k
done_reason: length
json_parse_success: false
valid_candidates: 0
```

Cause: hidden reasoning was fixed, but the model produced too much visible JSON and got truncated mid-string. This is output-contract/budget-specific.

Diagnostic with `num_predict=6000` and old verbose prompt succeeded once:

```text
elapsed: 77.3s
done_reason: stop
eval_count: 2776
json_parse_success: true
valid_candidates: 20
```

## Tuned prompt contract

The key fix was not only a larger budget; it was constraining output shape:

```text
- Return STRICT JSON only.
- Return at most 10 candidates total.
- Prioritize the 8-10 most durable, high-signal claims.
- Keep each claim concise, ideally under 220 Russian characters.
- Keep each reason concise, ideally under 140 Russian characters.
- Merge duplicate facts; no raw logs, secrets, credential paths, or temporary task progress.
```

Native settings:

```text
endpoint: /api/chat
format: json
think: false
temperature: 0.1
```

## Tuned multi-run result

Five serial DeepSeek runs with tuned prompt and `num_predict=6000`:

```text
HTTP ok: 5/5
JSON parse success: 5/5
valid candidates: 5/5
parse_success_rate: 1.0
valid_success_rate: 1.0
elapsed: 18.4–21.8s, mean 20.5s
valid_candidates: 9–10, mean 9.8
eval_count: 1077–1313
content_length: 3862–4657
finish_reason: stop
thinking/reasoning fields: none
invalid_candidates: 0
```

Budget matrix with tuned prompt:

```text
num_predict=2000: 3/3 parse ok, 9–10 valid candidates, eval_count 1211–1377
num_predict=3000: 3/3 parse ok, 10 valid candidates each, eval_count 1263–1284
num_predict=6000: 3/3 parse ok, 10 valid candidates each, eval_count 1270–1359
```

Conclusion: with the tuned prompt, `num_predict=3000` is sufficient on this payload; `6000` is only a safety margin.

## Baseline context with same tuned prompt

On the same payload and tuned prompt:

```text
glm-5.1:cloud /v1 max_tokens=3000: parse ok, 10 valid, elapsed 14.9s, reasoning length 3167
gemma4:31b-cloud /v1 max_tokens=3000: parse ok, 10 valid, elapsed 21.2s, no reasoning field
```

The tuned prompt improved GLM too; previous GLM failure on the stress payload was also prompt/budget-shaped.

## Operational lesson

Do not say “DeepSeek failed” without naming settings. Correct phrasing:

> The old DeepSeek distillation settings were unsuitable: `/v1` exposed a hidden-reasoning budget trap, and native `/api/chat` with the old verbose prompt could truncate visible JSON. With native `/api/chat`, `think:false`, `format:"json"`, and a capped concise output contract, DeepSeek V4 Pro produced stable valid worker JSON on the production-shaped payload.

Before adding DeepSeek to production `WORKER_MODELS`, run a fresh benchmark under the exact intended worker config and get explicit user approval. A benchmark passing is evidence for settings, not a blanket model ranking.
