# Auxiliary title generation warning audit pattern

Use this reference when a user reports a post-response warning like:

```text
⚠ Auxiliary title generation failed: Connection error.
```

This is a read-only diagnostic pattern for identifying the auxiliary title-generation path, provider/model/base URL, and likely failure layer without changing config or making LLM calls.

## Key code path

- User-facing warning is emitted by `run_agent.py` → `AIAgent._emit_auxiliary_failure(task, exc)` via `_emit_warning()`.
- Title generation is implemented in `agent/title_generator.py`:
  - `maybe_auto_title()` starts a daemon background thread after the first exchange.
  - `auto_title_session()` calls `generate_title()`.
  - `generate_title()` calls `agent.auxiliary_client.call_llm(task="title_generation", ...)`.
  - On exception, it logs `Title generation failed: ...` and calls `failure_callback("title generation", exc)`.
- Gateway path: `gateway/run.py` calls `maybe_auto_title(..., failure_callback=agent._emit_auxiliary_failure, main_runtime={...})` after the main response is ready/sent.
- CLI path: `cli.py` wires the same callback after local CLI response completion.

## Provider/model/base URL resolution

For `auxiliary.title_generation.provider: auto`:

1. `agent/auxiliary_client.py` reads `auxiliary.title_generation` from config.
2. If provider is `auto`, `_resolve_auto(main_runtime=...)` tries the live main runtime provider/model first, then fallback auxiliary providers.
3. If live main runtime is `openai-codex`, auxiliary title generation uses `CodexAuxiliaryClient` against the Codex backend base URL constant:

```text
https://chatgpt.com/backend-api/codex
```

Recent diagnostic case: config showed `model.provider=ollama-cloud` and `auxiliary.title_generation.provider=auto`, but logs showed live title generation resolving to `openai-codex` / `gpt-5.5` at `https://chatgpt.com/backend-api/codex/`. Treat logs/live runtime as authoritative over static config when they differ.

## Read-only command recipe

Run from the target Hermes checkout. If the user pins a repo path, verify `pwd` first and stop if it differs.

```bash
pwd
git status --short --branch --untracked-files=all
git log -5 --oneline

rg -n "Auxiliary title generation failed|title generation|generate.*title|session.*title|display_name|auxiliary" .
rg -n "title|display_name|session_name|conversation title|auxiliary" run_agent.py agent gateway hermes_cli tools tests
rg -n "auxiliary|title_model|summary_model|model.*title|base_url|provider|client" run_agent.py agent gateway hermes_cli tools

ls -lt ~/.hermes/logs 2>/dev/null | head -20
grep -R "Auxiliary title generation failed\|title generation\|Connection error" ~/.hermes/logs 2>/dev/null | tail -50 || true

grep -R "auxiliary\|title\|model\|base_url\|provider" ~/.hermes/config.yaml ~/.hermes/*.yaml ~/.hermes/*.json 2>/dev/null || true
```

If logs/config may include credentials, prefer a small Python sanitizer over raw `grep` in the final report. Do not print tokens, authorization headers, passwords, or bearer strings. If a secret-scan grep is requested as safety, understand that it can echo matching lines; sanitize or report matches without values when possible.

## Interpretation checklist

- If the warning appears after `response ready` / gateway send, it is auxiliary title generation, not main response failure.
- If logs say `Auxiliary title_generation: using auto (<model>) at <url>`, that is the actual provider endpoint for the failing title call.
- `Connection error on auto ... trying fallback` means the first selected auxiliary route failed at transport/client level.
- `no fallback available` means configured or credentialed fallback auxiliary providers were unavailable.
- With `openai-codex`, likely manual checks are network/DNS/TLS/Cloudflare reachability to `chatgpt.com/backend-api/codex`, OAuth credential freshness, model allow-list drift, or lack of non-Codex auxiliary fallback.

## Safe next steps

Do not patch code or config during a read-only audit. Recommend one of these with explicit approval:

- verify Codex reachability/OAuth freshness without sending prompts;
- set a dedicated `auxiliary.title_generation` provider/model to a stable low-latency backend;
- enable focused DEBUG logs for `agent.auxiliary_client` and reproduce once;
- accept that auto titles may remain unset if main responses are healthy and warning noise is tolerable.

## Report shape

Keep the final report compact:

- source file/function;
- suspected or verified provider/model/base URL;
- log evidence;
- why auxiliary, not main response;
- severity;
- recommended fix or manual check;
- whether any document/code was changed and whether checkpoint commit is appropriate.
