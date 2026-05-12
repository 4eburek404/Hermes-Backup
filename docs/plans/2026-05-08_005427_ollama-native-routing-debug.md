# Ollama native routing debug / fix

## Goal
Confirm whether `deepseek-v4-pro:cloud` after `/model` switch uses the native Ollama route (`/api/chat`) through `ollama-native`, isolate any fallback/timeout issue, add a regression test, apply a minimal fix, and verify with targeted tests plus runtime smoke.

## Evidence to keep grounded
- Runtime provider resolver output for `ollama-native` vs `ollama-local`.
- Gateway/agent/errors logs around 2026-05-08 00:34–00:40.
- Session files containing the model-switch note and following user prompts.
- Smoke against Ollama local endpoint without exposing credentials.

## Steps
1. Re-run focused evidence commands with redaction where logs/config can contain secrets.
2. Trace gateway `/model` override → AIAgent runtime config → native transport dispatch → fallback/timeout paths.
3. Reproduce the suspect path with a minimal smoke/test harness.
4. Write a failing regression test first.
5. Implement the smallest source change that makes the regression pass.
6. Run targeted tests and runtime smoke.
7. Report touched files, cause, verification, caveats.
