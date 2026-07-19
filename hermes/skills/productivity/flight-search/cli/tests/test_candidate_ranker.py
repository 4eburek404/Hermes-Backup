from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from itertools import permutations
from unittest.mock import patch

from flights_cli.domain.vocabulary import RouteFamily
from flights_cli.pipeline.candidate_ranker import (
    build_decision_frontier,
    rank_mixed_candidates,
)
from flights_cli.pipeline.candidate_scoring import score_validated_candidates
from flights_cli.pipeline.candidate_validation import (
    validate_candidate_envelope as validate_candidates_impl,
)
from flights_cli.pipeline.decision_scorer import DecisionScorer, DecisionScorerOptions


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
    direction: str = "outbound",
    journey_scope: str = "one_way",
) -> dict:
    normalized_segments = deepcopy(segments)
    base = datetime(
        2026,
        7,
        8 if direction == "return" else 1,
        8,
        tzinfo=timezone.utc,
    )
    for index, item in enumerate(normalized_segments):
        if item.get("departure_at") or item.get("arrival_at"):
            continue
        departure = base + timedelta(hours=index * 4)
        item["departure_at"] = departure.isoformat()
        item["arrival_at"] = (departure + timedelta(hours=2)).isoformat()
    return {
        "id": candidate_id,
        "source_type": source_type,
        "provider": "kupibilet" if source_type == "provider_full_route" else None,
        "source_providers": ["kupibilet"],
        "gateway": gateway
        if gateway is not None
        else ("IST" if source_type == "gateway_separate_ticket" else None),
        "covers_requested_trip": covers_requested_trip,
        "journey_scope": journey_scope,
        "price": price,
        "currency": "RUB",
        "price_basis": "provider_offer_price"
        if source_type == "provider_full_route"
        else "summed_live_leg_prices",
        "ticketing_model": ticketing_model,
        "detail_status": "full",
        "journeys": [{"direction": direction, "segments": normalized_segments}],
        "warnings": [],
        "elapsed_min": elapsed_min,
        "connection_risk_score": connection_risk_score,
    }


def outbound_via_ist(
    candidate_id: str,
    *,
    price: int,
    layover_min: int,
) -> dict:
    first_departure = datetime(2026, 9, 20, 5, tzinfo=timezone.utc)
    first_arrival = first_departure + timedelta(hours=3)
    second_departure = first_arrival + timedelta(minutes=layover_min)
    second_arrival = second_departure + timedelta(hours=3)
    return candidate(
        candidate_id,
        source_type="provider_full_route",
        price=price,
        ticketing_model="provider_order_unverified",
        segments=[
            segment(
                "SVX",
                "IST",
                depart=first_departure.isoformat(),
                arrive=first_arrival.isoformat(),
            ),
            segment(
                "IST",
                "FRA",
                depart=second_departure.isoformat(),
                arrive=second_arrival.isoformat(),
            ),
        ],
    )


def return_from_fra(candidate_id: str, *, price: int, slot: int = 0) -> dict:
    departure = datetime(2026, 9, 30, 6, tzinfo=timezone.utc) + timedelta(
        minutes=30 * slot
    )
    return candidate(
        candidate_id,
        source_type="provider_full_route",
        price=price,
        ticketing_model="provider_order_unverified",
        segments=[
            segment(
                "FRA",
                "SVX",
                depart=departure.isoformat(),
                arrive=(departure + timedelta(hours=5)).isoformat(),
            )
        ],
        direction="return",
    )


class CandidateRankerTests(unittest.TestCase):
    def test_missing_arrival_time_is_authoritatively_invalid(self) -> None:
        malformed = candidate(
            "missing-arrival",
            source_type="provider_full_route",
            price=10_000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "SVX",
                    "LED",
                    depart="2026-08-01T08:00:00+05:00",
                )
            ],
        )

        ranking = rank_mixed_candidates({"candidates": [malformed]})
        ranked = ranking["ranked_candidates"][0]

        self.assertEqual(ranked["validation"]["status"], "invalid")
        self.assertIn("missing_segment_time", ranked["validation"]["blocking_reasons"])
        self.assertEqual(build_decision_frontier(ranking)["options"], [])

    def test_gateway_lower_price_can_beat_provider_full_route(self) -> None:
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
        self.assertLess(
            ranking["ranked_candidates"][0]["rank_components"][
                "source_confidence_penalty"
            ],
            ranking["ranked_candidates"][1]["rank_components"][
                "source_confidence_penalty"
            ],
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

    def test_explicit_self_transfer_ranks_as_higher_ticketing_risk(self) -> None:
        protected = candidate(
            "protected",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        self_transfer = candidate(
            "self-transfer",
            source_type="provider_full_route",
            price=30000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "AMS")],
        )
        self_transfer["self_transfer"] = True

        ranking = rank_mixed_candidates({"candidates": [self_transfer, protected]})

        by_id = {item["id"]: item for item in ranking["ranked_candidates"]}
        self.assertLess(
            by_id["protected"]["rank_components"]["ticketing_risk_tier"],
            by_id["self-transfer"]["rank_components"]["ticketing_risk_tier"],
        )
        frontier = build_decision_frontier(ranking)
        exposed = next(
            item for item in frontier["options"] if item["id"] == "self-transfer"
        )
        self.assertIs(exposed["self_transfer"], True)

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

    def test_max_connections_without_tier2_blocks_two_connection_candidate(
        self,
    ) -> None:
        two_connection = candidate(
            "two-connection",
            source_type="provider_full_route",
            price=30000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment("SVX", "IST"),
                segment("IST", "AMS"),
                segment("AMS", "CDG"),
            ],
        )

        scored = DecisionScorer(
            DecisionScorerOptions(
                max_connections_per_journey=1,
                preferred_connections=1,
            )
        ).score({"candidates": [two_connection]})
        ranked = scored["mixed_candidate_ranking"]["ranked_candidates"][0]

        self.assertEqual(ranked["rank_components"]["max_connections_per_journey"], 1)
        self.assertEqual(scored["decision_frontier"]["options"], [])

    def test_tier2_allows_two_connections_but_preferred_limit_demotes(
        self,
    ) -> None:
        one_connection = candidate(
            "one-connection",
            source_type="provider_full_route",
            price=50000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "CDG")],
        )
        two_connection = candidate(
            "two-connection",
            source_type="provider_full_route",
            price=30000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment("SVX", "IST"),
                segment("IST", "AMS"),
                segment("AMS", "CDG"),
            ],
        )

        scored = DecisionScorer(
            DecisionScorerOptions(
                max_connections_per_journey=2,
                preferred_connections=1,
            )
        ).score({"candidates": [two_connection, one_connection]})
        ranked = scored["mixed_candidate_ranking"]["ranked_candidates"]
        by_id = {item["id"]: item for item in ranked}
        frontier_ids = {item["id"] for item in scored["decision_frontier"]["options"]}

        self.assertEqual(
            [item["id"] for item in ranked],
            ["one-connection", "two-connection"],
        )
        self.assertEqual(
            by_id["two-connection"]["rank_components"]["max_connections_per_journey"],
            0,
        )
        self.assertEqual(
            by_id["two-connection"]["rank_components"][
                "preferred_connections_per_journey"
            ],
            1,
        )
        self.assertNotIn("two-connection", frontier_ids)

    def test_directional_connection_cap_does_not_reject_other_round_trip_direction(
        self,
    ) -> None:
        outbound = candidate(
            "outbound-one-stop",
            source_type="provider_full_route",
            price=20000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "SVO"), segment("SVO", "LED")],
            direction="outbound",
        )
        inbound = candidate(
            "return-two-stop",
            source_type="provider_full_route",
            price=22000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment("LED", "SVO"),
                segment("SVO", "KZN"),
                segment("KZN", "SVX"),
            ],
            direction="return",
        )

        scored = DecisionScorer(
            DecisionScorerOptions(
                round_trip=True,
                max_connections_per_journey=2,
                max_connections_per_direction={"outbound": 1},
                preferred_connections=1,
            )
        ).score({"candidates": [outbound, inbound]})
        pair_id = "round-trip-pair:outbound-one-stop:return-two-stop"
        ranked = {
            item["id"]: item
            for item in scored["mixed_candidate_ranking"]["ranked_candidates"]
        }
        frontier_ids = {item["id"] for item in scored["decision_frontier"]["options"]}

        self.assertEqual(
            ranked[pair_id]["rank_components"]["max_connections_per_journey"], 0
        )
        self.assertEqual(
            scored["mixed_candidate_ranking"]["coverage"][
                "max_connections_per_direction"
            ],
            {"outbound": 1},
        )
        self.assertIn(pair_id, frontier_ids)

    def test_zero_connection_limit_blocks_connected_candidate(self) -> None:
        one_connection = candidate(
            "one-connection",
            source_type="provider_full_route",
            price=30000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "IST"), segment("IST", "CDG")],
        )

        scored = DecisionScorer(
            DecisionScorerOptions(
                max_connections_per_journey=0,
                preferred_connections=0,
            )
        ).score({"candidates": [one_connection]})
        ranked = scored["mixed_candidate_ranking"]["ranked_candidates"][0]

        self.assertEqual(ranked["rank_components"]["max_connections_per_journey"], 1)
        self.assertEqual(
            ranked["rank_components"]["preferred_connections_per_journey"], 1
        )
        self.assertEqual(scored["decision_frontier"]["options"], [])

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
        self.assertIn("best_viable", by_id["provider"]["selection_reasons"])

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
        self.assertEqual(frontier["options"][0]["id"], "fast")
        self.assertIn("fast", by_id)
        self.assertIn("cheap", by_id)
        self.assertIn("cheapest_selected", by_id["cheap"]["selection_reasons"])

    def test_frontier_keeps_safer_ticketing_and_direct_inventory(self) -> None:
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
        self.assertEqual(by_id["direct"]["selection_reasons"], ["best_viable"])
        self.assertEqual(
            frontier["coverage_summary"]["direct_option_count_by_direction"],
            {"outbound": 1},
        )

    def test_direct_inventory_respects_shared_output_limit_after_merge(self) -> None:
        direct = [
            candidate(
                f"direct-{index}",
                source_type=RouteFamily.DIRECT_INVENTORY,
                price=10000 + index,
                ticketing_model="provider_order_unverified",
                segments=[segment("SVX", "AMS")],
            )
            for index in range(3)
        ]

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": list(reversed(direct))}),
            max_options=2,
        )

        self.assertEqual(
            [option["id"] for option in frontier["options"]],
            ["direct-0", "direct-1"],
        )
        self.assertEqual(frontier["coverage_summary"]["selected_count"], 2)
        self.assertEqual(
            frontier["coverage_summary"]["suppressed_by_output_limit_count"], 1
        )

    def test_direct_options_bypass_gateway_pareto_and_diversity(self) -> None:
        better = candidate(
            "direct-better",
            source_type=RouteFamily.DIRECT_INVENTORY,
            price=20_000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "AMS", carrier="KL")],
            elapsed_min=240,
        )
        dominated = candidate(
            "direct-dominated",
            source_type=RouteFamily.DIRECT_INVENTORY,
            price=30_000,
            ticketing_model="provider_order_unverified",
            segments=[segment("SVX", "AMS", carrier="KL")],
            elapsed_min=300,
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [dominated, better]})
        )

        self.assertEqual(
            [option["id"] for option in frontier["options"]],
            ["direct-better", "direct-dominated"],
        )

    def test_frontier_keeps_gateway_alternatives(self) -> None:
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
            "carrier_diversity",
            by_id["gateway-ist"]["selection_reasons"],
        )
        self.assertIn(
            "gateway_alternative",
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

    def test_direct_output_limit_reports_suppressed_count(self) -> None:
        candidates = [
            candidate(
                f"direct-{index}",
                source_type="direct_inventory",
                price=50_000 + index,
                ticketing_model="provider_order_unverified",
                segments=[segment("SVX", "CDG")],
            )
            for index in range(3)
        ]

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": candidates}),
            max_options=2,
        )

        self.assertEqual(
            [option["id"] for option in frontier["options"]],
            ["direct-0", "direct-1"],
        )
        self.assertEqual(frontier["coverage_summary"]["selected_count"], 2)
        self.assertEqual(
            frontier["coverage_summary"]["suppressed_by_output_limit_count"], 1
        )

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

    def test_segment_arrival_before_departure_is_rejected_before_frontier(self) -> None:
        impossible = candidate(
            "impossible-segment",
            source_type="provider_full_route",
            price=10000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "IST",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-09T16:20:00+02:00",
                )
            ],
        )

        ranking = rank_mixed_candidates({"candidates": [impossible]})
        ranked = ranking["ranked_candidates"][0]

        self.assertEqual(ranked["candidate_status"], "impossible")
        self.assertEqual(
            ranked["chronology_violations"][0]["reason"],
            "segment_arrival_before_departure",
        )
        self.assertEqual(build_decision_frontier(ranking)["options"], [])

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

    def test_decision_scorer_keeps_round_trip_ticketing_models_distinct(
        self,
    ) -> None:
        provider_round_trip = {
            "id": "provider-round-trip",
            "source_type": "provider_full_route",
            "provider": "tutu",
            "source_providers": ["tutu"],
            "covers_requested_trip": True,
            "journey_scope": "round_trip",
            "price": 70000,
            "currency": "RUB",
            "price_basis": "provider_offer_price",
            "ticketing_model": "round_trip_single_ticket",
            "detail_status": "full",
            "journeys": [
                {
                    "direction": "outbound",
                    "segments": [
                        segment(
                            "NTE",
                            "IST",
                            depart="2026-07-09T17:20:00+02:00",
                            arrive="2026-07-10T01:20:00+03:00",
                        )
                    ],
                },
                {
                    "direction": "return",
                    "segments": [
                        segment(
                            "IST",
                            "NTE",
                            depart="2026-07-15T10:00:00+03:00",
                            arrive="2026-07-15T14:00:00+02:00",
                        )
                    ],
                },
            ],
            "warnings": [],
        }
        outbound = candidate(
            "outbound-one-way",
            source_type="provider_full_route",
            price=45000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "IST",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                )
            ],
        )
        inbound = candidate(
            "return-one-way",
            source_type="provider_full_route",
            price=45000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "IST",
                    "NTE",
                    depart="2026-07-15T10:00:00+03:00",
                    arrive="2026-07-15T14:00:00+02:00",
                )
            ],
            direction="return",
        )

        scored = DecisionScorer(DecisionScorerOptions(round_trip=True)).score(
            {"candidates": [outbound, inbound, provider_round_trip]}
        )
        ranked = scored["mixed_candidate_ranking"]["ranked_candidates"]
        by_id = {item["id"]: item for item in ranked}
        pair_id = "round-trip-pair:outbound-one-way:return-one-way"

        self.assertEqual(scored["scorer"]["name"], "DecisionScorer")
        self.assertEqual(ranked[0]["id"], "provider-round-trip")
        self.assertEqual(
            by_id["provider-round-trip"]["journey_pairing_model"],
            "round_trip_single_ticket",
        )
        self.assertEqual(by_id[pair_id]["ticketing_model"], "one_way_sum")
        self.assertEqual(by_id[pair_id]["journey_pairing_model"], "one_way_sum")
        self.assertEqual(
            scored["scorer"]["round_trip_pairing"]["one_way_pair_candidate_count"],
            1,
        )

    def test_round_trip_pair_pool_is_scored_only_in_the_final_candidate_pass(
        self,
    ) -> None:
        outbound = [
            outbound_via_ist("outbound-a", price=100, layover_min=240),
            outbound_via_ist("outbound-b", price=200, layover_min=300),
        ]
        inbound = [
            return_from_fra("return-a", price=100),
            return_from_fra("return-b", price=200, slot=1),
        ]

        with (
            patch(
                "flights_cli.pipeline.decision_scorer.validate_candidate_envelope",
                wraps=validate_candidates_impl,
            ) as validation_pass,
            patch(
                "flights_cli.pipeline.decision_scorer.score_validated_candidates",
                wraps=score_validated_candidates,
            ) as final_score,
        ):
            DecisionScorer(
                DecisionScorerOptions(round_trip=True, max_round_trip_pairs=2)
            ).score({"candidates": [*outbound, *inbound]})

        self.assertEqual(validation_pass.call_count, 1)
        self.assertEqual(final_score.call_count, 1)
        expected_ids = {
            "round-trip-pair:outbound-a:return-a",
            "round-trip-pair:outbound-a:return-b",
            "round-trip-pair:outbound-b:return-a",
            "round-trip-pair:outbound-b:return-b",
        }
        validation_ids = {
            item["id"] for item in validation_pass.call_args.args[0]["candidates"]
        }
        final_ids = {item["id"] for item in final_score.call_args.args[0]["candidates"]}
        self.assertEqual(validation_ids, expected_ids)
        self.assertEqual(final_ids, expected_ids)

    def test_decision_scorer_keeps_provider_round_trip_price_atomic(self) -> None:
        provider_round_trip = {
            "id": "provider-round-trip",
            "source_type": "provider_full_route",
            "provider": "tutu",
            "source_providers": ["tutu"],
            "covers_requested_trip": True,
            "journey_scope": "round_trip",
            "price": 20441,
            "currency": "RUB",
            "price_basis": "provider_offer_price",
            "ticketing_model": "provider_order_unverified",
            "detail_status": "full",
            "journeys": [
                {
                    "direction": "outbound",
                    "segments": [
                        segment(
                            "SVX",
                            "LED",
                            depart="2026-09-05T19:00:00+05:00",
                            arrive="2026-09-05T19:55:00+03:00",
                        )
                    ],
                },
                {
                    "direction": "return",
                    "segments": [
                        segment(
                            "LED",
                            "SVX",
                            depart="2026-09-12T18:55:00+03:00",
                            arrive="2026-09-12T23:40:00+05:00",
                        )
                    ],
                },
            ],
            "warnings": [],
        }
        outbound = candidate(
            "outbound-one-way",
            source_type="provider_full_route",
            price=20441,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "SVX",
                    "LED",
                    depart="2026-09-05T19:00:00+05:00",
                    arrive="2026-09-05T19:55:00+03:00",
                )
            ],
        )
        inbound = candidate(
            "return-one-way",
            source_type="provider_full_route",
            price=20441,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "LED",
                    "SVX",
                    depart="2026-09-12T18:55:00+03:00",
                    arrive="2026-09-12T23:40:00+05:00",
                )
            ],
            direction="return",
        )

        scored = DecisionScorer(DecisionScorerOptions(round_trip=True)).score(
            {"candidates": [outbound, inbound, provider_round_trip]}
        )
        ranked = scored["mixed_candidate_ranking"]["ranked_candidates"]
        by_id = {item["id"]: item for item in ranked}

        self.assertEqual(ranked[0]["id"], "provider-round-trip")
        self.assertEqual(by_id["provider-round-trip"]["price"], 20441)
        self.assertEqual(
            by_id["provider-round-trip"]["journey_pairing_model"],
            "round_trip_provider_order_unverified",
        )
        self.assertEqual(
            by_id["round-trip-pair:outbound-one-way:return-one-way"]["price"],
            40882,
        )
        self.assertEqual(
            scored["scorer"]["round_trip_pairing"][
                "provider_round_trip_candidate_count"
            ],
            1,
        )

    def test_round_trip_pair_limit_applies_after_full_pool_ranking(self) -> None:
        outbound = [
            candidate(
                f"outbound-{index}",
                source_type="provider_full_route",
                price=price,
                ticketing_model="provider_order_unverified",
                segments=[segment("SVX", "IST")],
            )
            for index, price in enumerate((90_000, 80_000, 10_000))
        ]
        returns = [
            candidate(
                f"return-{index}",
                source_type="provider_full_route",
                price=price,
                ticketing_model="provider_order_unverified",
                segments=[segment("IST", "SVX")],
                direction="return",
            )
            for index, price in enumerate((20_000, 30_000, 40_000))
        ]

        scored = DecisionScorer(
            DecisionScorerOptions(
                round_trip=True,
                max_round_trip_pairs=2,
                max_options=10,
            )
        ).score({"candidates": [*outbound, *returns]})
        ranked_ids = [
            item["id"]
            for item in scored["mixed_candidate_ranking"]["ranked_candidates"]
        ]
        frontier_ids = [item["id"] for item in scored["decision_frontier"]["options"]]

        self.assertEqual(len(ranked_ids), 9)
        self.assertIn("round-trip-pair:outbound-0:return-2", ranked_ids)
        self.assertEqual(
            frontier_ids,
            [
                "round-trip-pair:outbound-2:return-0",
                "round-trip-pair:outbound-2:return-1",
            ],
        )
        self.assertEqual(
            scored["scorer"]["round_trip_pairing"]["one_way_pair_pool_count"],
            9,
        )
        self.assertEqual(
            scored["scorer"]["round_trip_pairing"]["one_way_pair_candidate_count"],
            2,
        )
        self.assertEqual(
            scored["scorer"]["round_trip_pairing"]["one_way_pair_eligible_count"],
            2,
        )
        self.assertEqual(
            scored["decision_frontier"]["coverage_summary"][
                "suppressed_by_round_trip_pair_limit_count"
            ],
            7,
        )

        output_limited = DecisionScorer(
            DecisionScorerOptions(
                round_trip=True,
                max_round_trip_pairs=2,
                max_options=1,
            )
        ).score({"candidates": [*outbound, *returns]})
        output_coverage = output_limited["decision_frontier"]["coverage_summary"]
        self.assertEqual(output_coverage["eligible_round_trip_pair_count"], 2)
        self.assertEqual(output_coverage["selected_count"], 1)
        self.assertEqual(
            output_coverage["suppressed_by_round_trip_pair_limit_count"],
            7,
        )
        self.assertEqual(output_coverage["suppressed_by_output_limit_count"], 1)

    def test_round_trip_pair_limit_keeps_valid_pair_after_cheapest_invalid_outbound(
        self,
    ) -> None:
        cheapest_invalid = outbound_via_ist(
            "outbound-cheapest-invalid",
            price=10_000,
            layover_min=2_220,
        )
        valid = outbound_via_ist(
            "outbound-valid",
            price=20_000,
            layover_min=240,
        )
        returns = [
            return_from_fra(
                f"return-{index:02d}",
                price=30_000 + index,
                slot=index,
            )
            for index in range(12)
        ]

        scored = DecisionScorer(
            DecisionScorerOptions(
                round_trip=True,
                max_layover_min=1_440,
                max_round_trip_pairs=12,
                max_options=12,
            )
        ).score({"candidates": [cheapest_invalid, valid, *returns]})
        ranked = {
            item["id"]: item
            for item in scored["mixed_candidate_ranking"]["ranked_candidates"]
        }
        invalid_pair_id = "round-trip-pair:outbound-cheapest-invalid:return-00"
        valid_pair_id = "round-trip-pair:outbound-valid:return-00"
        frontier_ids = [item["id"] for item in scored["decision_frontier"]["options"]]

        self.assertEqual(
            scored["scorer"]["round_trip_pairing"]["one_way_pair_pool_count"],
            24,
        )
        self.assertEqual(ranked[invalid_pair_id]["validation"]["status"], "invalid")
        self.assertEqual(
            ranked[invalid_pair_id]["connection_assessment"]["connections"][0][
                "actual_min"
            ],
            2_220,
        )
        self.assertEqual(ranked[valid_pair_id]["validation"]["status"], "valid")
        self.assertIn(valid_pair_id, frontier_ids)
        self.assertTrue(frontier_ids)
        self.assertTrue(
            all(":outbound-valid:" in candidate_id for candidate_id in frontier_ids)
        )

    def test_zero_round_trip_pair_limit_preserves_atomic_provider_offer(self) -> None:
        provider_round_trip = candidate(
            "provider-round-trip",
            source_type="provider_full_route",
            price=50_000,
            ticketing_model="round_trip_single_ticket",
            segments=[
                segment(
                    "SVX",
                    "FRA",
                    depart="2026-09-20T05:00:00+00:00",
                    arrive="2026-09-20T10:00:00+00:00",
                )
            ],
            journey_scope="round_trip",
        )
        provider_round_trip["journeys"].append(
            {
                "direction": "return",
                "segments": [
                    segment(
                        "FRA",
                        "SVX",
                        depart="2026-09-30T06:00:00+00:00",
                        arrive="2026-09-30T11:00:00+00:00",
                    )
                ],
            }
        )
        outbound = outbound_via_ist("outbound", price=10_000, layover_min=240)
        inbound = return_from_fra("return", price=20_000)

        scored = DecisionScorer(
            DecisionScorerOptions(
                round_trip=True,
                max_round_trip_pairs=0,
                max_options=10,
            )
        ).score({"candidates": [outbound, inbound, provider_round_trip]})
        ranked_ids = [
            item["id"]
            for item in scored["mixed_candidate_ranking"]["ranked_candidates"]
        ]
        frontier_ids = [item["id"] for item in scored["decision_frontier"]["options"]]

        self.assertEqual(ranked_ids, ["provider-round-trip"])
        self.assertEqual(frontier_ids, ["provider-round-trip"])
        self.assertEqual(
            scored["scorer"]["round_trip_pairing"]["one_way_pair_candidate_count"],
            0,
        )
        self.assertFalse(
            any(item.startswith("round-trip-pair:") for item in ranked_ids)
        )

    def test_round_trip_pairing_with_only_invalid_pairs_has_empty_frontier(
        self,
    ) -> None:
        outbound = [
            outbound_via_ist("outbound-invalid-a", price=10_000, layover_min=2_220),
            outbound_via_ist("outbound-invalid-b", price=20_000, layover_min=2_280),
        ]
        inbound = [
            return_from_fra("return-a", price=30_000),
            return_from_fra("return-b", price=40_000, slot=1),
        ]

        scored = DecisionScorer(
            DecisionScorerOptions(
                round_trip=True,
                max_layover_min=1_440,
                max_round_trip_pairs=2,
                max_options=10,
            )
        ).score({"candidates": [*outbound, *inbound]})
        ranked = scored["mixed_candidate_ranking"]["ranked_candidates"]

        self.assertEqual(
            scored["scorer"]["round_trip_pairing"]["one_way_pair_pool_count"],
            4,
        )
        self.assertTrue(ranked)
        self.assertTrue(
            all(item["validation"]["status"] == "invalid" for item in ranked)
        )
        self.assertEqual(scored["decision_frontier"]["options"], [])

    def test_round_trip_pairing_order_is_invariant_under_input_permutations(
        self,
    ) -> None:
        outbound = [
            candidate(
                candidate_id,
                source_type="provider_full_route",
                price=10_000,
                ticketing_model="provider_order_unverified",
                segments=[
                    segment(
                        "SVX",
                        "FRA",
                        depart="2026-09-20T05:00:00+00:00",
                        arrive="2026-09-20T10:00:00+00:00",
                    )
                ],
            )
            for candidate_id in ("outbound-b", "outbound-a")
        ]
        inbound = [
            candidate(
                candidate_id,
                source_type="provider_full_route",
                price=20_000,
                ticketing_model="provider_order_unverified",
                segments=[
                    segment(
                        "FRA",
                        "SVX",
                        depart="2026-09-30T06:00:00+00:00",
                        arrive="2026-09-30T11:00:00+00:00",
                    )
                ],
                direction="return",
            )
            for candidate_id in ("return-b", "return-a")
        ]
        inputs = [*outbound, *inbound]
        expected_ids = [
            "round-trip-pair:outbound-a:return-a",
            "round-trip-pair:outbound-a:return-b",
            "round-trip-pair:outbound-b:return-a",
            "round-trip-pair:outbound-b:return-b",
        ]
        scorer = DecisionScorer(
            DecisionScorerOptions(
                round_trip=True,
                max_round_trip_pairs=4,
                max_options=4,
            )
        )

        for input_order in permutations(inputs):
            scored = scorer.score({"candidates": list(input_order)})
            ranked_ids = [
                item["id"]
                for item in scored["mixed_candidate_ranking"]["ranked_candidates"]
            ]
            frontier_ids = [
                item["id"] for item in scored["decision_frontier"]["options"]
            ]
            self.assertEqual(ranked_ids, expected_ids)
            self.assertEqual(frontier_ids, expected_ids)

    def test_decision_scorer_rejects_return_before_outbound_arrival(self) -> None:
        outbound = candidate(
            "outbound-one-way",
            source_type="provider_full_route",
            price=45000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "NTE",
                    "IST",
                    depart="2026-07-09T17:20:00+02:00",
                    arrive="2026-07-10T01:20:00+03:00",
                )
            ],
        )
        inbound = candidate(
            "return-one-way",
            source_type="provider_full_route",
            price=45000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "IST",
                    "NTE",
                    depart="2026-07-09T23:00:00+03:00",
                    arrive="2026-07-10T03:00:00+02:00",
                )
            ],
            direction="return",
        )

        scored = DecisionScorer(DecisionScorerOptions(round_trip=True)).score(
            {"candidates": [outbound, inbound]}
        )
        ranked = scored["mixed_candidate_ranking"]["ranked_candidates"][0]

        self.assertEqual(ranked["candidate_status"], "impossible")
        self.assertEqual(
            ranked["chronology_violations"][0]["reason"],
            "return_departure_before_outbound_arrival",
        )
        self.assertIn(
            "return_departure_before_outbound_arrival",
            ranked["ranking_reasons"],
        )
        self.assertEqual(scored["decision_frontier"]["options"], [])

    def test_comfortable_separate_ticket_connection_is_not_high_risk(self) -> None:
        assembled = candidate(
            "assembled",
            source_type="gateway_separate_ticket",
            price=41441,
            ticketing_model="separate_ticket_sum",
            segments=[
                segment(
                    "FRA",
                    "IST",
                    depart="2026-09-17T11:30:00+02:00",
                    arrive="2026-09-17T15:40:00+03:00",
                    offer_id="tk-leg",
                    ticketing_boundary="separate_ticket_leg",
                ),
                segment(
                    "IST",
                    "SVX",
                    depart="2026-09-17T19:45:00+03:00",
                    arrive="2026-09-18T02:25:00+05:00",
                    offer_id="u6-leg",
                    ticketing_boundary="separate_ticket_leg",
                ),
            ],
        )
        assembled["self_transfer"] = True

        ranked = rank_mixed_candidates({"candidates": [assembled]})[
            "ranked_candidates"
        ][0]

        self.assertEqual(ranked["connection_assessment"]["status"], "valid")
        self.assertEqual(ranked["connection_assessment"]["comfort"], "comfortable")
        self.assertEqual(ranked["ticket_protection"]["status"], "unprotected")
        self.assertEqual(ranked["rank_components"]["connection_risk_score"], 0)

    def test_airport_change_is_rejected_before_frontier(self) -> None:
        airport_change = candidate(
            "airport-change",
            source_type="provider_full_route",
            price=30000,
            ticketing_model="provider_order_unverified",
            segments=[
                segment(
                    "IST",
                    "SVO",
                    depart="2026-09-17T10:00:00+03:00",
                    arrive="2026-09-17T14:00:00+03:00",
                ),
                segment(
                    "DME",
                    "SVX",
                    depart="2026-09-17T20:00:00+03:00",
                    arrive="2026-09-18T00:00:00+05:00",
                ),
            ],
        )

        ranking = rank_mixed_candidates({"candidates": [airport_change]})
        ranked = ranking["ranked_candidates"][0]

        self.assertEqual(ranked["connection_assessment"]["status"], "invalid")
        self.assertIn("airport_change_forbidden", ranked["ranking_reasons"])
        self.assertNotIn("mct_violations", ranked)
        self.assertNotIn("cross_ticket_mct_violation", ranked["ranking_reasons"])
        self.assertEqual(build_decision_frontier(ranking)["options"], [])

    def test_nine_hour_same_airport_layover_is_valid_but_long(self) -> None:
        overnight = candidate(
            "overnight",
            source_type="gateway_separate_ticket",
            price=40000,
            ticketing_model="separate_ticket_sum",
            segments=[
                segment(
                    "FRA",
                    "IST",
                    depart="2026-09-17T08:00:00+02:00",
                    arrive="2026-09-17T12:00:00+03:00",
                    offer_id="leg-1",
                ),
                segment(
                    "IST",
                    "SVX",
                    depart="2026-09-17T21:00:00+03:00",
                    arrive="2026-09-18T03:30:00+05:00",
                    offer_id="leg-2",
                ),
            ],
        )

        ranked = rank_mixed_candidates({"candidates": [overnight]})[
            "ranked_candidates"
        ][0]

        self.assertEqual(ranked["connection_assessment"]["status"], "valid")
        self.assertEqual(ranked["connection_assessment"]["comfort"], "long")

    def test_frontier_hides_two_stop_cheapest_when_one_stop_exists(self) -> None:
        one_stop = candidate(
            "one-stop",
            source_type="provider_full_route",
            price=60000,
            ticketing_model="provider_order_unverified",
            elapsed_min=600,
            segments=[
                segment(
                    "SVX",
                    "IST",
                    depart="2026-07-19T08:00:00+05:00",
                    arrive="2026-07-19T10:00:00+03:00",
                    carrier="SU",
                    flight_number="SU1",
                ),
                segment(
                    "IST",
                    "LHR",
                    depart="2026-07-19T13:00:00+03:00",
                    arrive="2026-07-19T15:00:00+01:00",
                    carrier="TK",
                    flight_number="TK1",
                ),
            ],
        )
        two_stop = candidate(
            "two-stop-cheapest",
            source_type="provider_full_route",
            price=30000,
            ticketing_model="provider_order_unverified",
            elapsed_min=900,
            segments=[
                segment(
                    "SVX",
                    "UFA",
                    depart="2026-07-19T08:00:00+05:00",
                    arrive="2026-07-19T09:00:00+05:00",
                    carrier="WZ",
                    flight_number="WZ1",
                ),
                segment(
                    "UFA",
                    "IST",
                    depart="2026-07-19T12:00:00+05:00",
                    arrive="2026-07-19T14:00:00+03:00",
                    carrier="DP",
                    flight_number="DP1",
                ),
                segment(
                    "IST",
                    "LHR",
                    depart="2026-07-19T17:00:00+03:00",
                    arrive="2026-07-19T19:00:00+01:00",
                    carrier="TK",
                    flight_number="TK2",
                ),
            ],
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [two_stop, one_stop]})
        )

        self.assertEqual([item["id"] for item in frontier["options"]], ["one-stop"])
        self.assertNotIn(
            "cheapest_selected", frontier["options"][0]["selection_reasons"]
        )

    def test_frontier_uses_long_layover_only_as_global_fallback(self) -> None:
        normal = candidate(
            "normal",
            source_type="provider_full_route",
            price=60000,
            ticketing_model="provider_order_unverified",
            elapsed_min=800,
            segments=[
                segment(
                    "SVX",
                    "IST",
                    depart="2026-07-19T07:00:00+05:00",
                    arrive="2026-07-19T10:00:00+03:00",
                    carrier="SU",
                    flight_number="SU1",
                ),
                segment(
                    "IST",
                    "LHR",
                    depart="2026-07-19T14:00:00+03:00",
                    arrive="2026-07-19T16:00:00+01:00",
                    carrier="TK",
                    flight_number="TK1",
                ),
            ],
        )
        long_wait = candidate(
            "long-wait",
            source_type="provider_full_route",
            price=40000,
            ticketing_model="provider_order_unverified",
            elapsed_min=1100,
            segments=[
                segment(
                    "SVX",
                    "IST",
                    depart="2026-07-19T07:00:00+05:00",
                    arrive="2026-07-19T10:00:00+03:00",
                    carrier="U6",
                    flight_number="U61",
                ),
                segment(
                    "IST",
                    "LHR",
                    depart="2026-07-19T18:00:00+03:00",
                    arrive="2026-07-19T20:00:00+01:00",
                    carrier="BA",
                    flight_number="BA1",
                ),
            ],
        )

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": [long_wait, normal]})
        )
        fallback = build_decision_frontier(
            rank_mixed_candidates({"candidates": [long_wait]})
        )

        self.assertEqual([item["id"] for item in frontier["options"]], ["normal"])
        self.assertEqual([item["id"] for item in fallback["options"]], ["long-wait"])

    def test_frontier_balances_quality_carriers_and_gateways(self) -> None:
        def itinerary(
            candidate_id: str,
            *,
            source_type: str,
            price: int,
            ticketing_model: str,
            elapsed_min: int,
            first_carrier: str,
            first_flight: str,
            first_depart: str,
            first_arrive: str,
            gateway: str,
            second_carrier: str,
            second_flight: str,
            second_depart: str,
            second_arrive: str,
        ) -> dict:
            return candidate(
                candidate_id,
                source_type=source_type,
                price=price,
                ticketing_model=ticketing_model,
                elapsed_min=elapsed_min,
                segments=[
                    segment(
                        "SVX",
                        gateway,
                        depart=first_depart,
                        arrive=first_arrive,
                        carrier=first_carrier,
                        marketing_carrier=first_carrier,
                        flight_number=first_flight,
                    ),
                    segment(
                        gateway,
                        "LHR",
                        depart=second_depart,
                        arrive=second_arrive,
                        carrier=second_carrier,
                        marketing_carrier=second_carrier,
                        flight_number=second_flight,
                    ),
                ],
            )

        candidates = [
            itinerary(
                "su-tk",
                source_type="provider_full_route",
                price=57481,
                ticketing_model="provider_order_unverified",
                elapsed_min=830,
                first_carrier="SU",
                first_flight="SU630",
                first_depart="2026-07-19T11:15:00+05:00",
                first_arrive="2026-07-19T14:45:00+03:00",
                gateway="IST",
                second_carrier="TK",
                second_flight="TK1983",
                second_depart="2026-07-19T19:05:00+03:00",
                second_arrive="2026-07-19T21:05:00+01:00",
            ),
            itinerary(
                "su-tk-repeat",
                source_type="provider_full_route",
                price=52290,
                ticketing_model="provider_order_unverified",
                elapsed_min=910,
                first_carrier="SU",
                first_flight="SU630",
                first_depart="2026-07-19T11:15:00+05:00",
                first_arrive="2026-07-19T14:45:00+03:00",
                gateway="IST",
                second_carrier="TK",
                second_flight="TK1987",
                second_depart="2026-07-19T20:25:00+03:00",
                second_arrive="2026-07-19T22:25:00+01:00",
            ),
            itinerary(
                "su-ba",
                source_type="gateway_separate_ticket",
                price=48566,
                ticketing_model="separate_ticket_sum",
                elapsed_min=815,
                first_carrier="SU",
                first_flight="SU-630",
                first_depart="2026-07-19T11:15:00+05:00",
                first_arrive="2026-07-19T14:45:00+03:00",
                gateway="IST",
                second_carrier="BA",
                second_flight="BA-0719",
                second_depart="2026-07-19T18:50:00+03:00",
                second_arrive="2026-07-19T20:50:00+01:00",
            ),
            itinerary(
                "u6-tk",
                source_type="gateway_separate_ticket",
                price=61591,
                ticketing_model="separate_ticket_sum",
                elapsed_min=800,
                first_carrier="U6",
                first_flight="U6-773",
                first_depart="2026-07-19T07:20:00+05:00",
                first_arrive="2026-07-19T10:50:00+03:00",
                gateway="IST",
                second_carrier="TK",
                second_flight="TK-1971",
                second_depart="2026-07-19T14:50:00+03:00",
                second_arrive="2026-07-19T16:40:00+01:00",
            ),
            itinerary(
                "u6-tk-tight",
                source_type="gateway_separate_ticket",
                price=61591,
                ticketing_model="separate_ticket_sum",
                elapsed_min=710,
                first_carrier="U6",
                first_flight="U6-773",
                first_depart="2026-07-19T07:20:00+05:00",
                first_arrive="2026-07-19T10:50:00+03:00",
                gateway="IST",
                second_carrier="TK",
                second_flight="TK-1985",
                second_depart="2026-07-19T13:15:00+03:00",
                second_arrive="2026-07-19T15:10:00+01:00",
            ),
            itinerary(
                "u6-ba-long",
                source_type="gateway_separate_ticket",
                price=46843,
                ticketing_model="separate_ticket_sum",
                elapsed_min=1050,
                first_carrier="U6",
                first_flight="U6-773",
                first_depart="2026-07-19T07:20:00+05:00",
                first_arrive="2026-07-19T10:50:00+03:00",
                gateway="IST",
                second_carrier="BA",
                second_flight="BA-0719",
                second_depart="2026-07-19T18:50:00+03:00",
                second_arrive="2026-07-19T20:50:00+01:00",
            ),
            itinerary(
                "dubai",
                source_type="provider_full_route",
                price=600412,
                ticketing_model="provider_order_unverified",
                elapsed_min=1050,
                first_carrier="FZ",
                first_flight="FZ-980",
                first_depart="2026-07-19T02:40:00+05:00",
                first_arrive="2026-07-19T07:55:00+04:00",
                gateway="DXB",
                second_carrier="EK",
                second_flight="EK-31",
                second_depart="2026-07-19T11:25:00+04:00",
                second_arrive="2026-07-19T16:10:00+01:00",
            ),
        ]

        frontier = build_decision_frontier(
            rank_mixed_candidates({"candidates": candidates})
        )
        options = frontier["options"]

        self.assertEqual(
            [item["id"] for item in options],
            ["su-tk", "su-ba", "u6-tk", "dubai"],
        )
        self.assertIn("best_viable", options[0]["selection_reasons"])
        self.assertIn("cheapest_selected", options[1]["selection_reasons"])
        self.assertIn("fastest_selected", options[2]["selection_reasons"])
        self.assertIn("gateway_alternative", options[3]["selection_reasons"])


if __name__ == "__main__":
    unittest.main()
