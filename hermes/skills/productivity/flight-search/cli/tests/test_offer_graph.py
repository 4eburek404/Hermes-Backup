from __future__ import annotations

import unittest

from flights_cli.apps.common import validate_contract_payload
from flights_cli.pipeline.offer_graph import (
    OFFER_GRAPH_SCHEMA_VERSION,
    build_offer_graph,
    materialize_offer_graph_candidates,
)


class OfferGraphTests(unittest.TestCase):
    def graph_with_provider_and_gateway(
        self,
        *,
        provider_price: int = 39000,
        gateway_destination_departure_at: str = "2026-08-15T15:00:00+03:00",
    ) -> dict:
        return build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "origin": "SVX",
                    "destination": "AMS",
                    "top_offers": [
                        {
                            "id": "kb-full-1",
                            "price": provider_price,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "IST",
                                    "flight_number": "U6 123",
                                    "departure_at": "2026-08-15T10:00:00+05:00",
                                    "arrival_at": "2026-08-15T13:00:00+03:00",
                                },
                                {
                                    "origin": "IST",
                                    "destination": "AMS",
                                    "flight_number": "TK 1953",
                                    "departure_at": "2026-08-15T15:00:00+03:00",
                                    "arrival_at": "2026-08-15T17:30:00+02:00",
                                },
                            ],
                        }
                    ],
                }
            ],
            gateway_leg_results={
                "searched_gateways": 1,
                "viable_gateways": 1,
                "failed_gateways": 0,
                "not_searched_budget": 0,
                "gateways": [
                    {
                        "gateway": "IST",
                        "searched": True,
                        "viable": True,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "SVX",
                            "destination": "IST",
                            "provider": "kupibilet",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "svx-ist-1",
                                    "price": 18000,
                                    "currency": "RUB",
                                    "flight_number": "U6123",
                                    "departure_at": "2026-08-15T10:00:00+05:00",
                                    "arrival_at": "2026-08-15T13:00:00+03:00",
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "IST",
                            "destination": "AMS",
                            "provider": "fli",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ist-ams-1",
                                    "price": 22000,
                                    "currency": "RUB",
                                    "flight_number": "TK1953",
                                    "departure_at": gateway_destination_departure_at,
                                    "arrival_at": "2026-08-15T17:30:00+02:00",
                                }
                            ],
                        },
                        "provider_failures": [],
                        "skipped_reasons": [],
                        "missing_legs": [],
                    }
                ],
            },
        )

    def test_kupibilet_full_route_builds_offer_with_route_edges(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "status": "ok",
                    "execution_state": "searched",
                    "offer_count": 1,
                    "top_offers": [
                        {
                            "id": "kb-full-1",
                            "price": 42000,
                            "currency": "RUB",
                            "segments": [
                                {"origin": "SVX", "destination": "IST"},
                                {"origin": "IST", "destination": "AMS"},
                            ],
                        }
                    ],
                }
            ],
            gateway_leg_results={},
        )

        validate_contract_payload("offer_graph", graph)
        self.assertEqual(graph["schema_version"], OFFER_GRAPH_SCHEMA_VERSION)
        self.assertEqual(len(graph["offers"]), 1)
        offer = graph["offers"][0]
        self.assertEqual(offer["source_type"], "provider_full_route")
        self.assertEqual(offer["provider"], "kupibilet")
        self.assertEqual(offer["ticketing_boundary"], "provider_protected_full_route")
        self.assertEqual(offer["route"], ["SVX", "IST", "AMS"])
        self.assertEqual(len(offer["edge_ids"]), 2)
        self.assertEqual(
            [(edge["origin"], edge["destination"]) for edge in graph["edges"]],
            [("SVX", "IST"), ("IST", "AMS")],
        )
        self.assertEqual(graph["connections"], [])
        self.assertEqual(graph["coverage"]["provider_full_route_offer_count"], 1)

    def test_provider_full_route_materializes_with_provider_price(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "origin": "SVX",
                    "destination": "AMS",
                    "top_offers": [
                        {
                            "id": "kb-full-1",
                            "price": 42000,
                            "currency": "RUB",
                            "segments": [
                                {"origin": "SVX", "destination": "IST"},
                                {"origin": "IST", "destination": "AMS"},
                            ],
                        }
                    ],
                }
            ],
            gateway_leg_results={},
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(
            envelope["schema_version"], "flight_offer_candidate_envelope.v1"
        )
        self.assertEqual(len(envelope["candidates"]), 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["source_type"], "provider_full_route")
        self.assertEqual(candidate["source_providers"], ["kupibilet"])
        self.assertTrue(candidate["covers_requested_trip"])
        self.assertEqual(candidate["journey_scope"], "one_way")
        self.assertEqual(candidate["price"], 42000)
        self.assertEqual(candidate["currency"], "RUB")
        self.assertEqual(candidate["price_basis"], "provider_offer_price")
        self.assertEqual(candidate["ticketing_model"], "provider_order_unverified")
        self.assertEqual(candidate["detail_status"], "full")
        self.assertEqual(candidate["warnings"], [])
        self.assertEqual(
            [
                (segment["origin"], segment["destination"])
                for segment in candidate["journeys"][0]["segments"]
            ],
            [("SVX", "IST"), ("IST", "AMS")],
        )

    def test_gateway_legs_build_two_edges_and_connection(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[],
            gateway_leg_results={
                "searched_gateways": 1,
                "viable_gateways": 1,
                "failed_gateways": 0,
                "not_searched_budget": 0,
                "gateways": [
                    {
                        "gateway": "IST",
                        "searched": True,
                        "viable": True,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "SVX",
                            "destination": "IST",
                            "provider": "kupibilet",
                            "status": "ok",
                            "execution_state": "searched",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "svx-ist-1",
                                    "price": 18000,
                                    "currency": "RUB",
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "IST",
                            "destination": "AMS",
                            "provider": "fli",
                            "status": "ok",
                            "execution_state": "searched",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ist-ams-1",
                                    "price": 22000,
                                    "currency": "RUB",
                                }
                            ],
                        },
                        "provider_failures": [],
                        "skipped_reasons": [],
                        "missing_legs": [],
                    }
                ],
            },
        )

        validate_contract_payload("offer_graph", graph)
        self.assertEqual(len(graph["offers"]), 2)
        self.assertEqual(len(graph["edges"]), 2)
        self.assertEqual(len(graph["connections"]), 1)
        self.assertEqual(
            [
                (edge["origin"], edge["destination"], edge["provider"])
                for edge in graph["edges"]
            ],
            [("SVX", "IST", "kupibilet"), ("IST", "AMS", "fli")],
        )
        self.assertEqual(
            {offer["ticketing_boundary"] for offer in graph["offers"]},
            {"separate_ticket_leg"},
        )
        connection = graph["connections"][0]
        self.assertEqual(connection["gateway"], "IST")
        self.assertEqual(connection["ticketing_boundary"], "separate_ticket_candidate")
        self.assertEqual(
            connection["candidate_status"], "complete_gateway_legs_unranked"
        )
        self.assertEqual(
            graph["coverage"]["assembled_separate_ticket_candidate_count"], 1
        )

    def test_gateway_separate_ticket_materializes_summed_leg_price(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[],
            gateway_leg_results={
                "searched_gateways": 1,
                "viable_gateways": 1,
                "failed_gateways": 0,
                "not_searched_budget": 0,
                "gateways": [
                    {
                        "gateway": "IST",
                        "searched": True,
                        "viable": True,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "SVX",
                            "destination": "IST",
                            "provider": "kupibilet",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "svx-ist-1",
                                    "price": 18000,
                                    "currency": "RUB",
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "IST",
                            "destination": "AMS",
                            "provider": "fli",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ist-ams-1",
                                    "price": 22000,
                                    "currency": "RUB",
                                }
                            ],
                        },
                        "provider_failures": [],
                        "skipped_reasons": [],
                        "missing_legs": [],
                    }
                ],
            },
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(len(envelope["candidates"]), 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["source_type"], "gateway_separate_ticket")
        self.assertEqual(candidate["source_providers"], ["kupibilet", "fli"])
        self.assertEqual(candidate["gateway"], "IST")
        self.assertTrue(candidate["covers_requested_trip"])
        self.assertEqual(candidate["price"], 40000)
        self.assertEqual(candidate["currency"], "RUB")
        self.assertEqual(candidate["price_basis"], "summed_live_leg_prices")
        self.assertEqual(candidate["ticketing_model"], "separate_ticket_sum")
        self.assertIn("separate_ticket_connection_unverified", candidate["warnings"])
        self.assertEqual(
            [
                (segment["origin"], segment["destination"])
                for segment in candidate["journeys"][0]["segments"]
            ],
            [("SVX", "IST"), ("IST", "AMS")],
        )

    def test_missing_gateway_leg_does_not_create_full_candidate(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[],
            gateway_leg_results={
                "searched_gateways": 1,
                "viable_gateways": 0,
                "failed_gateways": 0,
                "not_searched_budget": 0,
                "gateways": [
                    {
                        "gateway": "IST",
                        "searched": True,
                        "viable": False,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "SVX",
                            "destination": "IST",
                            "provider": "kupibilet",
                            "status": "ok",
                            "execution_state": "searched",
                            "offer_count": 1,
                            "offers": [{"id": "svx-ist-1"}],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "IST",
                            "destination": "AMS",
                            "provider": "fli",
                            "status": "ok",
                            "execution_state": "searched",
                            "offer_count": 0,
                            "offers": [],
                        },
                        "provider_failures": [],
                        "skipped_reasons": [],
                        "missing_legs": ["destination_leg"],
                    }
                ],
            },
        )

        validate_contract_payload("offer_graph", graph)
        self.assertEqual(len(graph["offers"]), 1)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["connections"], [])
        self.assertEqual(graph["coverage"]["connection_count"], 0)
        self.assertEqual(
            graph["coverage"]["assembled_separate_ticket_candidate_count"], 0
        )
        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
        )
        self.assertEqual(envelope["candidates"], [])

    def test_direct_only_hard_constraint_rejects_connected_candidates(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "origin": "SVX",
                    "destination": "AMS",
                    "top_offers": [
                        {
                            "id": "kb-connected",
                            "price": 42000,
                            "currency": "RUB",
                            "segments": [
                                {"origin": "SVX", "destination": "IST"},
                                {"origin": "IST", "destination": "AMS"},
                            ],
                        }
                    ],
                }
            ],
            gateway_leg_results={},
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            direct_only=True,
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(envelope["candidates"], [])
        self.assertEqual(envelope["coverage"]["rejected_count"], 1)
        self.assertEqual(
            envelope["rejected"][0]["reason"],
            "direct_only_hard_constraint",
        )

    def test_summary_only_provider_offer_materializes_with_warning(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "origin": "SVX",
                    "destination": "AMS",
                    "top_offers": [
                        {
                            "id": "kb-summary",
                            "price": 39000,
                            "currency": "RUB",
                            "detail_status": "summary_only",
                        }
                    ],
                }
            ],
            gateway_leg_results={},
        )

        validate_contract_payload("offer_graph", graph)
        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(len(envelope["candidates"]), 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["detail_status"], "summary_only")
        self.assertFalse(candidate["covers_requested_trip"])
        self.assertEqual(candidate["price"], 39000)
        self.assertEqual(candidate["price_basis"], "provider_offer_price")
        self.assertIn("summary_only_offer_details", candidate["warnings"])

    def test_same_physical_itinerary_dedupes_with_alternate_sources(self) -> None:
        envelope = materialize_offer_graph_candidates(
            self.graph_with_provider_and_gateway(),
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        self.assertEqual(envelope["coverage"]["deduped_count"], 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["source_type"], "provider_full_route")
        self.assertEqual(candidate["price"], 39000)
        self.assertEqual(candidate["currency"], "RUB")
        self.assertEqual(candidate["price_basis"], "provider_offer_price")
        self.assertEqual(candidate["source_providers"], ["kupibilet", "fli"])
        self.assertEqual(len(candidate["alternate_sources"]), 1)
        alternate = candidate["alternate_sources"][0]
        self.assertEqual(alternate["source_type"], "gateway_separate_ticket")
        self.assertEqual(alternate["price"], 40000)
        self.assertEqual(alternate["price_basis"], "summed_live_leg_prices")
        self.assertEqual(
            candidate["price_comparison"],
            {
                "provider_offer_price": {"amount": 39000, "currency": "RUB"},
                "summed_live_leg_prices": {"amount": 40000, "currency": "RUB"},
                "difference": 1000,
                "currency": "RUB",
            },
        )

    def test_different_times_do_not_dedupe(self) -> None:
        envelope = materialize_offer_graph_candidates(
            self.graph_with_provider_and_gateway(
                gateway_destination_departure_at="2026-08-15T16:00:00+03:00"
            ),
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 2)
        self.assertEqual(envelope["coverage"]["deduped_count"], 0)
        self.assertEqual(
            [candidate["source_type"] for candidate in envelope["candidates"]],
            ["provider_full_route", "gateway_separate_ticket"],
        )

    def test_provider_price_retained_when_summed_legs_are_cheaper(self) -> None:
        envelope = materialize_offer_graph_candidates(
            self.graph_with_provider_and_gateway(provider_price=41000),
            requested_origin="SVX",
            requested_destination="AMS",
        )

        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["source_type"], "provider_full_route")
        self.assertEqual(candidate["price"], 41000)
        self.assertEqual(candidate["price_basis"], "provider_offer_price")
        self.assertEqual(candidate["alternate_sources"][0]["price"], 40000)
        self.assertEqual(candidate["price_comparison"]["difference"], -1000)

    def test_alternate_sources_are_retained_after_repeated_dedupe(self) -> None:
        graph = self.graph_with_provider_and_gateway()
        duplicate = dict(graph["connections"][0])
        duplicate["id"] = "connection:IST:duplicate"
        graph["connections"].append(duplicate)

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
        )

        candidate = envelope["candidates"][0]
        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        self.assertEqual(envelope["coverage"]["deduped_count"], 2)
        self.assertEqual(len(candidate["alternate_sources"]), 1)
        self.assertEqual(
            candidate["alternate_sources"][0]["source_type"],
            "gateway_separate_ticket",
        )


if __name__ == "__main__":
    unittest.main()
