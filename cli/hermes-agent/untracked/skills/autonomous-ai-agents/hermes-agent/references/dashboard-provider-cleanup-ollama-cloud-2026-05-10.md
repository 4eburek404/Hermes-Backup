# Dashboard Provider Cleanup & Ollama Cloud Case (2026-05-10)

Practical notes from the migration to `ollama-cloud` and provider list cleanup.

## Secret Safety Guardrail
**[CRITICAL]** Never delete, comment out, or remove tokens (like `GITHUB_TOKEN`, `OLLAMA_API_KEY`) from `.env` or `auth.json` to "clean up" the Dashboard UI list. 
- **Consequence:** Destroying secrets leads to user frustration and lost credentials.
- **Correct Action:** Hide providers via non-secret config or code filters. If no such filter exists, leave the provider visible rather than purging the secret.

## Ollama Provider Comparison
When choosing between Ollama routes on this host:

- **ollama-local:** OpenAI compat (`/v1`). Suboptimal for native Ollama models; redundant with native.
- **ollama-native:** Uses `/api/chat`. Best for local models.
- **ollama-cloud:** Built-in provider for `ollama.com`. High reliability, no local server required.

## Smoke Testing Pitfall: Reasoning Tokens
When performing an inference smoke test (e.g., `curl` or `httpx` to `/v1/chat/completions`) on models like `glm-5.1` or `nemotron`:
- **Problem:** If `max_tokens` is low (e.g., 20) and the model starts with internal thinking, `content` will be empty (`""`) and `reasoning` will contain the text.
- **Symptom:** Test looks like it "failed" or returned nothing.
- **Fix:** Set `max_tokens` to ≥128 for smokes or inspect the `message.reasoning` field in the JSON response.

## Recovery Checklist
If a provider disappears from Dashboard:
1. Check `.env` for the relevant token.
2. Check `~/.hermes/auth.json` credential pool.
3. Check `hermes config` for excluded/overridden providers.
