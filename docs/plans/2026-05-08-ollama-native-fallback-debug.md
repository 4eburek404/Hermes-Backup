# Ollama native fallback debug plan

> **For Hermes:** use systematic-debugging first; do not patch until root cause is isolated. If code changes are needed, use TDD.

**Goal:** выяснить, почему `deepseek-v4-pro:cloud` через `ollama-native` один раз ответил, а на следующем сообщении сработал fallback, и устранить воспроизводимую причину.

**Architecture:** сохранить явный split: `ollama-native` → native `/api/chat`, `ollama-local` → OpenAI-compatible `/v1/chat/completions`. Диагностировать отдельно: main agent call, auxiliary/title generation call, Ollama server/cloud latency, Hermes retry/fallback thresholds.

**Tech Stack:** Hermes Agent runtime repo `/home/konstantin/.hermes/hermes-agent`, Ollama HTTP API `http://127.0.0.1:11434`, pytest.

---

## Tasks

### Task 1: Evidence snapshot
- Read `~/.hermes/logs/agent.log`, `gateway.log`, `errors.log` around 2026-05-08 00:34–00:41.
- Inspect current `~/.hermes/config.yaml` provider entries.
- Verify runtime resolver output for `ollama-native` and `ollama-local`.

### Task 2: Trace route and timeout/fallback code
- Read `agent/transports/ollama_native.py`, `run_agent.py`, `agent/auxiliary_client.py`, runtime provider resolver, and fallback handling.
- Find exact request timeout used by native transport and whether provider `request_timeout_seconds` is honored.

### Task 3: Reproduce/minimal smoke
- Direct native `/api/chat` smoke with `deepseek-v4-pro:cloud` and small prompt.
- Hermes-level smoke only if safe: one short `hermes chat -q` with `--provider ollama-native -m deepseek-v4-pro:cloud`, timeout bounded.

### Task 4: TDD regression if code/config bug found
- Write/extend a failing pytest covering the root cause.
- Verify RED.
- Implement minimal fix.
- Verify GREEN + targeted suite.

### Task 5: Verification and report
- Run native provider tests and auxiliary routing tests.
- Re-run runtime resolver/smoke.
- Update relevant skill/fact if behavior/procedure changed.
- Report: touched files, root cause, verification, rollback.
