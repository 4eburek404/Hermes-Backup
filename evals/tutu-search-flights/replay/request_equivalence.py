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
    # Values below are the recorded search_avia schema defaults in
    # fixtures/meta/tools-list.json. Do not infer defaults from the response:
    # a response can describe a different passenger or pagination scope.
    defaults = {
        "adults": 1,
        "children": 0,
        "page": 1,
        "sort": "price_asc",
        "view": "compact",
    }
    for key, value in actual.items():
        if key in expected:
            continue
        if key in defaults and value == defaults[key]:
            continue
        return False
    return True


def payload_from_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(fixture["response"]["envelope"]["result"]["content"][0]["text"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
