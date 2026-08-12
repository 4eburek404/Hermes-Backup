# Subagent Model Configuration for Source Discovery

Session 2026-08-12: The user asked to run subagents on specific models (deepseek-v4-flash:0731, "codex 5.6 luna high"). Key findings.

## delegate_task Model Inheritance

`delegate_task` subagents **inherit the parent's model by default**. The tool has NO parameter to select a model per-subagent.

To use different models for subagents, set these in `config.yaml` under `delegation:`:

```yaml
delegation:
  model: ''          # e.g. 'deepseek-v4-flash:0731'
  provider: ''       # e.g. 'ollama-cloud'
  base_url: ''       # optional override
  api_key: ''        # optional override
  api_mode: ''       # optional override
  reasoning_effort: ''  # optional
```

Or via CLI:
```bash
hermes config set delegation.model deepseek-v4-flash:0731
hermes config set delegation.provider ollama-cloud
```

**IMPORTANT:** This is a GLOBAL setting — ALL subagents use the same model. You cannot run different subagents on different models in the same delegation batch.

## Available Ollama Cloud Models (as of 2026-08-12)

Query the API to get the current list:
```bash
OLLAMA_KEY=$(grep OLLAMA_API_KEY "$HOME/AppData/Local/hermes/.env" | tail -1 | sed 's/.*=//')
curl -s "https://ollama.com/v1/models" -H "Authorization: Bearer $OLLAMA_KEY" | python -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('data', []):
    print(m.get('id', ''))
"
```

Known available models:
- `deepseek-v4-flash:0731` — fast, good for search/discovery
- `deepseek-v4-pro` — reasoning-heavy
- `glm-5.2` — current default
- `kimi-k2.6` / `kimi-k2.7-code` / `kimi-k3` — code-oriented
- `nemotron-3-ultra` / `nemotron-3-super` — Nous Research
- `minimax-m2.7` / `minimax-m3`
- `mistral-large-3:675b`
- `qwen3.5:397b`
- `gpt-oss:20b` / `gpt-oss:120b`

**Note:** "codex 5.6 luna high" is NOT available on Ollama Cloud. Closest alternatives: `kimi-k2.7-code` (code-oriented) or `deepseek-v4-pro` (reasoning).

## delegate_task Cannot Be Cancelled

There is no way to stop a running subagent. If you dispatch a batch and need to cancel:
- Let them finish and discard the results
- Do NOT dispatch duplicate batches expecting to cancel the first

## Subagent Source Discovery Workflow

The user may ask for more sources ("нужно больше сайтов") and specify:
- Number of subagents (e.g. "двух субагентов")
- Roles (e.g. "один РФ, один за рубеж")
- Models (e.g. "deepseek-v4-flash:0731 и codex 5.6 luna high")
- Role swapping ("поменяй их ролями")

**Pattern:**
1. Dispatch subagents via `delegate_task` with `tasks: [{goal, context}, {goal, context}]`
2. If the user asks to swap roles, dispatch a second pair with swapped goals
3. Wait for ALL subagents to complete (results re-enter conversation automatically)
4. Merge results into a single unified list

**Pitfall:** If the user specifies different models per subagent, explain that `delegate_task` uses a single global model (`delegation.model` in config.yaml). Offer to set it before dispatching, or let them run on the inherited model and reconfigure for next time.

**Pitfall:** If the user asks to stop some subagents but not others, explain that cancellation is not supported. Suggest letting them finish and discarding unwanted results.