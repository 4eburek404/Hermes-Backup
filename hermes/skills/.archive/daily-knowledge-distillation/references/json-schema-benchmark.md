# Ollama Cloud JSON Compliance Benchmark (April 2025)

Test: Extract factual claims using 3 response_format modes — `json_schema` (strict), `json_object`, and `none`.

Schema: `{claims: [{fact: str, category: enum[infrastructure,preference,project,tool,general], confidence: enum[high,medium,low]}]}`

Models tested: glm-5.1:cloud, deepseek-v4-pro:cloud, deepseek-v4-flash:cloud, gemma4:31b-cloud, gpt-oss:120b-cloud, gpt-oss:20b-cloud, kimi-k2.6:cloud

## json_schema strict mode — BROKEN for ALL models

Every model ignores enum constraints when `json_schema` strict mode is used through Ollama Cloud:

| Model | Wraps ` ```json ` | Key names match | Category enum | Confidence type | Confidence enum |
|---|---|---|---|---|---|
| **glm-5.1** | ✅ | ✅ | ❌ `"Technology"`, `"Software Configuration"` | float `0.95` | ❌ |
| **deepseek-v4-pro** | ❌ | ✅ | ❌ `"n8n configuration"`, `"authentication preference"` | float `1.0` | ❌ |
| **deepseek-v4-flash** | ❌ | ✅ | ❌ `"configuration"`, `"preference"`, `"action"` | str `"high"` | ✅ (!) |
| **gemma4** | ✅ | ✅ | ❌ `"Infrastructure"`, `"Database"`, `"User Preference"` | float `1.0` | ❌ |
| **gpt-oss:120b** | ❌ | ✅ | ❌ `"configuration"`, `"addition"`, `"preference"` | float `0.99` | ❌ |
| **gpt-oss:20b** | ✅ | ✅ | ❌ `"n8n configuration"`, `"integration addition"` | float `0.95` | ❌ |
| **kimi-k2.6** | ✅ | ⚠️ truncation | ❌ `"deployment"`, `"network"`, `"database"` | float `1.0` | ❌ |

Only deepseek-v4-flash partially complied (string `"high"` for confidence), but still ignored category enums.

## json_object mode + enums in prompt — ALL models comply

With `response_format: {type: "json_object"}` and explicit enum values in the system prompt:

| Model | Keys match | Category enum | Confidence enum | Wraps ` ```json ` | Reasoning tokens |
|---|---|---|---|---|---|
| **glm-5.1** | ✅ | ✅ | ✅ | ✅ | ~2K |
| **deepseek-v4-pro** | ✅ | ✅ | ✅ | ✅ | ~2K |
| **deepseek-v4-flash** | ✅ | ✅ | ✅ | ❌ | ~reasoning |
| **gemma4** | ✅ | ✅ | ✅ | ✅ | minimal |
| **gpt-oss:120b** | ✅ | ✅ | ✅ | ❌ | ~reasoning |
| **gpt-oss:20b** | ✅ | ✅ | ✅ | ✅ | minimal |
| **kimi-k2.6** | ✅ | ✅ | ✅ | ✅ | 3.5-7K ⚠️ |

## Speed benchmarks (distillation-quality prompt, 800 max_tokens)

| Model | json_schema | json_object | none |
|---|---|---|---|
| **glm-5.1** | 27.5s | 36.5s | 30.2s |
| **deepseek-v4-pro** | 8.9s | 19.0s | 20.0s |
| **deepseek-v4-flash** | 20.3s | 19.3s | 9.8s |
| **gemma4** | 5.4s | 9.7s | 4.7s |
| **gpt-oss:120b** | 4.5s | 2.8s | 3.6s |
| **gpt-oss:20b** | 2.2s | 2.1s | 1.6s |
| **kimi-k2.6** | 18.2s | 24.9s | 17.6s |

Note: speeds vary significantly by load. The relative ordering is more reliable than absolute numbers.

## Classification

**Production workers (json_object + prompt enums):** glm-5.1 and gemma4. DeepSeek V4 Pro remains a benchmarked model, but is not in the production pool because earlier “high-quality worker” notes repeatedly caused unwanted reintroduction despite full-prompt timeout/latency concerns.

**Viable but not in pool:** gpt-oss:120b, gpt-oss:20b, deepseek-v4-flash — comply but not selected for pool.

**Not viable:** kimi-k2.6 — excessive reasoning tokens, truncation, inconsistent output.

## Root cause: Why json_schema doesn't work through Ollama Cloud

Ollama implements structured output via **GBNF grammar-based constrained decoding** in the local llama.cpp sampler. This sampler operates token-by-token, filtering which tokens are allowed at each generation step. It only runs for **locally loaded models**.

All `:cloud` models are **remote proxies** — they show 0.0 GB size in `ollama list` because they don't run locally. Requests are forwarded to Ollama's cloud servers. The grammar parameter cannot be enforced remotely because the remote server doesn't apply constrained decoding to its generation pipeline.

**Evidence:**

1. **Codeblock wrapping with json_schema** — if grammar enforcement worked, ` ```json ` wrapping would be impossible (the grammar doesn't allow backtick tokens outside string values). Models glm-5.1, gemma4, gpt-oss:20b, kimi all produce codeblocks under json_schema, proving no grammar enforcement.

2. **Float confidence with json_schema** — models output `0.95`, `1.0` (float) instead of `"high"/"medium"/"low"` (string enum), which would be impossible under enforced enum grammar.

3. **GBNF grammar via native `/api/chat` endpoint** — tested custom GBNF grammar:
   - `glm-5.1:cloud` → **empty output** (grammar breaks remote generation)
   - `deepseek-v4-pro:cloud` → **empty output**
   - `gemma4:31b-cloud` → output but **grammar ignored** (own categories, float confidence)
   - `gpt-oss:20b-cloud` → output but **grammar ignored**

4. **Identical results across all modes** — with the same detailed system prompt, `json_schema`, `json_object`, and `none` produce structurally identical output on all tested models. `response_format` adds zero enforcement value.

5. **Bare prompt + json_object ≠ compliance** — with a minimal prompt (`"Extract facts"`), even `json_object` mode fails to produce correct structure. Compliance comes entirely from prompt-engineered enum specifications, not from any API parameter.

**Implication for local models:** If local models are added to Ollama (non-cloud), GBNF grammar WILL work via `/api/chat`'s `grammar` parameter, providing true constrained decoding. But for all current cloud models, enforcement is prompt-only.

## Key takeaway

`json_schema` strict mode is an illusion through Ollama Cloud. Use `json_object` + explicit enum values in the prompt. The codeblock wrapping difference between models is cosmetic and handled by a 3-level fallback parser (direct parse → strip fences → find `{...}`).

For Ollama Cloud specifically: `response_format` is a prompt-level hint only. Do NOT rely on it for enforcement. All structural and enum compliance must come from explicit instructions in the system/user prompt.