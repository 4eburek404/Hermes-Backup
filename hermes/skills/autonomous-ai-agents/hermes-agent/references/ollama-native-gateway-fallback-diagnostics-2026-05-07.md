# Ollama native gateway fallback diagnostics (2026-05-07)

## Session learning

A Telegram/gateway session was switched from `glm-5.1:cloud` to `deepseek-v4-pro:cloud` via `ollama-native`. User-visible status showed repeated retries and fallback:

```text
⏳ Retrying in 2.4s (attempt 1/3)...
⏳ Retrying in 5.9s (attempt 2/3)...
⚠️ Max retries (3) exhausted — trying fallback...
🔄 Primary model failed — switching to fallback: gpt-5.5 via openai-codex
```

Initial interpretation risk: saying “Ollama native does not work” based only on fallback in the gateway turn. The correct diagnosis requires separating three layers:

1. Native Ollama endpoint (`/api/chat`) availability.
2. Hermes CLI provider path (`hermes chat --provider ollama-native ...`).
3. Gateway/Telegram cached session path, including model/provider resolver, tool schemas, context size, fallback and stale `AIAgent` state.

## Evidence from the session

`~/.hermes/logs/agent.log` showed the gateway repeatedly detecting the primary as `ollama-native (deepseek-v4-pro:cloud)` and then activating fallback:

```text
2026-05-07 12:58:30 ... Auxiliary auto-detect: using main provider ollama-native (deepseek-v4-pro:cloud)
2026-05-07 12:58:38 ... Fallback activated: deepseek-v4-pro:cloud → gpt-5.5 (openai-codex)
2026-05-07 12:59:04 ... Auxiliary auto-detect: using main provider ollama-native (deepseek-v4-pro:cloud)
2026-05-07 12:59:12 ... Fallback activated: deepseek-v4-pro:cloud → gpt-5.5 (openai-codex)
2026-05-07 13:00:18 ... Auxiliary auto-detect: using main provider ollama-native (deepseek-v4-pro:cloud)
2026-05-07 13:00:25 ... Fallback activated: deepseek-v4-pro:cloud → gpt-5.5 (openai-codex)
2026-05-07 13:14:38 ... Auxiliary auto-detect: using main provider ollama-native (deepseek-v4-pro:cloud)
2026-05-07 13:14:45 ... Fallback activated: deepseek-v4-pro:cloud → gpt-5.5 (openai-codex)
```

But direct smoke tests proved native endpoint and CLI route were alive:

```bash
python3 - <<'PY'
import json, time, urllib.request
url='http://127.0.0.1:11434/api/chat'
payload={
  'model':'deepseek-v4-pro:cloud',
  'messages':[{'role':'user','content':'Reply exactly: OK'}],
  'stream':False,
  'think':False,
  'options':{'temperature':0,'num_predict':16},
}
req=urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
t0=time.time()
with urllib.request.urlopen(req, timeout=45) as r:
    data=json.loads(r.read().decode())
print(round(time.time()-t0, 2), data.get('message', {}).get('content'))
PY
```

Observed result:

```text
31.29 OK
```

Hermes CLI smoke:

```bash
hermes chat -q 'Reply exactly: OK' --provider ollama-native --model deepseek-v4-pro:cloud -t '' -Q
hermes chat -q 'Reply exactly: OK' --provider ollama-native --model deepseek-v4-pro:cloud -Q
```

Both returned `OK`.

## Diagnostic rule

Do not conclude “Ollama native is broken” from a gateway fallback banner alone. Say precisely:

> The native endpoint and CLI route may be alive, while the gateway/Telegram path is failing or stale. Diagnose endpoint, CLI provider, and gateway cached session separately.

## Recommended sequence

1. Read gateway/agent logs around the user-visible fallback time:

```bash
grep -E 'ollama-native|deepseek-v4-pro|Fallback activated|Retrying API call|Max retries' ~/.hermes/logs/agent.log ~/.hermes/logs/errors.log | tail -80
```

2. Smoke-test native Ollama `/api/chat` directly with a tiny prompt, `stream:false`, `think:false`, and small `num_predict`.
3. Smoke-test Hermes CLI provider path with tools disabled first:

```bash
hermes chat -q 'Reply exactly: OK' --provider ollama-native --model deepseek-v4-pro:cloud -t '' -Q
```

4. Smoke-test Hermes CLI with normal/default tool context:

```bash
hermes chat -q 'Reply exactly: OK' --provider ollama-native --model deepseek-v4-pro:cloud -Q
```

5. If direct endpoint and CLI pass but Telegram keeps falling back, suspect gateway-specific state:
   - stale cached `AIAgent` after model switch or session reset;
   - gateway provider resolver split-brain (`ollama-native` displaying as `custom` in some logs);
   - Telegram toolset/system prompt payload larger than CLI smoke;
   - fallback logging not surfacing the primary exception clearly.

6. Before changing config or restarting gateway, report exact expected vs actual and preserve current model/provider config. Restart only with explicit approval when writes/long-running work are safe.

## Pitfalls

- `Fallback activated` proves the gateway turn switched models; it does not prove the configured primary endpoint is down.
- `Auxiliary auto-detect: using main provider ...` is not itself the main LLM call outcome; it is useful routing evidence, not final proof.
- A tiny CLI `OK` smoke proves availability only; it does not prove full production-shaped Telegram/tool-calling payloads will work.
- If logs do not include the primary exception near fallback, inspect `run_agent.py` fallback/retry paths or request dumps. Improve logging before making confident root-cause claims.
