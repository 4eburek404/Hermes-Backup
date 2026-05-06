# DeepSeek worker repro — 2026-05-01

## Scope

Daily knowledge distillation worker benchmark for `deepseek-v4-pro:cloud`, using the same shape as the scheduled cron worker.

## Exact repro shape

- Endpoint: Ollama HTTP API `/v1/chat/completions` (`ollama run`/`pull` are forbidden for cloud models).
- Model: `deepseek-v4-pro:cloud`.
- System prompt: `WORKER_SYSTEM_PROMPT` from `scripts/distillation_worker.py`.
- User content: `Session snippets:\n` + ~12k chars from recent daily distillation cron output/session packet.
- `response_format`: `{ "type": "json_object" }`.
- `temperature`: `0.1`.
- `max_tokens`: `3000`.
- Timeout: `200s`.

## Observed result

Successful HTTP transport, failed semantic output:

- elapsed: `92.6–113s` across repro attempts;
- HTTP status: `200` on the successful repro;
- `completion_tokens`: `3000`;
- `message.content`: `127` chars;
- hidden `message.reasoning`: ~`12756` chars;
- content was incomplete JSON, ending mid-string:

```json
{
  "candidates": [
    {
      "claim": "Cron-задача с ID 62e7a25f4e15 выполняет ежедневную дистилляцию знаний по расписанию 0
```

Follow-up retries briefly returned Ollama Cloud `503 Server overloaded` and `500 Internal Server Error`, which are provider availability issues, not the main semantic failure.

## Root cause

DeepSeek V4 Pro spent the completion budget on hidden reasoning and returned only a truncated JSON prefix. The previous worker implementation treated this as `status=ok` with `0 candidates` because HTTP succeeded and parse failure collapsed to an empty candidate list.

Correct classification: `parse_error`, not `ok/0 candidates`.

## Guardrail

`call_worker()` must:

1. read both `message.reasoning_content` and `message.reasoning`;
2. return `parse_error` when `parse_json_response(content)` fails;
3. return `validation_error` when parsed candidates fail enum/field validation;
4. record `finish_reason`, `completion_tokens`, `content_chars`, `reasoning_chars`, and `content_preview` for diagnosis;
5. keep DeepSeek out of the production worker pool unless a fresh task-specific benchmark proves it returns complete parseable JSON under the current cron-shaped constraints.

## User workflow correction captured

When asked to find root cause, do not write philosophical explanations from stale docs. Reproduce the failing production-shaped path first, then patch the guardrail and persist the exact failure mode in the skill/docs/fact store.
