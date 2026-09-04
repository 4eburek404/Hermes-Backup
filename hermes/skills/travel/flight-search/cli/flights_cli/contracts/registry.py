from __future__ import annotations

from types import MappingProxyType
from typing import Any

# Публичных контрактов два: вход и ответ. У них есть путь в конверте, потому
# что их читает агент.
#
# План и граф предложений — внутренние инварианты. Публичного пути у них нет:
# `data.plan` и `data.decision` исчезли вместе с диагностической трассой, и
# схемы держатся здесь только затем, чтобы тесты могли проверить форму того,
# что пайплайн передаёт сам себе.
_CURRENT_CONTRACTS: dict[str, dict[str, str]] = {
    "search_request": {
        "schema_version": "flight_search_request.v1",
        "schema_resource": "flight_search_request.v1.schema.json",
        "status": "current_public_input",
    },
    "search_result": {
        "schema_version": "flight_search_result.v1",
        "schema_resource": "flight_search_result.v1.schema.json",
        "public_path": "data",
        "canonical_text_path": "data.rendered_text",
        "status": "current_public_contract",
    },
    "search_plan": {
        "schema_version": "flight_search_plan.v6",
        "schema_resource": "flight_search_plan.v6.schema.json",
        "status": "internal_invariant",
    },
    "offer_graph": {
        "schema_version": "flight_offer_graph.v1",
        "schema_resource": "flight_offer_graph.v1.schema.json",
        "status": "internal_invariant",
    },
}

CURRENT_CONTRACTS = MappingProxyType(_CURRENT_CONTRACTS)


def current_contract(name: str) -> dict[str, Any]:
    try:
        return dict(CURRENT_CONTRACTS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown flight-search contract: {name}") from exc
