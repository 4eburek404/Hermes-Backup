# Ollama Cloud Models — Reference

Scraped from ollama.com library pages, blog posts, and GitHub releases on 2026-05-05.

## New Cloud Models (v0.22–v0.23 era)

These models appeared on the featured models page after the initial cloud launch. Source: `/library/<model>` pages + GitHub Releases API.

| Tag | Source | Params | Notes |
|-----|--------|--------|-------|
| `deepseek-v4-flash:cloud` | `/library/deepseek-v4-flash` | 284B total / 13B active (MoE) | Preview, 1M context |
| `deepseek-v4-pro:cloud` | `/library/deepseek-v4-pro` | MoE, 1M context | Three reasoning modes |
| `glm-5.1:cloud` | `/library/glm-5.1` | — | Next-gen flagship; SWE-Bench Pro leader |
| `kimi-k2.6:cloud` | `/library/kimi-k2.6` | — | Multimodal agentic; swarm orchestration |
| `nemotron-3-super:cloud` | `/library/nemotron-3-super` | 120B total / 12B active (MoE) | NVIDIA multi-agent |
| `qwen3-coder-next:cloud` | `/library/qwen3-coder-next` | — | Agentic coding |
| `ministral-3:3b-cloud` | `/library/ministral-3` | 3B | Small Mistral |
| `ministral-3:8b-cloud` | `/library/ministral-3` | 8B | Medium Mistral |
| `ministral-3:14b-cloud` | `/library/ministral-3` | 14B | Large Mistral |

## Established Cloud Models (v0.12–v0.21 era)

| Tag | Source | Params | Notes |
|-----|--------|--------|-------|
| `glm-5:cloud` | `/blog/web-search-subagents-claude-code`, `/library/glm-5` | 744B total / 40B active (MoE) | Reasoning + agents |
| `minimax-m2.5:cloud` | `/blog/web-search-subagents-claude-code`, `/library/minimax-m2.5` | — | Productivity + coding; recommended for subagents |
| `kimi-k2.5:cloud` | `/blog/web-search-subagents-claude-code`, `/library/kimi-k2.5` | — | Multimodal agentic |
| `qwen3.5:397b-cloud` / `qwen3.5:cloud` | `/library/qwen3.5` | 397B MoE | General-purpose |
| `qwen3-vl:235b-cloud` | `/library/qwen3-vl` | 235B | Multimodal VL |
| `gemma4:31b-cloud` | `/library/gemma4` | 31B | — |
| `devstral-small-2:24b-cloud` | `/library/devstral-small-2` | 24B | Mistral coding |
| `kimi-k2:1t-cloud` | `/library/kimi-k2` | 1T | Older Kimi |
| `deepseek-v3.1:671b-cloud` | `/blog/cloud-models` | 671B | Initial 4 cloud models |
| `qwen3-coder:480b-cloud` | `/blog/cloud-models`, `/blog/coding-models`, `/blog/launch` | 480B MoE | Coding; local needs 300GB+ VRAM |
| `glm-4.7:cloud` | `/blog/launch`, `/blog/claude` | — | Claude Code/Zed integration |
| `glm-4.6:cloud` | `/blog/coding-models` | 357B | VS Code/Zed/Claude Code/OpenCode |
| `gpt-oss:120b-cloud` | `/blog/cloud-models`, `/blog/launch`, `/blog/codex` | 120B | Open reasoning; Codex CLI |
| `gpt-oss:20b-cloud` | `/blog/cloud-models` | 20B | Smaller open reasoning |
| `minimax-m2.1:cloud` | `/blog/launch` | 230B total / 10B active (MoE) | Updated MiniMax |
| `minimax-m2:cloud` | `/blog/minimax-m2` | 230B total / 10B active (MoE) | Coding + agentic |

## Version History (Cloud-Related)

| Version | Date | Cloud features |
|---------|------|---------------|
| v0.12 | — | Cloud models preview: initial 4 models. Free tier, no data retention. |
| v0.22.0 | 2026-04-28 | Nemotron 3 Omni + Laguna XS.2 local models. |
| v0.22.1 | 2026-04-28 | Gemma 4 renderer fix, model recommendations via server. |
| v0.23.0 | 2026-05-03 | Claude Desktop integration via `ollama launch claude-desktop`. Third-party inference for Claude Cowork + Claude Code. Web Search and Extensions not yet supported in Desktop. Server-driven featured models. |

## Recommended Cloud Models for Agents (Ollama blog)

- `minimax-m2.5:cloud` — auto-triggers web search subagents
- `glm-5:cloud` — auto-triggers subagents
- `kimi-k2.5:cloud` — auto-triggers subagents

## Discovery Commands

### GitHub Releases (best for version features)

```bash
curl -sL "https://api.github.com/repos/ollama/ollama/releases/tags/v0.23.0" | jq -r '.body'
```

### Quick cloud model scan (model library pages)

```bash
for model in deepseek-v4-flash deepseek-v4-pro glm-5 glm-5.1 kimi-k2.6 nemotron-3-super \
  qwen3-coder-next qwen3.5 qwen3-vl gemma4 devstral-small-2 kimi-k2 minimax-m2.5; do
  echo "=== $model ==="
  curl -sL "https://ollama.com/library/$model" | grep -oP '[a-z0-9_.-]+:[0-9a-z]+-cloud|[a-z0-9_.-]+:cloud' | sort -u
done
```

### Full cloud model scan (blogs + library pages combined)

```bash
# Blog-based scan
for url in \
  "https://ollama.com/blog/cloud-models" \
  "https://ollama.com/blog/launch" \
  "https://ollama.com/blog/coding-models" \
  "https://ollama.com/blog/web-search-subagents-claude-code"; do
  curl -sL "$url" 2>/dev/null | grep -oP '[a-z0-9_.-]+:[0-9a-z]+-cloud|[a-z0-9_.-]+:cloud'
done | sort -u
```

### Featured models page (discovers new additions)

```bash
curl -sL "https://ollama.com/models" 2>/dev/null | grep -oP 'href="/library/[^"]+' | sort -u
# Then check each slug for :cloud tags
```

### Blog content extraction

```bash
curl -sL "https://ollama.com/blog/<slug>" | sed 's/<[^>]*>//g' \
  | sed 's/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g; s/&nbsp;/ /g' \
  | tr -s ' \n'
```

## Blog Slugs

| Slug | Topic |
|------|-------|
| `/blog/cloud-models` | Cloud models preview announcement (initial 4 models) |
| `/blog/launch` | `ollama launch` command + cloud model list |
| `/blog/coding-models` | GLM-4.6 + Qwen3-Coder cloud |
| `/blog/minimax-m2` | MiniMax M2 cloud |
| `/blog/web-search-subagents-claude-code` | Subagents + recommended cloud models (glm-5, minimax-m2.5, kimi-k2.5) |
| `/blog/claude` | Anthropic Messages API compatibility |
| `/blog/codex` | OpenAI Codex CLI integration |
| `/blog/openclaw` | OpenClaw agent + cloud models |
| `/blog/openclaw-tutorial` | OpenClaw setup tutorial |
| `/blog/image-generation` | Z-Image Turbo + FLUX image generation |

## Pricing / Access

- Cloud models require `ollama v0.12+`
- Sign in: `ollama login` (browser opens ollama.com auth)
- Free tier: generous rate limits for individual use
- Higher rate limits available via Ollama's cloud subscription
- Data retention: **none** — Ollama does not retain prompt/completion data

## Claude Desktop Integration (v0.23+)

- `ollama launch claude-desktop` — launches Claude Desktop with Ollama as third-party inference
- All Cloud models available inside Claude Cowork and Claude Code (Desktop)
- CLI Claude Code unchanged: `ollama launch claude`
- Not yet supported in Desktop: Web Search (coming soon), Extensions