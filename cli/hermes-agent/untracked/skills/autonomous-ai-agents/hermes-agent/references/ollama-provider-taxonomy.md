# Ollama Provider Taxonomy

As of May 2026, Hermes uses three distinct ways to interact with Ollama, often appearing simultaneously in the dashboard.

## 1. ollama-local (deprecated subset)
- **API Mode:** `chat_completions` (OpenAI-compatible)
- **Endpoint:** `http://127.0.0.1:11434/v1`
- **Context:** Historically the easiest way to add local models, but completely redundant if `ollama-native` is present. All models in this provider are a subset of `ollama-native`.

## 2. ollama-native (primary local)
- **API Mode:** `ollama_native_chat`
- **Endpoint:** `http://127.0.0.1:11434`
- **Context:** Uses the raw Ollama `/api/chat` protocol. More stable for streaming, provides better reasoning field handling, and exposes the full local catalog (26+ models in this session).
- **Default Slot:** Should be the preferred local provider.

## 3. ollama-cloud (Ollama.com)
- **API Mode:** `chat_completions`
- **Endpoint:** `https://ollama.com/v1`
- **Requires:** `OLLAMA_API_KEY` in `.env`.
- **Context:** Built-in provider for cloud-hosted open models like `gemini-3-flash-preview` or `glm-5.1`. 
- **Recommendation:** Use as default when local hardware is unavailable or context length > 128k is required (Ollama Cloud offers up to 1M).

## Taxonomy Summary
- **Native Protocol > OpenAI Compatibility** for local Ollama.
- **Cloud > Local** for high-context tasks (Gemini) or when local GPU is busy.
- **Cleanup:** Remove `ollama-local` from `config.yaml` to avoid UI clutter; it brings nothing `ollama-native` doesn't have.
