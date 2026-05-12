# Hermes Toolset Audit Workflow

How to trace why a specific tool (e.g., `cronjob`) appears in session tool schemas — and how to plan its safe exclusion. Read-only until a concrete config/code change is approved.

## Quick diagnostic questions

- Is the tool in `_HERMES_CORE_TOOLS` (toolsets.py:31-68)?
- Which platform toolset is the session using? (Check `platform_toolsets` in config.yaml → `_get_platform_tools()`)
- Does the tool have a `check_fn` or conditional gating, or is it unconditionally included?

**If the answer is «in `_HERMES_CORE_TOOLS`, no check_fn» → the tool is universal across all platform defaults.** It will appear in every session regardless of task type.

## Core inclusion path (worked example: cronjob)

```
tools/cronjob_tools.py          → registers "cronjob"
model_tools.py:233              → "cronjob_tools": ["cronjob"]
toolsets.py:58                  → "cronjob" in _HERMES_CORE_TOOLS
toolsets.py:373                 → hermes-telegram.tools = _HERMES_CORE_TOOLS
toolsets.py:356                 → hermes-cli.tools = _HERMES_CORE_TOOLS
  (same for hermes-discord, hermes-slack, hermes-whatsapp, etc.)
gateway/run.py:9236             → enabled_toolsets = _get_platform_tools(config, platform)
hermes_cli/tools_config.py:823  → _get_platform_tools reads config["platform_toolsets"][platform]
hermes_cli/tools_config.py:862  → resolve_toolset("hermes-telegram") → all _HERMES_CORE_TOOLS
run_agent.py:1624               → get_tool_definitions(enabled_toolsets=…) returns schemas
model_tools.py:344              → for each toolset_name: resolve + update tool set
```

**Result:** Every session using a platform default (hermes-cli, hermes-telegram, etc.) gets the tool unconditionally.

## Search commands for tracing

```bash
# Find tool registration
rg -n "tool_name|register.*tool" tools/ model_tools.py

# Find toolset membership
rg -n "tool_name|_HERMES_CORE_TOOLS" toolsets.py

# Find platform_toolsets resolution
rg -n "platform_toolsets|_get_platform_tools|enabled_toolsets" gateway/run.py hermes_cli/tools_config.py cli.py run_agent.py model_tools.py

# Find schema generation
rg -n "get_tool_definitions|resolve_toolset" model_tools.py run_agent.py cli.py
```

## Quantifying overhead with the analyzer

```bash
python scripts/analyze_context_overhead.py \
  --sessions-index ~/.hermes/sessions/sessions.json \
  --sessions-dir ~/.hermes/sessions \
  --limit 20 \
  --out-md /tmp/hermes_context_baseline.md \
  --out-json /tmp/hermes_context_baseline.json
```

From the JSON output, check:
- `snapshot_sizing.tools_schema_tokens` — total tool schema overhead
- `system_prompt.sessions[].tools_schema` section — per-session tool presence
- Tool name + `estimated_tokens` — individual tool cost

## When a tool is in `_HERMES_CORE_TOOLS` and has no check_fn

Options ranked by invasiveness:

| Approach | Code change | Config change | Rollback |
|---|---|---|---|
| Remove from `_HERMES_CORE_TOOLS`, add to desired platform_toolsets via config | 1 line | Yes (add to config) | Revert 1 line |
| Add `check_fn` (env var gate) | ~10 lines | Yes (env var) | Revert code |
| Add per-tool exclusion to `_get_platform_tools` | ~30 lines | Yes (config list) | Revert code |
| Do nothing — accept the overhead | 0 | 0 | N/A |

## When a dedicated toolset already exists

If the tool already has a standalone toolset in `TOOLSETS` (like `"cronjob"` at toolsets.py:135), removal from `_HERMES_CORE_TOOLS` is the simplest path: the standalone toolset remains for opt-in via `platform_toolsets` config, and the tool disappears from all platform defaults.

## Safe removal experiment procedure

When removing a tool from `_HERMES_CORE_TOOLS` (and a standalone toolset already exists):

### Phase A — Pre-measurement

```bash
python scripts/analyze_context_overhead.py --limit 20 \
  --out-md /tmp/hermes_pre_experiment.md --out-json /tmp/hermes_pre_experiment.json
```

### Phase B — Apply the change

```bash
# Remove the tool string from _HERMES_CORE_TOOLS in toolsets.py
# Replace the commented line + tool line with a single comment
```

### Phase C — Validate resolution

```bash
python -c "
from toolsets import resolve_toolset
# Verify removal from ALL platform defaults (15+)
for p in ['hermes-cli','hermes-cron','hermes-telegram','hermes-discord',
          'hermes-whatsapp','hermes-slack','hermes-signal','hermes-bluebubbles',
          'hermes-homeassistant','hermes-email','hermes-mattermost',
          'hermes-matrix','hermes-dingtalk','hermes-feishu','hermes-weixin']:
    assert 'cronjob' not in resolve_toolset(p), f'{p}: still has cronjob'
# Verify standalone toolset intact
assert 'cronjob' in resolve_toolset('cronjob'), 'standalone broken'
print('OK')
"
```

### Phase D — Run targeted tests

The full test suite (~17k tests) times out in 60s. Run targeted:

```bash
python -m py_compile toolsets.py
pytest tests/test_analyze_context_overhead.py -q
pytest tests/cron/test_scheduler.py tests/tools/test_cronjob_tools.py \
  tests/hermes_cli/test_tools_config.py -x -q
```

### Phase E — Check pre-existing failures

Stash, test on HEAD~1, confirm same failures, unstash:

```bash
git stash
pytest tests/agent/test_prompt_builder.py::TestBuildSkillsSystemPromptConditional::test_requires_skill_hidden_when_toolset_missing \
  tests/cron/test_cron_script.py::TestBuildJobPromptWithScript::test_script_empty_output_noted \
  tests/cron/test_scheduler_mcp_init.py -x -q
# Same 4 failures → pre-existing, not caused by our change
git stash pop
```

### Phase F — Measure effect

```bash
python scripts/analyze_context_overhead.py --limit 20 \
  --out-md /tmp/hermes_post_experiment.md --out-json /tmp/hermes_post_experiment.json
```

Expected per-session saving: ~1,652 tokens (cronjob schema). Total for 20 sessions: ~33,040 tokens (~17.8% of tools_schema).

### Phase G — Verify cron-runner independence

Confirm `cron/scheduler.py` uses `disabled_toolsets=["cronjob", ...]` — the scheduler suppresses cronjob independently of `_HERMES_CORE_TOOLS`. Test at `tests/cron/test_scheduler.py:1555`: `assert "cronjob" in (kwargs["disabled_toolsets"] or [])`.

### Phase H — Safety check

```bash
git diff | grep -Ei 'api[_-]?key|secret|password|authorization|bearer' || echo "OK"
```

### Phase I — Opt-in verification

```bash
python -c "
from toolsets import resolve_toolset
combined = set(resolve_toolset('hermes-cli')) | set(resolve_toolset('cronjob'))
assert 'cronjob' in combined
print('Opt-in via enabled_toolsets=[hermes-cli,cronjob] works')
"
```

### Gotchas discovered

- `resolve_toolset` counts resolved tool names differently from the analyzer's per-session tool count (the analyzer counts individual tool schemas, which may differ from raw tool names in the resolution set).
- The full pytest suite times out (`-x -q` on 17k tests > 60s). Always run targeted tests.
- Pre-existing test failures are common in a fast-moving codebase; always verify on HEAD~1 before attributing failures to your change.
- Plugin auto-generated platforms (toolsets.py:604-618) also inherit `_HERMES_CORE_TOOLS` — removal propagates automatically.

## Verification checklist

- [ ] `rg` search confirms the tool's registration, toolset membership, and resolution path
- [ ] Analyzer baseline shows tool presence/absence before change
- [ ] Analyzer baseline after change confirms expected drop
- [ ] `pytest tests/test_analyze_context_overhead.py -q` passes
- [ ] No secrets in diff: `git diff | grep -Ei 'api[_-]?key|secret|password|authorization|bearer'`
- [ ] Config/platform_toolsets correctly wired for platforms that still need the tool
- [ ] `/reset` or new session picks up the change
