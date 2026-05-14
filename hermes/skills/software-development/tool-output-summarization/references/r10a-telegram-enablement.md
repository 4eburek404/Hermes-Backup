# R10A — Telegram Enablement Diagnostic

## Problem

Config set for Telegram compaction (`enabled:true, rollout_platforms:[telegram], enabled_output_kinds:[terminal]`), but no artifacts created and tool output returned verbatim.

## Root Cause

**Deployment mismatch:** Gateway process runs from production install, not the fork checkout.

| Component | Production (`/home/konstantin/.hermes/hermes-agent/`) | Fork (`/tmp/hermes-fork-development-clean-4v5Bch/`) |
|---|---|---|
| `run_agent.py` | 14,714 lines, **0** `_maybe_compact_tool_output` refs | 14,836 lines, **12** refs |
| `tools/budget_config.py` | 52 lines (stub, no `ToolOutputCompactionConfig`) | 230 lines (full implementation) |
| `scripts/tool_output_compaction.py` | **MISSING** | EXISTS (8,788 bytes) |
| `scripts/tool_output_summarizer.py` | **MISSING** | EXISTS |

The editable pip install (`__editable___hermes_agent_0_13_0_finder.py`) maps all module imports to `/home/konstantin/.hermes/hermes-agent/`. The gateway CWD is `/home/konstantin/.hermes/hermes-agent/` (confirmed via `/proc/PID/cwd`).

## Diagnostic Commands

```bash
# Verify running gateway's codebase
ls -la /proc/$(pgrep -f "hermes_cli.main gateway")/cwd

# Check production has compaction code
grep -c '_maybe_compact_tool_output' /home/konstantin/.hermes/hermes-agent/run_agent.py
wc -l /home/konstantin/.hermes/hermes-agent/tools/budget_config.py
ls /home/konstantin/.hermes/hermes-agent/scripts/tool_output_compaction.py

# Check editable install module mapping
cat /home/konstantin/.hermes/hermes-agent/venv/lib/python*/site-packages/__editable___hermes_agent*_finder.py | grep MAPPING
```

## Platform Resolution (Verified Correct)

- `_platform_config_key(Platform.TELEGRAM)` → `"telegram"`
- `AIAgent(platform="telegram")` → `self.platform = "telegram"`
- `should_compact("terminal", platform="telegram")` → `True` (when `rollout_platforms` includes `"telegram"`)
- `classify_output_kind("terminal")` → `"terminal"` (in `_TERMINAL_OUTPUT_TOOLS` frozenset)

The config and platform resolution are correct. The code path simply doesn't exist in production.

## Fix Options

### A. Deploy fork files to production (recommended)

Copy changed files from fork to production install, then restart gateway:
1. `run_agent.py` (+122 lines: `_maybe_compact_tool_output` + call sites)
2. `tools/budget_config.py` (replace 52-line stub → 230-line full)
3. `scripts/tool_output_compaction.py` (new)
4. `scripts/tool_output_summarizer.py` (new)
5. `systemctl --user restart hermes-gateway`
6. Verify: repeat R10A live check

### B. Symlink fork as production (risky)

1. `mv /home/konstantin/.hermes/hermes-agent/ /home/konstantin/.hermes/hermes-agent-backup/`
2. `ln -s /tmp/hermes-fork-development-clean-4v5Bch /home/konstantin/.hermes/hermes-agent`
3. `cd /home/konstantin/.hermes/hermes-agent && pip install -e .`
4. `systemctl --user restart hermes-gateway`

**Risk:** `/tmp/` checkouts can be lost on reboot. Option A is safer.

## Key Lesson

**Config without matching code is a silent no-op.** No error, no log, no warning. When rolling out a feature behind a config flag, always verify the *running code* implements the feature, not just that the config is set correctly.