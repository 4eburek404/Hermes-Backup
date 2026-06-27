from __future__ import annotations

from typing import Any

HUMAN_ANSWER_FORMAT_VERSION = "flight_human_answer.v1"


def build_human_answer_mirror(agent_report: dict[str, Any]) -> dict[str, Any]:
    """Diagnostic mirror for the canonical user answer.

    The active user-facing contract is ``agent_report.user_answer``. This
    projection deliberately does not render routes, caveats, or alternatives on
    its own; it only mirrors ``user_answer.rendered_text`` for diagnostic readers.
    """

    user_answer = (
        agent_report.get("user_answer")
        if isinstance(agent_report.get("user_answer"), dict)
        else {}
    )
    return {
        "format_version": HUMAN_ANSWER_FORMAT_VERSION,
        "text": str(user_answer.get("rendered_text") or ""),
        "sections": [],
    }
