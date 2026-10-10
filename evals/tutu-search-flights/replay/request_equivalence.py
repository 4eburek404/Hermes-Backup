"""Conservative matching of recorded Tutu searches to saved responses."""
from __future__ import annotations

import json
from typing import Any


def equivalent_arguments(actual: Any, expected: Any, payload: Any) -> bool:
    """Allow only known non-semantic/default fields; keep search constraints exact."""
    if not isinstance(actual, dict) or not isinstance(expected, dict) or not isinstance(payload, dict):
        return False
    if any(actual.get(key) != value for key, value in expected.items()):
        return False
    meta_value = payload.get("meta")
    meta: dict[str, Any] = meta_value if isinstance(meta_value, dict) else {}
    pricing_value = meta.get("pricing")
    pricing: dict[str, Any] = pricing_value if isinstance(pricing_value, dict) else {}
    passengers_value = pricing.get("passengers")
    passengers: dict[str, Any] = passengers_value if isinstance(passengers_value, dict) else {}
    for key, value in actual.items():
        if key in expected:
            continue
        if key == "adults" and "adults" not in expected and value == passengers.get("full", 1):
            continue
        if key == "children" and "children" not in expected and value == passengers.get("child", 0):
            continue
        if key == "page" and value == meta.get("page", 1):
            continue
        if key == "sort" and value == meta.get("sort"):
            continue
        if key == "view" and value == "full":
            continue
        return False
    return True


def payload_from_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(fixture["response"]["envelope"]["result"]["content"][0]["text"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
