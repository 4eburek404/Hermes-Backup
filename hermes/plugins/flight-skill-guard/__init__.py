"""Flight-search skill guard plugin for Hermes Agent.

Enforces the flight-search Golden Path by blocking direct calls to
travelpayouts_flight_search (and other guarded flight tools) until the
'flight-search' skill has been loaded via skill_view() in the current session.

Why this exists:
  The LLM frequently calls travelpayouts_flight_search directly, ignoring
  the skill's instruction to use flights_cli route live-assemble first.
  Prompt-only constraints ("Do not call X, use Y") achieve ~70-85% compliance;
  this runtime guard achieves 95%+ by returning a BLOCK error that forces
  the model to call skill_view('flight-search').

Config (optional, in config.yaml):
  plugins.flight_skill_guard.enabled: true   (default: true when installed)
  plugins.flight_skill_guard.guarded_tools:   (override if you add more tools)
    - travelpayouts_flight_search

The guard is session-scoped: loading the skill once per session unlocks the
guarded tools for the rest of that session.  This prevents accidental bypass
while allowing travelpayouts as a debug/validation fallback after the CLI
has been consulted.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

_FLIGHT_SEARCH_SKILL = "flight-search"

# Tools that are blocked until the skill is loaded.
# Extensible via config or by editing this set.
_DEFAULT_GUARDED_TOOLS: Set[str] = {
    "travelpayouts_flight_search",
}

# Session-level tracking: sessions that have loaded the flight-search skill.
# In-process only; restart clears it (which is correct — skill must be loaded
# each session so the model sees the instructions fresh).
_sessions_with_skill_loaded: Set[str] = set()


# ── Hook handlers ─────────────────────────────────────────────────────────

def register(ctx) -> None:
    """Register flight-skill-guard hooks. Called once by Hermes plugin loader."""
    # Read optional config overrides
    guarded_tools = _DEFAULT_GUARDED_TOOLS.copy()
    try:
        from hermes_cli.config import cfg_get
        custom = cfg_get(None, "plugins", "flight_skill_guard", "guarded_tools")
        if isinstance(custom, list):
            guarded_tools = set(custom)
    except Exception:
        pass

    ctx.register_hook("pre_tool_call", _make_pre_tool_call(guarded_tools))
    ctx.register_hook("post_tool_call", _on_post_tool_call)

    logger.info(
        "flight-skill-guard: registered — guarding %s until skill_view('%s') is called",
        guarded_tools, _FLIGHT_SEARCH_SKILL,
    )


def _make_pre_tool_call(guarded_tools: Set[str]):
    """Return a pre_tool_call hook that blocks guarded tools."""

    def _on_pre_tool_call(
        *,
        tool_name: str = "",
        args: Optional[Dict[str, Any]] = None,
        task_id: str = "",
        session_id: str = "",
        tool_call_id: str = "",
    ) -> Optional[Dict[str, str]]:
        """Block guarded flight tools unless the skill was loaded this session."""
        if tool_name not in guarded_tools:
            return None

        if session_id and session_id in _sessions_with_skill_loaded:
            # Skill already loaded this session → allow the call
            return None

        # Block with an actionable error that tells the model exactly what to do
        return {
            "action": "block",
            "message": (
                f"🚫 BLOCKED: {tool_name} cannot be called directly for flight searches. "
                f"You MUST call skill_view('{_FLIGHT_SEARCH_SKILL}') first to load the "
                f"flight-search workflow, then follow its Golden Path using "
                f"flights_cli route live-assemble. "
                f"After loading the skill once this session, {tool_name} will be "
                f"available for debug/validation fallback."
            ),
        }

    return _on_pre_tool_call


def _on_post_tool_call(
    *,
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: str = "",
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **kwargs,
) -> None:
    """Track when skill_view('flight-search') is called to unlock guarded tools."""
    if tool_name != "skill_view":
        return

    if not args:
        # Some dispatch paths pass args differently; try result-based detection
        # as a fallback (if the skill_view succeeded, it contains the skill name)
        if session_id and '"flight-search"' in result or "'flight-search'" in result:
            _sessions_with_skill_loaded.add(session_id)
            logger.debug("flight-skill-guard: skill loaded for session %s (via result)", session_id)
        return

    skill_name = args.get("name", "")
    if skill_name == _FLIGHT_SEARCH_SKILL:
        if session_id:
            _sessions_with_skill_loaded.add(session_id)
            logger.info(
                "flight-skill-guard: unlocked for session %s — flight-search skill loaded",
                session_id,
            )