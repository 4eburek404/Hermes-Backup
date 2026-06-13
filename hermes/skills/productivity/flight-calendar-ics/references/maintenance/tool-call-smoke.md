# Native tool-call smoke tests for model evals

Use this when evaluating small/new models on `flight-calendar-ics` through Hermes. The goal is to separate **calendar-skill/runtime quality** from **model-as-agent native tool-call ability**.

## Trigger

Run this before spending repeated calendar eval runs when a model is small, newly added, routed through an OpenAI-compatible proxy, or has any prior sign of printing tool calls as text.

## Failure shape observed

On 2026-06-12, `ollama-cloud` `gemma3:12b` matched the requested provider/model and answered the eval prompt, but the session had:

- `message_count=2`
- `tool_call_count=0`
- `api_call_count=1`
- no `result.json`, no generated `.ics`
- assistant content was a fenced `python` block containing a pseudo `terminal` call

This is a provider/model native tool-call incompatibility: the model returned `message.content` instead of provider-native `message.tool_calls[]`.

## Smoke-test contract

Before full eval, send a harmless one-step task with the same Hermes tool schema surface that the eval requires. Accept only evidence of a real structured tool call:

- session provenance/footer reports `tool_call_count >= 1`;
- stdout/log contains a real Hermes tool execution line, not just a printed snippet;
- if available from provider response: `finish_reason=tool_calls` and non-empty `message.tool_calls[]`.

Reject/skip full prompt-only eval when the model returns only:

- fenced `python`, JSON, or `tool_code` blocks;
- `<tool_call>` / `<function name="...">` XML text;
- prose that describes the command but no structured tool call;
- footer/provenance `0 tool calls`.

## Classification

- If the smoke test fails and the task is model-as-agent evaluation: mark `tool_call_unsupported` / `native_tool_call_failure`.
- If the task is skill/runtime regression: do not ask the model to run tools. Use a deterministic harness: run `flight_calendar_ics.py`, parse the compact JSON envelope, write `result.json`, then optionally ask the model only for a final one-line handoff.

## Do not over-fix with prompts

Prompt wording or `tool_choice` is not a reliable fix when the provider response lacks `message.tool_calls`. Do not count printed tool-shaped text as execution.

A text-to-tool bridge in Hermes core would need to be opt-in and conservative: pure standalone block only, known tool allowlist, valid JSON parameters, no mixed prose, no execution of examples from tool output, and preferably retry/nudge before direct execution.
