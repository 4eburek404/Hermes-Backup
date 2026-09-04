from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


OFFER_GRAPH_SCHEMA_VERSION = "flight_offer_graph.v1"


@dataclass(frozen=True, slots=True)
class OfferGraph:
    edges: list[dict[str, Any]] = field(default_factory=list)
    offers: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    schema_version: str = OFFER_GRAPH_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "edges": deepcopy(self.edges),
            "offers": deepcopy(self.offers),
            "coverage": deepcopy(self.coverage),
        }


__all__ = [
    "OFFER_GRAPH_SCHEMA_VERSION",
    "OfferGraph",
]
