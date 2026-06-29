from __future__ import annotations

import unittest

from flights_cli.domain.vocabulary import RouteFamily
from flights_cli.pipeline.candidate_ranker import rank_mixed_candidates


def segment(origin: str, destination: str) -> dict[str, str]:
    return {"origin": origin, "destination": destination}


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
) -> dict:
    return {
        "id": candidate_id,
        "source_type": source_type,
        "provider": "kupibilet" if source_type == "provider_full_route" else None,
        "source_providers": ["kupibilet"],
        "gateway": "IST" if source_type == "gateway_separate_ticket" else None,
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
            "journeys": [{"direction": "outbound", "segments": [segment("SVX", "AMS")]}],
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


if __name__ == "__main__":
    unittest.main()
