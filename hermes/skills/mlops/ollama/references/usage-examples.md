# Ollama usage examples

Executable examples are kept here so `SKILL.md` stays focused on rules, pitfalls, and model-selection guidance.

## Safe cloud model validation

Do **not** use `ollama run <model>:cloud` from Hermes tool calls for smoke tests; in this environment it can pull multi-GB blobs and fill disk. Prefer metadata checks and API calls through the local OpenAI-compatible endpoint.

```bash
# Metadata/availability probe without starting a chat session
ollama show glm-5.1:cloud

# OpenAI-compatible localhost endpoint
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v3.1:671b-cloud","messages":[{"role":"user","content":"Say OK"}],"max_tokens":16}'
```

## Launch integrations

```bash
ollama launch claude-desktop
ollama launch claude --model minimax-m2.5:cloud
ollama launch opencode --model kimi-k2.5:cloud
ollama launch openclaw --model kimi-k2.5:cloud
```

## Local model lifecycle

```bash
ollama run qwen3:30b       # local model; auto-pulls if not cached
ollama pull qwen3:30b      # pull without running
ollama ls                  # list locally cached models
ollama show qwen3:30b      # model details
ollama rm qwen3:30b        # delete a local model
ollama cp qwen3:30b my-qwen3
```

## Modelfile customization

```bash
cat > Modelfile << 'EOF'
FROM qwen3:30b
PARAMETER temperature 0.7
PARAMETER num_ctx 8192
SYSTEM You are a helpful coding assistant.
EOF

ollama create my-qwen3 -f Modelfile
```

## Cloud tag discovery

```bash
# Latest release notes
curl -sL "https://api.github.com/repos/ollama/ollama/releases" | jq -r '.[0] | .tag_name, .body' | head -50

# Featured model slugs
curl -sL "https://ollama.com/models" 2>/dev/null | grep -oP 'href="/library/[^"]+' | sort -u

# Check each slug for cloud tags
for model in deepseek-v4-flash glm-5.1 kimi-k2.6; do
  curl -sL "https://ollama.com/library/$model" | grep -oP '[a-z0-9_.-]+:[0-9a-z]+-cloud|[a-z0-9_.-]+:cloud' | sort -u
done
```

## Python client example

```python
import ollama

response = ollama.chat(
    model='qwen3-coder:480b-cloud',
    messages=[{'role': 'user', 'content': 'Explain quicksort'}],
)
print(response['message']['content'])

for chunk in ollama.chat(
    model='qwen3-coder:480b-cloud',
    messages=[{'role': 'user', 'content': 'Explain quicksort'}],
    stream=True,
):
    print(chunk['message']['content'], end='', flush=True)
```

## Native REST API

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "qwen3-coder:480b-cloud",
  "messages": [{"role": "user", "content": "Hello"}]
}'
```
