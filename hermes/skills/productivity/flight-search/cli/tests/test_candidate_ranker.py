from __future__ import annotations

import unittest

from flights_cli.domain.vocabulary import RouteFamily
from flights_cli.pipeline.candidate_ranker import (
    build_decision_frontier,
    rank_mixed_candidates,
)


def segment(
    origin: str,
    destination: str,
    *,
    depart: str | None = None,
    arrive: str | None = None,
    **extra: str,
) -> dict[str, str]:
    item = {"origin": origin, "destination": destination}
    if depart:
        item["departure_at"] = depart
    if arrive:
        item["arrival_at"] = arrive
    item.update(extra)
    return item


def candidate(
    candidate_id: str,
    *,
    source_type: str,
    price: int,
    ticketing_model: str,
    segments: list[dict[str, str]],
    covers_requested_trip: bool = True,
    connection_risk_score: int = 0,
    elapsed_min: int = 600,
    gateway: str | None = None,
) -> dict:
    return {
        "id": candidate_id,
        "source_type": source_type,
        "provider": "kupibilet" if source_type == "provider_full_route" else None,
        "source_providers": ["kupibilet"],
        "gateway": gateway
        if gateway is not None
        else ("IST" if source_type == "gateway_separate_ticket" else None),
        "covers_requested_trip": covers_requested_trip,
        "journey_scope": "one_way",
        "price": price,
        "currency": "RUB",
        "price_basis": "provider_offer_price"
        if source_type == "provider_full_route"
        else "summed_live_leg_prices",
        "ticketing_model": ticketing_model,
        "detail_status": "full",
        "journeys": [{"direction": "outbound", "segments": segments}],
        "warnings": [],
        "elapsed_min": elapsed_min,
        "connection_risk_score": connection_risk_score,
    }


class CandidateRankerTests(unittest.TestCase):
    def test_gateway_lower_price_does_not_beat_provider_full_route(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        gateway = candidate(
            "gateway",
            source_type="gateway_separate_ticket",
            price=30000,
            ticketing_model="separate_ticket_sum",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )

        ranking = rank_mixed_candidates({"candidates": [gateway, provider]})

        self.assertEqual(
            [item["id"] for item in ranking["ranked_candidates"]],
            ["provider", "gateway"],
        )
        self.assertGreater(
            ranking["ranked_candidates"][1]["rank_components"][
                "source_confidence_penalty"
            ],
            ranking["ranked_candidates"][0]["rank_components"][
                "source_confidence_penalty"
            ],
        )
        self.assertIn(
            "separate_ticket_ranked_after_provider_route_evidence",
            ranking["ranked_candidates"][1]["ranking_reasons"],
        )

    def test_provider_full_route_does_not_claim_single_pnr_without_proof(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="single_pnr",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )

        ranking = rank_mixed_candidates({"candidates": [provider]})

        ranked = ranking["ranked_candidates"][0]
        self.assertEqual(ranked["ticketing_model"], "provider_order_unverified")
        self.assertIn("provider_ticketing_protection_unverified", ranked["warnings"])
        self.assertIn(
            "provider_ticketing_protection_unverified",
            ranked["ranking_reasons"],
        )

    def test_direct_inventory_provider_and_gateway_are_all_visible(self) -> None:
        direct = candidate(
            "direct",
            source_type=RouteFamily.DIRECT_INVENTORY,
            price=70000,
            ticketing_model="unknown",
            segments=[segment("SVX", "AMS")],
        )
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        gateway = candidate(
            "gateway",
            source_type="gateway_separate_ticket",
            price=30000,
            ticketing_model="separate_ticket_sum",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )

        ranking = rank_mixed_candidates(
            {"candidates": [gateway, provider, direct]},
        )

        self.assertEqual(
            [item["id"] for item in ranking["ranked_candidates"]],
            ["direct", "provider", "gateway"],
        )
        self.assertEqual(ranking["coverage"]["candidate_count"], 3)

    def test_legacy_assembled_candidate_is_ranked_but_not_preferred(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        legacy = {
            "id": "legacy",
            "price": 25000,
            "currency": "RUB",
            "journeys": [
                {"direction": "outbound", "segments": [segment("SVX", "AMS")]}
            ],
        }

        ranking = rank_mixed_candidates(
            {"candidates": [provider]},
            legacy_candidates=[legacy],
        )

        self.assertEqual(
            [item["id"] for item in ranking["ranked_candidates"]],
            ["provider", "legacy"],
        )
        self.assertEqual(
            ranking["ranked_candidates"][1]["source_type"],
            "assembled_separate_ticket",
        )

    def test_impossible_connection_and_connection_limit_are_penalized(self) -> None:
        normal = candidate(
            "normal",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        impossible = candidate(
            "impossible",
            source_type="provider_full_route",
            price=40000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment("SVX", "IST"),
                segment("IST", "BEG"),
                segment("BEG", "AMS"),
                segment("AMS", "LHR"),
            ],
        )
        impossible["connection_status"] = "impossible"

        ranking = rank_mixed_candidates(
            {"candidates": [impossible, normal]},
            max_connections_per_journey=2,
        )

        self.assertEqual(
            [item["id"] for item in ranking["ranked_candidates"]],
            ["normal", "impossible"],
        )
        self.assertEqual(
            ranking["ranked_candidates"][1]["rank_components"][
                "rejected_or_impossible_connection"
            ],
            1,
        )
        self.assertEqual(
            ranking["ranked_candidates"][1]["rank_components"][
                "max_connections_per_journey"
            ],
            1,
        )

    def test_frontier_keeps_best_viable_option_without_raw_diagnostics(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [provider]})
        )

        self.assertEqual(frontier["schema_version"], "flight_decision_frontier.v1")
        self.assertEqual(frontier["options"][0]["id"], "provider")
        self.assertEqual(frontier["options"][0]["selection_reasons"], ["best_viable"])
        self.assertNotIn("rank_key", frontier["options"][0])
        self.assertNotIn("rank_components", frontier["options"][0])
        self.assertNotIn("ranking_reasons", frontier["options"][0])

    def test_frontier_keeps_cheapest_materially_different_option(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=60000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        gateway = candidate(
            "gateway",
            source_type="gateway_separate_ticket",
            price=30000,
            ticketing_model="separate_ticket_sum",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [gateway, provider]})
        )

        by_id = {option["id"]: option for option in frontier["options"]}
        self.assertIn("provider", by_id)
        self.assertIn("gateway", by_id)
        self.assertIn("cheapest_acceptable", by_id["gateway"]["selection_reasons"])

    def test_frontier_keeps_fastest_materially_different_option(self) -> None:
        cheap = candidate(
            "cheap",
            source_type="provider_full_route",
            price=45000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
            elapsed_min=720,
        )
        fast = candidate(
            "fast",
            source_type="provider_full_route",
            price=80000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
            elapsed_min=360,
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [fast, cheap]})
        )

        by_id = {option["id"]: option for option in frontier["options"]}
        self.assertEqual(frontier["options"][0]["id"], "cheap")
        self.assertIn("fast", by_id)
        self.assertIn("fastest_acceptable", by_id["fast"]["selection_reasons"])

    def test_frontier_keeps_safer_ticketing_and_direct_controls(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=40000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        direct = candidate(
            "direct",
            source_type=RouteFamily.DIRECT_INVENTORY,
            price=90000,
            ticketing_model="unknown",
            segments=[segment("SVX", "AMS")],
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [provider, direct]})
        )

        by_id = {option["id"]: option for option in frontier["options"]}
        self.assertIn("direct", by_id)
        self.assertIn("best_viable", by_id["direct"]["selection_reasons"])
        self.assertIn("safer_ticketing", by_id["direct"]["selection_reasons"])
        self.assertIn("direct_nonstop_control", by_id["direct"]["selection_reasons"])

    def test_frontier_keeps_significant_gateway_alternatives(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        ist = candidate(
            "gateway-ist",
            source_type="gateway_separate_ticket",
            price=48000,
            ticketing_model="separate_ticket_sum",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
            gateway="IST",
        )
        dxb = candidate(
            "gateway-dxb",
            source_type="gateway_separate_ticket",
            price=52000,
            ticketing_model="separate_ticket_sum",
            segments=[segment("SVX", "DXB"), segment("DXB", "AMS")],
            gateway="DXB",
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [dxb, ist, provider]})
        )

        by_id = {option["id"]: option for option in frontier["options"]}
        self.assertIn("gateway-ist", by_id)
        self.assertIn("gateway-dxb", by_id)
        self.assertIn(
            "significant_gateway_alternative",
            by_id["gateway-ist"]["selection_reasons"],
        )
        self.assertIn(
            "significant_gateway_alternative",
            by_id["gateway-dxb"]["selection_reasons"],
        )

    def test_frontier_coverage_summary_counts_representatives(self) -> None:
        provider = candidate(
            "provider",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        impossible = candidate(
            "impossible",
            source_type="provider_full_route",
            price=10000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
            covers_requested_trip=False,
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [impossible, provider]})
        )

        summary = frontier["coverage_summary"]
        self.assertEqual(summary["candidate_count"], 2)
        self.assertEqual(summary["acceptable_count"], 1)
        self.assertEqual(summary["selected_count"], 1)
        self.assertEqual(summary["selection_roles"], ["best_viable"])

    def test_invalid_chronology_is_rejected_before_frontier(self) -> None:
        viable = candidate(
            "viable",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T18:55:00+02:00",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T21:00:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                ),
            ],
        )
        impossible = candidate(
            "impossible",
            source_type="provider_full_route",
            price=10000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T18:55:00+02:00",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T18:00:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                ),
            ],
        )

        ranking = rank_mixed_candidates({"candidates": [impossible, viable]})
        ranked = {item["id"]: item for item in ranking["ranked_candidates"]}

        self.assertEqual(ranking["ranked_candidates"][0]["id"], "viable")
        self.assertEqual(
            ranked["impossible"]["rank_components"][
                "rejected_or_impossible_connection"
            ],
            1,
        )
        self.assertEqual(ranked["impossible"]["candidate_status"], "impossible")
        self.assertEqual(
            ranked["impossible"]["chronology_violations"][0]["reason"],
            "invalid_time_order",
        )
        self.assertIn("invalid_time_order", ranked["impossible"]["ranking_reasons"])

        frontier = build_decision_frontier(ranking)
        self.assertEqual([item["id"] for item in frontier["options"]], ["viable"])

    def test_provider_validated_short_connection_is_not_mct_rejected(self) -> None:
        provider = candidate(
            "provider-short-mct",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T18:55:00+02:00",
                    offer_id="provider-offer",
                    ticketing_boundary="provider_protected_full_route",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T19:45:00+02:00",
                    arrive="2026-07-09T23:55:00+03:00",
                    offer_id="provider-offer",
                    ticketing_boundary="provider_protected_full_route",
                ),
            ],
        )

        ranking = rank_mixed_candidates(
            {"candidates": [provider]},
            min_same_airport_connection_min=120,
            min_cross_airport_connection_min=300,
        )

        ranked = ranking["ranked_candidates"][0]
        self.assertEqual(
            ranked["rank_components"]["rejected_or_impossible_connection"], 0
        )
        self.assertNotIn("mct_violations", ranked)
        self.assertEqual(
            build_decision_frontier(ranking)["options"][0]["id"], provider["id"]
        )

    def test_cross_ticket_short_connection_is_rejected_before_frontier(self) -> None:
        viable = candidate(
            "viable",
            source_type="gateway_separate_ticket",
            price=50000,
            ticketing_model="separate_ticket_sum",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T18:55:00+02:00",
                    offer_id="leg-1",
                    ticketing_boundary="separate_ticket_leg",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T21:00:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                    offer_id="leg-2",
                    ticketing_boundary="separate_ticket_leg",
                ),
            ],
        )
        short = candidate(
            "short",
            source_type="gateway_separate_ticket",
            price=10000,
            ticketing_model="separate_ticket_sum",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T18:55:00+02:00",
                    offer_id="leg-1",
                    ticketing_boundary="separate_ticket_leg",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T19:45:00+02:00",
                    arrive="2026-07-09T23:55:00+03:00",
                    offer_id="leg-2",
                    ticketing_boundary="separate_ticket_leg",
                ),
            ],
        )

        ranking = rank_mixed_candidates(
            {"candidates": [short, viable]},
            min_same_airport_connection_min=120,
            min_cross_airport_connection_min=300,
        )
        ranked = {item["id"]: item for item in ranking["ranked_candidates"]}

        self.assertEqual(ranking["ranked_candidates"][0]["id"], "viable")
        self.assertEqual(ranked["short"]["candidate_status"], "impossible")
        self.assertEqual(
            ranked["short"]["mct_violations"][0]["reason"],
            "cross_ticket_mct_violation",
        )
        self.assertIn("cross_ticket_mct_violation", ranked["short"]["ranking_reasons"])
        self.assertEqual(
            [item["id"] for item in build_decision_frontier(ranking)["options"]],
            ["viable"],
        )

    def test_request_constraints_reject_before_frontier(self) -> None:
        viable = candidate(
            "viable",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T18:55:00+02:00",
                    carrier="KLM Royal Dutch Airlines",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T21:00:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                    carrier="KLM Royal Dutch Airlines",
                ),
            ],
        )
        missing_airport = candidate(
            "missing-airport",
            source_type="provider_full_route",
            price=10000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "IST",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                    carrier="KLM Royal Dutch Airlines",
                )
            ],
        )
        early = candidate(
            "early",
            source_type="provider_full_route",
            price=11000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T14:20:00+02:00",
                    arrive="2026-07-09T15:55:00+02:00",
                    carrier="KLM Royal Dutch Airlines",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T21:00:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                    carrier="KLM Royal Dutch Airlines",
                ),
            ],
        )
        wrong_carrier = candidate(
            "wrong-carrier",
            source_type="provider_full_route",
            price=12000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "AMS",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T18:55:00+02:00",
                    carrier="Air France",
                ),
                segment(
                    "AMS",
                    "IST",
                    depart="2026-07-09T21:00:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                    carrier="Air France",
                ),
            ],
        )

        ranking = rank_mixed_candidates(
            {"candidates": [missing_airport, early, wrong_carrier, viable]},
            constraints={
                "must_include_airports": ["AMS"],
                "first_departure_after": "15:00",
                "only_carriers": ["KL"],
            },
        )
        ranked = {item["id"]: item for item in ranking["ranked_candidates"]}

        self.assertEqual(ranking["ranked_candidates"][0]["id"], "viable")
        self.assertEqual(
            ranked["viable"]["rank_components"]["hard_constraint_violation"], 0
        )
        self.assertEqual(
            ranked["missing-airport"]["hard_constraint_violations"][0]["reason"],
            "missing_required_airport",
        )
        self.assertEqual(
            ranked["early"]["hard_constraint_violations"][0]["reason"],
            "first_departure_before_requested_time",
        )
        self.assertEqual(
            ranked["wrong-carrier"]["hard_constraint_violations"][0]["reason"],
            "carrier_not_allowed",
        )

        frontier = build_decision_frontier(ranking)
        self.assertEqual([item["id"] for item in frontier["options"]], ["viable"])

    def test_preferred_carrier_is_soft_rank_signal(self) -> None:
        preferred = candidate(
            "preferred",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("IST", "CDG", carrier="Air France")],
        )
        other = candidate(
            "other",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("IST", "CDG", carrier="Turkish Airlines")],
        )

        ranking = rank_mixed_candidates(
            {"candidates": [other, preferred]},
            constraints={"preferred_carriers": ["AF"]},
        )

        self.assertEqual(
            [item["id"] for item in ranking["ranked_candidates"]],
            ["preferred", "other"],
        )
        self.assertEqual(
            ranking["ranked_candidates"][0]["rank_components"][
                "preferred_carrier_miss"
            ],
            0,
        )
        self.assertEqual(
            ranking["ranked_candidates"][1]["rank_components"][
                "preferred_carrier_miss"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
