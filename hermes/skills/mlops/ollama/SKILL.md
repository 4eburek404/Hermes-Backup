---
name: ollama
description: Run, pull, and manage models via Ollama — local GGUF inference and cloud-hosted models. Model discovery, tag selection, CLI usage, and API integration.
version: 1.0.0
author: Orchestra Research
license: MIT
metadata:
  hermes:
    tags: [ollama, LLM, inference, cloud-models, local-models, CLI, API]
---

# Ollama — Local & Cloud Model Management

Use this skill when the user asks about Ollama: running models, pulling models, cloud vs local tags, model discovery, CLI commands, API integration, or choosing the right model size/tag for their hardware.

## Cloud Models

Ollama v0.12+ offers cloud-hosted models with datacenter-grade hardware. Cloud models require sign-in to `ollama.com` and have a free tier with generous limits. Data is not retained on the server.

### Available cloud models (May 2026)

**Newest (v0.22–v0.23 era):**

| Tag | Params | Notes |
|-----|--------|-------|
| `deepseek-v4-flash:cloud` | 284B total / 13B active (MoE) | DeepSeek V4 preview, 1M context |
| `deepseek-v4-pro:cloud` | MoE, 1M context | Three reasoning modes |
| `glm-5.1:cloud` | — | Next-gen flagship; SWE-Bench Pro leader, agentic engineering |
| `kimi-k2.6:cloud` | — | Multimodal agentic; long-horizon coding, swarm orchestration |
| `nemotron-3-super:cloud` | 120B total / 12B active (MoE) | NVIDIA multi-agent efficiency |
| `qwen3-coder-next:cloud` | — | Agentic coding workflows |
| `qwen3.5:397b-cloud` / `qwen3.5:cloud` | 397B MoE | General-purpose |

**Established (v0.12–v0.21 era):**

| Tag | Params | Notes |
|-----|--------|-------|
| `glm-5:cloud` | 744B total / 40B active (MoE) | Reasoning + agents + systems engineering |
| `minimax-m2.5:cloud` | — | Productivity + coding; recommended for subagents |
| `kimi-k2.5:cloud` | — | Multimodal (vision+language+agentic), instant/thinking modes |
| `minimax-m2:cloud` / `minimax-m2.1:cloud` | 230B total / 10B active | MoE, coding + agents |
| `qwen3-vl:235b-cloud` | 235B | Multimodal VL |
| `qwen3-coder:480b-cloud` | 480B MoE | Coding-focused |
| `deepseek-v3.1:671b-cloud` | 671B | One of initial 4 cloud models |
| `gpt-oss:120b-cloud` | 120B | Open reasoning; Codex CLI |
| `gpt-oss:20b-cloud` | 20B | Smaller open reasoning |
| `glm-4.7:cloud` | — | Claude Code/Zed integration |
| `glm-4.6:cloud` | 357B | VS Code/Zed/Claude Code/OpenCode |
| `gemma4:31b-cloud` | 31B | — |
| `devstral-small-2:24b-cloud` | 24B | Mistral coding model |
| `kimi-k2:1t-cloud` | 1T | Older Kimi |
| `ministral-3:3b-cloud` / `:8b-cloud` / `:14b-cloud` | 3B/8B/14B | Multiple sizes |

### Recommended cloud models for agents (Ollama blog)

- `minimax-m2.5:cloud` — auto-triggers web search subagents
- `glm-5:cloud` — auto-triggers subagents
- `kimi-k2.5:cloud` — auto-triggers subagents

### Cloud model usage

Examples moved to `references/usage-examples.md`. For cloud models, use `ollama show` or the localhost API; do not run/pull cloud tags from agent tool calls.

### Cloud model quirks

- **Structured output**: Cloud models do NOT support `json_schema` enforcement — grammar-based constrained decoding doesn't apply to remote models. Use `json_object` + enums in system prompt + `strip_codeblock()` instead. This gives ~100% compliance across all cloud models.
- **Context length**: Cloud models get full context length (no truncation unlike local runs on limited VRAM).
- **`ollama-local` provider** on `http://127.0.0.1:11434/v1` does NOT require an API key even for `:cloud` tags — the key is only needed for the `ollama-cloud` provider.
- **`ollama ls`** shows cloud models alongside local ones. Cloud models display a small placeholder size.

## Local Models

### Running models locally

Examples moved to `references/usage-examples.md` to keep the instruction core separate from executable snippets.

### Choosing a local model tag

- Default tag (e.g. `qwen3:30b`) = recommended quantization, good balance of speed and quality.
- For more precision: try larger parameters or different quant suffixes if available.
- Check available tags: `ollama list` for locally cached, or browse `https://ollama.com/library/<model>/tags`.

### Modelfile customization

Examples moved to `references/usage-examples.md` to keep the instruction core separate from executable snippets.

## Model Discovery

### Finding new models

Examples moved to `references/usage-examples.md` to keep the instruction core separate from executable snippets.

### Scraping model lists from ollama.com

When browser is unavailable, use `curl` + GitHub Releases API. **Discovery priority order:**

1. **GitHub Releases API** — latest version features and new model announcements
2. **Featured models page** (`/models`) — lists currently promoted models (discover new slugs)
3. **Individual `/library/<model>` pages** — check each slug for `:cloud` tags (authoritative)
4. **Blog posts** — supplementary; always stale relative to `/library` pages

Examples moved to `references/usage-examples.md` to keep the instruction core separate from executable snippets.

### Blog post slugs for cloud models

Key blog posts to check for updates:
- `/blog/cloud-models` — original cloud models preview (4 initial models)
- `/blog/launch` — `ollama launch` command + cloud model list
- `/blog/coding-models` — GLM-4.6 + Qwen3-Coder cloud
- `/blog/minimax-m2` — MiniMax M2 cloud announcement
- `/blog/web-search-subagents-claude-code` — subagents + cloud model recommendations (glm-5, minimax-m2.5, kimi-k2.5)
- `/blog/openclaw` / `/blog/openclaw-tutorial` — OpenClaw agent + cloud models

## API Integration

### OpenAI-compatible endpoint

Examples moved to `references/usage-examples.md` to keep the instruction core separate from executable snippets.

### REST API

Examples moved to `references/usage-examples.md` to keep the instruction core separate from executable snippets.

## Pitfalls

- **Don't rely on old blog posts for version info:** The blog index at `/blog` may not list the newest posts. Use GitHub Releases API (`/repos/ollama/ollama/releases/tags/vX.Y.Z`) for authoritative version features, then check the newest blog slugs for cloud model additions.
- **Don't scrape old blog posts when checking current cloud models:** Blog posts reflect the model list *at publication time*, not the current state. Cloud models get added to library pages without new blog posts. Always scan `/library/<model>` pages for `:cloud` tags, starting from the featured models on `/models`. Scraping `/blog/cloud-models` gave the initial 4 models only — missed everything added since.
- **`json_schema` doesn't work on cloud**: Use `json_object` + prompt enums instead (see Cloud Model Quirks above).
- **Cloud models require auth and safe invocation**: validate with `ollama show <model>:cloud` or the localhost API. Do not use `ollama run <model>:cloud` from Hermes tool calls for smoke tests; it can pull blobs/fill disk in this setup. Local models can use `ollama run`.
- **`ollama-local` vs `ollama-cloud` provider**: The local provider proxies through localhost and doesn't need an API key even for `:cloud` tags. The cloud provider hits `api.ollama.com` and requires a key.
- **Model tag naming**: Cloud tags follow the pattern `<model>:<size>b-cloud` (e.g., `deepseek-v3.1:671b-cloud`) or `<model>:cloud` (e.g., `glm-5:cloud`).
- **Scraping ollama.com**: The site is JS-heavy. `curl` gets initial HTML but may miss dynamic content. Blog posts render text well with `sed 's/<[^>]*>//g'`. GitHub Releases API returns JSON with full release notes.
- **v0.23 Claude Desktop integration**: Requires `ollama launch claude-desktop`. Web Search and Extensions are not yet supported inside Claude Desktop. CLI Claude Code still works via `ollama launch claude`.

## References

- **[cloud-models.md](references/cloud-models.md)** — Full list of cloud model tags, blog sources, and discovery commands
- **[usage-examples.md](references/usage-examples.md)** — executable CLI/API/Python examples kept outside `SKILL.md`