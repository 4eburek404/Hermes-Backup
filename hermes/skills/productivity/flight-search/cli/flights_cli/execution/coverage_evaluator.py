from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CoverageEvaluation:
    continue_search: bool
    reasons: list[str]
    searched_gateways: int
    viable_gateways: int
    failed_gateways: int
    not_searched_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "continue_search": self.continue_search,
            "reasons": list(self.reasons),
            "searched_gateways": self.searched_gateways,
            "viable_gateways": self.viable_gateways,
            "failed_gateways": self.failed_gateways,
            "not_searched_budget": self.not_searched_budget,
        }


@dataclass(frozen=True, slots=True)
class CoverageEvaluatorOptions:
    min_gateways_searched: int
    min_viable_gateways: int = 1
    planned_probes_terminal: bool = True


class CoverageEvaluator:
    def __init__(self, options: CoverageEvaluatorOptions) -> None:
        self.options = options

    def evaluate(
        self,
        gateways: list[dict[str, Any]],
        *,
        total_gateway_count: int,
        batch_index: int,
        max_batches: int,
    ) -> CoverageEvaluation:
        searched = [gateway for gateway in gateways if gateway.get("searched")]
        viable = [gateway for gateway in searched if gateway.get("viable")]
        failed = [gateway for gateway in searched if gateway.get("provider_failures")]
        searched_count = len(searched)
        viable_count = len(viable)
        failed_count = len(failed)
        not_searched_budget = max(0, int(total_gateway_count) - searched_count)
        reasons: list[str] = []

        if not self.options.planned_probes_terminal:
            reasons.append("planned_probes_not_terminal")
            return CoverageEvaluation(
                continue_search=not self._max_batches_reached(batch_index, max_batches),
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )
        reasons.append("planned_probes_terminal")

        blocking_provider_failure = failed_count > 0 and viable_count == 0
        if blocking_provider_failure:
            reasons.append("blocking_provider_failure_without_viable_gateway")

        if viable_count >= max(1, int(self.options.min_viable_gateways)):
            reasons.extend(
                [
                    "viable_gateway_found",
                    "minimum_viable_gateways_reached",
                ]
            )
            return CoverageEvaluation(
                continue_search=False,
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )

        if self._max_batches_reached(batch_index, max_batches):
            reasons.append("max_batches_reached")
            if searched_count >= max(0, int(self.options.min_gateways_searched)):
                reasons.append("minimum_gateways_searched_reached")
            return CoverageEvaluation(
                continue_search=False,
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )

        if searched_count >= max(0, int(self.options.min_gateways_searched)):
            reasons.append("minimum_gateways_searched_reached")
            return CoverageEvaluation(
                continue_search=False,
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )

        reasons.extend(["no_viable_gateway_yet", "gateway_probe_budget_remaining"])
        return CoverageEvaluation(
            continue_search=True,
            reasons=reasons,
            searched_gateways=searched_count,
            viable_gateways=viable_count,
            failed_gateways=failed_count,
            not_searched_budget=not_searched_budget,
        )

    @staticmethod
    def _max_batches_reached(batch_index: int, max_batches: int) -> bool:
        return int(max_batches) <= 0 or int(batch_index) >= int(max_batches)


def evaluate_graph_coverage_controls(
    plan: dict[str, Any],
    offer_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for control in plan.get("coverage_controls") or []:
        if not isinstance(control, dict) or control.get("type") != "city_pair_direct":
            continue
        graph_control = _graph_direct_control(
            {
                "direction": str(control.get("direction") or "outbound"),
                "origin": str(control.get("origin") or "").upper(),
                "destination": str(control.get("destination") or "").upper(),
                "date": str(control.get("date") or ""),
                "only_carriers": list(control.get("only_carriers") or []),
            },
            offer_graph,
        )
        if graph_control is None:
            continue
        graph_control["type"] = control.get("type")
        graph_control["negative_evidence"] = control.get("negative_evidence")
        graph_control["source_type"] = "graph_derived_policy_control"
        graph_control["control_policy"] = "coverage_controls"
        controls.append(graph_control)
    return controls


def _graph_direct_control(
    query: dict[str, Any], offer_graph: dict[str, Any]
) -> dict[str, Any] | None:
    origin = str(query.get("origin") or "").upper()
    destination = str(query.get("destination") or "").upper()
    direction = str(query.get("direction") or "")
    date_text = str(query.get("date") or "")
    carriers = [str(code).upper() for code in query.get("only_carriers") or []]
    edges_by_id = {
        str(edge.get("id") or ""): edge
        for edge in offer_graph.get("edges") or []
        if isinstance(edge, dict)
    }
    matches: list[dict[str, Any]] = []
    source_providers: set[str] = set()
    for offer in offer_graph.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        route = [str(code).upper() for code in offer.get("route") or [] if code]
        if len(route) != 2 or route[0] != origin or route[-1] != destination:
            continue
        if direction and str(offer.get("direction") or direction) != direction:
            continue
        edge_ids = [str(edge_id) for edge_id in offer.get("edge_ids") or []]
        edges = [edges_by_id[edge_id] for edge_id in edge_ids if edge_id in edges_by_id]
        if date_text and not _offer_matches_departure_date(edges, date_text):
            continue
        if carriers and not all(
            _edge_matches_carriers(edge, carriers) for edge in edges
        ):
            continue
        provider = str(offer.get("provider") or "").lower()
        if provider:
            source_providers.add(provider)
        matches.append(
            {
                "id": offer.get("id"),
                "source_type": offer.get("source_type"),
                "provider": offer.get("provider"),
                "route": route,
                "price": offer.get("price"),
                "currency": offer.get("currency"),
            }
        )
    if not matches:
        return None
    return {
        "direction": direction,
        "origin": origin,
        "destination": destination,
        "date": date_text,
        "status": "graph_derived",
        "provider": "graph",
        "filters": {"direct_only": True, "only_carriers": carriers},
        "offer_count": len(matches),
        "raw_offer_count": len(matches),
        "cache_status": "graph",
        "top_offers": matches[:1],
        "source_providers": sorted(source_providers),
        "graph_derived": True,
    }


def _offer_matches_departure_date(edges: list[dict[str, Any]], date_text: str) -> bool:
    if not edges:
        return True
    departure_at = str(edges[0].get("departure_at") or "")
    return not departure_at or departure_at.startswith(date_text)


def _edge_matches_carriers(edge: dict[str, Any], carriers: list[str]) -> bool:
    values = {
        str(edge.get(name) or "").upper()
        for name in ("carrier", "marketing_carrier", "operating_carrier")
        if edge.get(name)
    }
    flight_number = str(edge.get("flight_number") or "").upper()
    if len(flight_number) >= 2:
        values.add(flight_number[:2])
    return bool(values & set(carriers))
