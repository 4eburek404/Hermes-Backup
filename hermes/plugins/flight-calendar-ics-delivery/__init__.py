"""Hermes plugin: automatic flight-calendar-ics delivery.

The flight-calendar-ics skill is a producer: it creates a verified private
bundle and emits an agent_handoff object. This plugin owns the Hermes-specific
delivery side effect so the agent does not need to inspect, redact, refold, or
otherwise mutate the generated .ics file after a successful build.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PLUGIN_NAME = "flight-calendar-ics-delivery"
_DEFAULT_TARGET = "telegram"
_DELIVERY_BY_KEY: dict[str, dict[str, Any]] = {}
_DELIVERED_PATHS: set[str] = set()


def register(ctx) -> None:
    """Register delivery and guard hooks. Called once by Hermes plugin loader."""
    ctx.register_hook("post_tool_call", _make_post_tool_call(ctx))
    ctx.register_hook("transform_tool_result", _make_transform_tool_result(ctx))
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    logger.info("%s: registered", _PLUGIN_NAME)


def _make_post_tool_call(ctx) -> Callable[..., None]:
    def _on_post_tool_call(**kwargs: Any) -> None:
        handoff = _extract_delivery_handoff(kwargs.get("result"))
        if handoff is None:
            return
        _ensure_delivered(ctx, handoff, kwargs)

    return _on_post_tool_call


def _make_transform_tool_result(ctx) -> Callable[..., str | None]:
    def _on_transform_tool_result(**kwargs: Any) -> str | None:
        handoff = _extract_delivery_handoff(kwargs.get("result"))
        if handoff is None:
            return None
        delivery = _ensure_delivered(ctx, handoff, kwargs)
        if not delivery.get("delivered"):
            return None
        return json.dumps(
            {
                "ok": True,
                "delivery": {
                    "plugin": _PLUGIN_NAME,
                    "delivered": True,
                    "target": delivery.get("target"),
                    "media": handoff["media"],
                    "safe_summary": handoff.get("safe_summary") or {},
                },
                "agent_instruction": (
                    "The flight calendar .ics has already been delivered. "
                    "Do not read, edit, redact, refold, or reserialize the .ics. "
                    "Reply with a concise confirmation using only safe_summary."
                ),
            },
            ensure_ascii=False,
        )

    return _on_transform_tool_result


def _on_pre_tool_call(*, tool_name: str = "", args: dict | None = None, **kwargs: Any) -> dict[str, str] | None:
    if not _DELIVERED_PATHS:
        return None
    if tool_name not in {
        "terminal",
        "execute_code",
        "read_file",
        "write_file",
        "patch",
        "search_files",
        "edit_file",
    }:
        return None
    if not _mentions_delivered_ics(args or {}):
        return None
    return {
        "action": "block",
        "message": (
            "flight-calendar-ics delivery is complete. The delivered .ics must not be "
            "read, edited, redacted, refolded, or reserialized after handoff."
        ),
    }


def _ensure_delivered(ctx, handoff: dict[str, Any], hook_kwargs: dict[str, Any]) -> dict[str, Any]:
    key = _delivery_key(handoff, hook_kwargs)
    existing = _DELIVERY_BY_KEY.get(key)
    if existing is not None:
        return existing

    target = _delivery_target()
    media = handoff["media"]
    message = _delivery_message(media, handoff.get("safe_summary") or {})
    try:
        result = ctx.dispatch_tool(
            "send_message",
            {"action": "send", "target": target, "message": message},
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        delivery = {"delivered": False, "target": target, "error": str(exc)}
        logger.warning("%s: delivery failed: %s", _PLUGIN_NAME, exc)
    else:
        if _tool_result_has_error(result):
            delivery = {"delivered": False, "target": target, "error": _short_error(result)}
            logger.warning("%s: send_message returned error: %s", _PLUGIN_NAME, delivery["error"])
        else:
            delivery = {"delivered": True, "target": target}
            path = _media_path(media)
            if path:
                _DELIVERED_PATHS.add(path)

    _DELIVERY_BY_KEY[key] = delivery
    return delivery


def _delivery_target() -> str:
    try:
        from hermes_cli.config import cfg_get

        value = cfg_get(None, "plugins", "flight_calendar_ics_delivery", "target")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        pass
    return _DEFAULT_TARGET


def _delivery_message(media: str, safe_summary: dict[str, Any]) -> str:
    route = str(safe_summary.get("route") or "flight-calendar-ics")
    segments_count = safe_summary.get("segments_count")
    if isinstance(segments_count, int):
        caption = f"Flight calendar ready: {route}, segments={segments_count}"
    else:
        caption = f"Flight calendar ready: {route}"
    return f"{caption}\n{media}"


def _delivery_key(handoff: dict[str, Any], hook_kwargs: dict[str, Any]) -> str:
    tool_call_id = str(hook_kwargs.get("tool_call_id") or "").strip()
    if tool_call_id:
        return f"tool_call:{tool_call_id}"
    return f"media:{handoff['media']}"


def _extract_delivery_handoff(raw_result: Any) -> dict[str, Any] | None:
    for obj in _candidate_objects(raw_result):
        if not isinstance(obj, dict):
            continue
        if obj.get("ok") is not True:
            continue
        data = obj.get("data")
        if not isinstance(data, dict):
            continue
        handoff = data.get("agent_handoff")
        if not isinstance(handoff, dict):
            continue
        if handoff.get("ready") is not True:
            continue
        if handoff.get("no_further_action_needed") is not True:
            continue
        if handoff.get("artifact_inspection_required") is not False:
            continue
        media = handoff.get("media")
        if not (isinstance(media, str) and media.startswith("MEDIA:/")):
            continue
        safe_summary = handoff.get("safe_summary")
        if safe_summary is not None and not isinstance(safe_summary, dict):
            continue
        return {"media": media, "safe_summary": safe_summary or {}}
    return None


def _candidate_objects(raw_result: Any) -> list[Any]:
    candidates: list[Any] = []
    if isinstance(raw_result, dict):
        candidates.extend(_objects_from_dict(raw_result))
    elif isinstance(raw_result, str):
        for parsed in _parse_json_candidates(raw_result):
            if isinstance(parsed, dict):
                candidates.extend(_objects_from_dict(parsed))
            else:
                candidates.append(parsed)
    return candidates


def _objects_from_dict(obj: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = [obj]
    for key in ("stdout", "output", "content", "result"):
        value = obj.get(key)
        if isinstance(value, str):
            candidates.extend(_parse_json_candidates(value))
    return candidates


def _parse_json_candidates(text: str) -> list[Any]:
    parsed: list[Any] = []
    stripped = text.strip()
    if not stripped:
        return parsed
    try:
        parsed.append(json.loads(stripped))
        return parsed
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if 0 <= start < end:
        try:
            parsed.append(json.loads(stripped[start : end + 1]))
        except json.JSONDecodeError:
            pass
    return parsed


def _tool_result_has_error(raw_result: Any) -> bool:
    for obj in _candidate_objects(raw_result):
        if isinstance(obj, dict) and obj.get("error"):
            return True
    return False


def _short_error(raw_result: Any) -> str:
    text = str(raw_result)
    return text if len(text) <= 240 else text[:237] + "..."


def _mentions_delivered_ics(args: dict[str, Any]) -> bool:
    text = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    for delivered_path in _DELIVERED_PATHS:
        if delivered_path in text:
            return True
        name = Path(delivered_path).name
        if name and name in text:
            return True
    return False


def _media_path(media: str) -> str:
    if media.startswith("MEDIA:"):
        return media[len("MEDIA:") :]
    return ""


def _reset_state_for_tests() -> None:
    _DELIVERY_BY_KEY.clear()
    _DELIVERED_PATHS.clear()
