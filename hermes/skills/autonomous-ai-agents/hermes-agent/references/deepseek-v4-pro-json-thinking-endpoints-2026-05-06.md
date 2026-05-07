# DeepSeek V4 Pro JSON + thinking endpoint behavior (2026-05-06)

## Why this exists

Konstantin corrected the framing around `deepseek-v4-pro:cloud`: long reasoning is not a quality defect. It is a task-fit trade-off. The previous daily-distillation failure was real, but it was evidence about one endpoint/contract/token budget, not a general verdict that DeepSeek V4 Pro is bad or cannot do JSON.

## Official docs checked

Sources checked live on 2026-05-06:

- `https://api-docs.deepseek.com/api/create-chat-completion`
- `https://api-docs.deepseek.com/guides/json_mode`
- `https://api-docs.deepseek.com/guides/thinking_mode`
- `https://api-docs.deepseek.com/quick_start/pricing`
- `https://ollama.com/library/deepseek-v4-pro`
- `https://raw.githubusercontent.com/ollama/ollama/main/docs/api.md`
- DeepSeek V4 technical report linked from Ollama/HuggingFace: `DeepSeek_V4.pdf`

## Official facts

DeepSeek API docs:

- Model IDs include `deepseek-v4-flash` and `deepseek-v4-pro`.
- `thinking` controls enabled/disabled and defaults to enabled.
- `reasoning_effort` supports `high` and `max`; default for regular requests is `high`.
- In thinking mode, reasoning is returned as `reasoning_content`, separate from visible `content`.
- Usage includes `completion_tokens_details.reasoning_tokens`.
- JSON Output uses `response_format: {"type":"json_object"}`.
- JSON Output requires the prompt itself to ask for JSON and preferably include an example.
- Docs warn to set `max_tokens` reasonably to avoid truncating the JSON midway.
- Docs warn JSON Output may occasionally return empty content.
- If `finish_reason="length"`, content may be cut off.

Pricing/features page nuance:

- JSON Output is listed as supported for `deepseek-v4-pro`.
- The “Non-thinking mode only” note in the pricing/features table applies to FIM Completion Beta, not JSON Output. Do not say JSON Output is non-thinking-only based on that table.

Ollama facts:

- `ollama show deepseek-v4-pro:cloud` reported architecture `deepseek4`, parameters `1600000000000`, context length `1048576`, capabilities `completion`, `tools`, `thinking`.
- Ollama model page lists `deepseek-v4-pro:cloud` as tools + thinking + cloud, 1M context, 1.6T total parameters / 49B activated, with three thinking modes.
- Ollama native API supports `think` for thinking models and `format: "json"` or JSON schema.

DeepSeek V4 technical report:

- `DeepSeek-V4-Pro` is 1.6T total / 49B activated, 1M context.
- Reasoning modes are Non-think, Think High, Think Max.
- Think High: conscious logical analysis, slower but more accurate.
- Think Max: slow but powerful, pushes reasoning to the fullest extent.

## Live smoke tests on Konstantin's environment

### Native Ollama `/api/chat`

Request shape:

```json
{
  "model": "deepseek-v4-pro:cloud",
  "messages": [
    {"role": "system", "content": "Return ONLY a valid JSON object. No markdown. Example: {\"status\":\"ok\",\"n\":1}"},
    {"role": "user", "content": "Return JSON with fields status=\"ok\" and n=1."}
  ],
  "format": "json",
  "stream": false,
  "options": {"num_predict": 256},
  "think": false
}
```

Result:

- HTTP 200
- latency: 9.62s
- `content`: `{"status":"ok","n":1}`
- parse OK
- `thinking_len`: 0

With `think: true` on the same tiny prompt:

- HTTP 200
- latency: 17.3s
- `content`: `{"status":"ok","n":1}`
- parse OK
- `thinking_len`: 341

Conclusion: native Ollama `/api/chat` can produce parseable JSON for DeepSeek V4 Pro on a tiny task, including with thinking enabled if token budget is enough. Use this endpoint as a candidate for structured extraction benchmarks.

### Ollama OpenAI-compatible `/v1/chat/completions`

Request shape used for tiny prompt:

```json
{
  "model": "deepseek-v4-pro:cloud",
  "messages": [...],
  "response_format": {"type": "json_object"},
  "max_tokens": 256,
  "stream": false
}
```

Results with `max_tokens=256`:

- Default: `content=""`, `reasoning_len≈1079`, `finish_reason="length"`, parse error.
- Adding `thinking: {"type":"disabled"}` still returned reasoning and empty content.
- Adding `think:false` still returned reasoning and empty content.
- Explicit thinking enabled returned incomplete visible content and parse error.

With `max_tokens=1024` on the same tiny prompt:

- HTTP 200
- `finish_reason="stop"`
- `content`: `{"status":"ok","n":1}`
- `reasoning_len`: 295
- parse OK

Conclusion: the OpenAI-compatible Ollama endpoint can let reasoning consume small `max_tokens` budgets before visible JSON. Thinking-disable parameters may not map the way DeepSeek official API documents describe. Do not assume native `/api/chat` and `/v1/chat/completions` behave the same.

## Revised interpretation of the old distillation failure

Old repro remains real:

- Endpoint/path: Ollama OpenAI-compatible `/v1/chat/completions` / Hermes provider path.
- Contract: `response_format/json_object`, large 12k snippet packet, strict parseable worker JSON.
- Limits: `max_tokens=3000`, timeout around 200s.
- Observed: 92.6–113s, hidden `message.reasoning`, only 127 chars incomplete visible JSON.
- Operational result: parse_error for that worker contract.

Correct interpretation:

- This is not proof DeepSeek V4 Pro is a bad model.
- This is not proof DeepSeek V4 Pro cannot output JSON.
- It is evidence that this endpoint + thinking behavior + token/timeout budget is unsafe for that production worker contract.

## Workflow for future agents

When evaluating DeepSeek V4 Pro for structured output:

1. State the endpoint explicitly: DeepSeek official API, Ollama native `/api/chat`, Ollama OpenAI-compatible `/v1/chat/completions`, or Hermes provider path.
2. State thinking controls explicitly: `thinking.enabled/disabled`, `reasoning_effort`, Ollama `think`, and whether they actually affected output.
3. Capture both visible `content` and reasoning fields (`reasoning`, `reasoning_content`, `message.thinking`) plus usage (`reasoning_tokens` if available).
4. Treat `finish_reason="length"` as a hard failure for strict JSON even if partial content looks plausible.
5. Benchmark on production-shaped payloads before changing cron worker pools. Tiny prompt success only proves endpoint availability and basic JSON ability.
6. Prefer native Ollama `/api/chat` with `format:"json"` + `think:false` as a candidate path for extraction tasks, but validate on the full worker payload.
7. For deep analysis, long reasoning can be desirable; judge by coverage, accuracy, and usefulness, not by latency alone.
8. If the follow-up question is architectural (“why not make Ollama native?”), use `references/ollama-native-provider-split-2026-05-07.md`: add a separate native `ollama-native` / `ollama_native_chat` path rather than silently repointing existing `/v1` `ollama-local` semantics.

## Reporting rule

Use this wording pattern:

> DeepSeek V4 Pro is a thinking-capable model. Long reasoning is a task-fit trade-off. In our previous distillation worker, the OpenAI-compatible Ollama path and token budget caused reasoning to consume the budget before full JSON content, so it failed that contract. Official docs and native Ollama smoke tests show JSON can work under the right endpoint and budget; production use still requires task-shaped benchmarking.
