from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from ..errors import CliError


def parse_retry_after_seconds(value: Any, *, now: datetime | None = None) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    text = str(value).strip()
    if not text:
        return None, "empty"
    if text.isdigit():
        return max(0, int(text)), None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError) as exc:
        return None, type(exc).__name__
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    base = now or datetime.now(timezone.utc)
    return max(0, int((parsed - base).total_seconds())), None


def classify_failure(error_type: Any, message: Any, *, details: Any = None) -> dict[str, Any]:
    original_type = str(error_type or "error")
    text = str(message or "")
    lower = text.lower()
    detail_map = details if isinstance(details, dict) else {}
    retry_after = detail_map.get("retry_after") or detail_map.get("Retry-After")
    retry_after_seconds, retry_after_parse_error = parse_retry_after_seconds(retry_after)

    if original_type == "rate_limited" or "http 429" in lower or " 429" in lower or "too many requests" in lower:
        classification = "rate_limited"
        retryable = True
    elif original_type == "timeout" or "timeout" in lower or "timed out" in lower:
        classification = "timeout"
        retryable = True
    elif original_type == "provider_unavailable" or any(
        token in lower
        for token in (
            "connection refused",
            "connection reset",
            "name or service not known",
            "temporary failure",
            "network is unreachable",
            "nodename nor servname",
            "failed to establish",
        )
    ):
        classification = "provider_unavailable"
        retryable = True
    elif any(token in lower for token in ("captcha", "cloudflare", "access denied", "forbidden", "bot", "blocked")):
        classification = "blocked_response"
        retryable = False
    elif any(token in lower for token in ("invalid json", "jsondecodeerror", "does not contain", "parse", "parser")):
        classification = "parse_error"
        retryable = False
    elif original_type in {"upstream_error", "error"}:
        classification = "upstream_error"
        retryable = False
    else:
        classification = original_type
        retryable = False

    result: dict[str, Any] = {
        "classification": classification,
        "retryable": retryable,
    }
    if retry_after_seconds is not None:
        result["retry_after_seconds"] = retry_after_seconds
    if retry_after_parse_error is not None:
        result["retry_after_parse_error"] = retry_after_parse_error
    if detail_map.get("http_status") is not None:
        result["http_status"] = detail_map.get("http_status")
    return result


def error_payload_from_cli_error(exc: CliError) -> dict[str, Any]:
    return {
        "type": exc.error_type,
        "message": exc.message,
        **classify_failure(exc.error_type, exc.message, details=exc.details),
    }
