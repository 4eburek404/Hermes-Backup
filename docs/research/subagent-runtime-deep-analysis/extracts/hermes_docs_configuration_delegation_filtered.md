---
title: Configuration | Hermes Agent
description: Configure Hermes Agent — config.yaml, providers, models, API keys, and more
url: https://hermes-agent.nousresearch.com/docs/user-guide/configuration
site: hermes-agent.nousresearch.com
generator: Docusaurus v3.9.2
---

## Delegation

Configure subagent behavior for the delegate tool:

```
delegation:
  max_concurrent_children: 3                
  max_spawn_depth: 1                        
  orchestrator_enabled: true                
```

**Subagent provider:model override:** By default, subagents inherit the parent agent's provider and model. Set `delegation.provider` and `delegation.model` to route subagents to a different provider:model pair — e.g., use a cheap/fast model for narrowly-scoped subtasks while your primary agent runs an expensive reasoning model.

**Direct endpoint override:** If you want the obvious custom-endpoint path, set `delegation.base_url`, `delegation.api_key`, and `delegation.model`. That sends subagents directly to that OpenAI-compatible endpoint and takes precedence over `delegation.provider`. If `delegation.api_key` is omitted, Hermes falls back to `OPENAI_API_KEY` only.

The delegation provider uses the same credential resolution as CLI/gateway startup. All configured providers are supported: `openrouter`, `nous`, `copilot`, `zai`, `kimi-coding`, `minimax`, `minimax-cn`. When a provider is set, the system automatically resolves the correct base URL, API key, and API mode — no manual credential wiring needed.

**Precedence:** `delegation.base_url` in config → `delegation.provider` in config → parent provider (inherited). `delegation.model` in config → parent model (inherited). Setting just `model` without `provider` changes only the model name while keeping the parent's credentials (useful for switching models within the same provider like OpenRouter).

**Width and depth:** `max_concurrent_children` caps how many subagents run in parallel per batch (default `3`, floor of 1, no ceiling). Can also be set via the `DELEGATION_MAX_CONCURRENT_CHILDREN` env var. When the model submits a `tasks` array longer than the cap, `delegate_task` returns a tool error explaining the limit rather than silently truncating. `max_spawn_depth` controls the delegation tree depth (clamped to 1-3). At the default `1`, delegation is flat: children cannot spawn grandchildren, and passing `role="orchestrator"` silently degrades to `leaf`. Raise to `2` so orchestrator children can spawn leaf grandchildren; `3` for three-level trees. The agent opts into orchestration per call via `role="orchestrator"`; `orchestration_enabled: false` forces every child back to leaf regardless. Cost scales multiplicatively — at `max_spawn_depth: 3` with `max_concurrent_children: 3`, the tree can reach 3×3×3 = 27 concurrent leaf agents. See [Subagent Delegation → Depth Limit and Nested Orchestration](/docs/user-guide/features/delegation#depth-limit-and-nested-orchestration) for usage patterns.

---

Powered by [curl.md](https://curl.md)
