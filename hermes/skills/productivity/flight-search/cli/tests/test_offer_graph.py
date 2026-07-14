from __future__ import annotations

import unittest

from flights_cli.commands.common import validate_contract_payload
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
        provider_first_flight_number: str | None = "U6 123",
        provider_second_flight_number: str | None = "TK 1953",
        gateway_first_flight_number: str | None = "U6123",
        gateway_second_flight_number: str | None = "TK1953",
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
                                    "flight_number": provider_first_flight_number,
                                    "departure_at": "2026-08-15T10:00:00+05:00",
                                    "arrival_at": "2026-08-15T13:00:00+03:00",
                                },
                                {
                                    "origin": "IST",
                                    "destination": "AMS",
                                    "flight_number": provider_second_flight_number,
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
                                    "flight_number": gateway_first_flight_number,
                                    "departure_at": "2026-08-15T10:00:00+05:00",
                                    "arrival_at": "2026-08-15T13:00:00+03:00",
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "IST",
                            "destination": "AMS",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ist-ams-1",
                                    "price": 22000,
                                    "currency": "RUB",
                                    "flight_number": gateway_second_flight_number,
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
                            "self_transfer": True,
                            "self_transfer_note": "Collect baggage and check in again.",
                            "self_transfer_source": "tutu",
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
                            "self_transfer": True,
                            "self_transfer_note": "Collect baggage and check in again.",
                            "self_transfer_source": "tutu",
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
        self.assertIs(candidate["self_transfer"], True)
        self.assertEqual(candidate["self_transfer_source"], "tutu")
        self.assertEqual(
            candidate["self_transfer_note"], "Collect baggage and check in again."
        )
        self.assertEqual(candidate["detail_status"], "full")
        self.assertEqual(candidate["warnings"], [])
        self.assertEqual(
            [
                (segment["origin"], segment["destination"])
                for segment in candidate["journeys"][0]["segments"]
            ],
            [("SVX", "IST"), ("IST", "AMS")],
        )

    def test_city_destination_request_accepts_matching_airport_offer(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "origin": "SVX",
                    "destination": "MOW",
                    "top_offers": [
                        {
                            "id": "tutu-direct-dme",
                            "price": 9461,
                            "currency": "RUB",
                            "journeys": [
                                {
                                    "direction": "outbound",
                                    "segments": [
                                        {
                                            "origin": "SVX",
                                            "destination": "DME",
                                            "departure_at": "2026-10-09T06:30:00+05:00",
                                            "arrival_at": "2026-10-09T07:15:00+03:00",
                                        }
                                    ],
                                }
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
            requested_destination="MOW",
            requested_origin_airports=["SVX"],
            requested_destination_airports=["DME", "SVO", "VKO"],
        )

        self.assertEqual(len(envelope["candidates"]), 1)
        self.assertTrue(envelope["candidates"][0]["covers_requested_trip"])

    def test_return_one_way_uses_reversed_exact_airport_scope(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "direction": "return",
                    "origin": "LON",
                    "destination": "IST",
                    "top_offers": [
                        {
                            "id": "return-ltn-ist",
                            "price": 12000,
                            "currency": "RUB",
                            "journeys": [
                                {
                                    "direction": "return",
                                    "segments": [
                                        {
                                            "origin": "LTN",
                                            "destination": "IST",
                                            "departure_at": "2026-08-22T10:00:00+01:00",
                                            "arrival_at": "2026-08-22T16:00:00+03:00",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            gateway_leg_results={},
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="IST",
            requested_destination="LON",
            requested_origin_airports=["IST", "SAW"],
            requested_destination_airports=["LHR", "LGW", "STN", "LTN"],
        )

        self.assertEqual(len(envelope["candidates"]), 1)
        self.assertTrue(envelope["candidates"][0]["covers_requested_trip"])

    def test_tutu_round_trip_offer_uses_journeys_atomically(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "LED",
                    "top_offers": [
                        {
                            "id": "tutu-rt-1",
                            "price": 20441,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "LED",
                                    "departure_at": "2026-09-05T19:00:00+05:00",
                                    "arrival_at": "2026-09-05T19:55:00+03:00",
                                    "marketing_carrier": "SU",
                                }
                            ],
                            "journeys": [
                                {
                                    "direction": "outbound",
                                    "segments": [
                                        {
                                            "origin": "SVX",
                                            "destination": "LED",
                                            "departure_at": (
                                                "2026-09-05T19:00:00+05:00"
                                            ),
                                            "arrival_at": ("2026-09-05T19:55:00+03:00"),
                                            "marketing_carrier": "SU",
                                        }
                                    ],
                                },
                                {
                                    "direction": "return",
                                    "segments": [
                                        {
                                            "origin": "LED",
                                            "destination": "SVX",
                                            "departure_at": (
                                                "2026-09-12T18:55:00+03:00"
                                            ),
                                            "arrival_at": ("2026-09-12T23:40:00+05:00"),
                                            "marketing_carrier": "U6",
                                        }
                                    ],
                                },
                            ],
                            "journey_scope": "round_trip",
                            "ticketing_model": "provider_order_unverified",
                        }
                    ],
                }
            ],
            gateway_leg_results={},
        )

        validate_contract_payload("offer_graph", graph)
        self.assertEqual(len(graph["offers"]), 1)
        self.assertEqual(len(graph["edges"]), 2)
        offer = graph["offers"][0]
        self.assertEqual(offer["id"], "primary_offer:tutu:tutu-rt-1")
        self.assertEqual(offer["journey_scope"], "round_trip")
        self.assertEqual(offer["price"], 20441)
        self.assertEqual(
            [
                (edge["origin"], edge["destination"], edge["direction"])
                for edge in graph["edges"]
            ],
            [("SVX", "LED", "outbound"), ("LED", "SVX", "return")],
        )
        self.assertEqual(graph["coverage"]["provider_full_route_offer_count"], 1)

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="LED",
        )
        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        candidate = envelope["candidates"][0]
        self.assertTrue(candidate["covers_requested_trip"])
        self.assertEqual(candidate["journey_scope"], "round_trip")
        self.assertEqual(candidate["price"], 20441)
        self.assertEqual(
            [journey["direction"] for journey in candidate["journeys"]],
            ["outbound", "return"],
        )

    def test_direct_mode_allows_atomic_round_trip_when_both_directions_direct(
        self,
    ) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "LED",
                    "top_offers": [
                        {
                            "id": "tutu-rt-direct",
                            "price": 18347,
                            "currency": "RUB",
                            "segments": [{"origin": "SVX", "destination": "LED"}],
                            "journeys": [
                                {
                                    "direction": "outbound",
                                    "segments": [
                                        {"origin": "SVX", "destination": "LED"}
                                    ],
                                },
                                {
                                    "direction": "return",
                                    "segments": [
                                        {"origin": "LED", "destination": "SVX"}
                                    ],
                                },
                            ],
                            "journey_scope": "round_trip",
                        }
                    ],
                }
            ],
            gateway_leg_results={},
            direct_mode={"outbound": True, "return": True},
            requested_origin="SVX",
            requested_destination="LED",
        )

        self.assertEqual(len(graph["offers"]), 1)
        self.assertEqual(len(graph["edges"]), 2)
        self.assertNotIn(
            "direct_mode_gate", graph["coverage"].get("skipped_reasons", [])
        )
        envelope = materialize_offer_graph_candidates(
            graph,
            direct_mode={"outbound": True, "return": True},
            requested_origin="SVX",
            requested_destination="LED",
        )
        self.assertEqual(envelope["coverage"]["candidate_count"], 1)

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
                            "provider": "tutu",
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
            [("SVX", "IST", "kupibilet"), ("IST", "AMS", "tutu")],
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

    def test_gateway_access_leg_preserves_provider_returned_feeder_segments(
        self,
    ) -> None:
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
                            "origin": "NTE",
                            "destination": "IST",
                            "provider": "tutu",
                            "status": "ok",
                            "execution_state": "searched",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "nte-ist-via-ams",
                                    "price": 82103,
                                    "currency": "RUB",
                                    "segments": [
                                        {
                                            "origin": "NTE",
                                            "destination": "AMS",
                                            "flight_number": "KL1420",
                                            "departure_at": "2026-07-09T17:20:00+02:00",
                                            "arrival_at": "2026-07-09T18:55:00+02:00",
                                        },
                                        {
                                            "origin": "AMS",
                                            "destination": "IST",
                                            "flight_number": "KL1959",
                                            "departure_at": "2026-07-09T21:00:00+02:00",
                                            "arrival_at": "2026-07-10T01:20:00+03:00",
                                        },
                                    ],
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "IST",
                            "destination": "SVX",
                            "provider": "tutu",
                            "status": "ok",
                            "execution_state": "searched",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ist-svx-direct",
                                    "price": 22418,
                                    "currency": "RUB",
                                    "segments": [
                                        {
                                            "origin": "IST",
                                            "destination": "SVX",
                                            "flight_number": "SU2137",
                                            "departure_at": "2026-07-10T12:50:00+03:00",
                                            "arrival_at": "2026-07-10T19:55:00+05:00",
                                        }
                                    ],
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
        self.assertEqual(
            [(edge["origin"], edge["destination"]) for edge in graph["edges"]],
            [("NTE", "AMS"), ("AMS", "IST"), ("IST", "SVX")],
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="NTE",
            requested_destination="SVX",
        )

        self.assertEqual(len(envelope["candidates"]), 1)
        candidate = envelope["candidates"][0]
        self.assertTrue(candidate["covers_requested_trip"])
        self.assertEqual(candidate["gateway"], "IST")
        self.assertEqual(
            [
                (segment["origin"], segment["destination"])
                for segment in candidate["journeys"][0]["segments"]
            ],
            [("NTE", "AMS"), ("AMS", "IST"), ("IST", "SVX")],
        )

    def test_edges_preserve_ticketing_and_carrier_metadata(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "origin": "NTE",
                    "destination": "IST",
                    "top_offers": [
                        {
                            "id": "tutu-kl",
                            "price": 82103,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "NTE",
                                    "destination": "AMS",
                                    "flight_number": "KL1420",
                                    "marketing_carrier": "KL",
                                    "operating_carrier": "KL",
                                    "carrier": "KLM Royal Dutch Airlines",
                                    "departure_at": "2026-07-09T17:20:00+02:00",
                                    "arrival_at": "2026-07-09T18:55:00+02:00",
                                }
                            ],
                        }
                    ],
                }
            ],
            gateway_leg_results={},
        )

        edge = graph["edges"][0]
        self.assertEqual(edge["ticketing_boundary"], "provider_protected_full_route")
        self.assertEqual(edge["ticketing_model"], "provider_order_unverified")
        self.assertEqual(edge["marketing_carrier"], "KL")
        self.assertEqual(edge["carrier"], "KLM ROYAL DUTCH AIRLINES")

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="NTE",
            requested_destination="AMS",
        )
        segment = envelope["candidates"][0]["journeys"][0]["segments"][0]
        self.assertEqual(segment["ticketing_boundary"], "provider_protected_full_route")
        self.assertEqual(segment["ticketing_model"], "provider_order_unverified")
        self.assertEqual(segment["marketing_carrier"], "KL")
        self.assertEqual(segment["carrier"], "KLM ROYAL DUTCH AIRLINES")

    def test_n_leg_gateway_path_materializes_three_offer_chain(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[],
            gateway_leg_results={
                "searched_gateways": 2,
                "viable_gateways": 2,
                "failed_gateways": 0,
                "not_searched_budget": 0,
                "gateways": [
                    {
                        "gateway": "AMS",
                        "searched": True,
                        "viable": True,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "NTE",
                            "destination": "AMS",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "nte-ams",
                                    "origin": "NTE",
                                    "destination": "AMS",
                                    "price": 100,
                                    "currency": "RUB",
                                    "flight_number": "KL1420",
                                    "departure_at": "2026-07-09T17:20:00+02:00",
                                    "arrival_at": "2026-07-09T18:55:00+02:00",
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "AMS",
                            "destination": "IST",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ams-ist",
                                    "origin": "AMS",
                                    "destination": "IST",
                                    "price": 200,
                                    "currency": "RUB",
                                    "flight_number": "KL1959",
                                    "departure_at": "2026-07-09T21:00:00+02:00",
                                    "arrival_at": "2026-07-10T01:20:00+03:00",
                                }
                            ],
                        },
                    },
                    {
                        "gateway": "IST",
                        "searched": True,
                        "viable": True,
                        "origin_leg": {
                            "leg": "origin_to_gateway",
                            "origin": "AMS",
                            "destination": "IST",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ams-ist-duplicate",
                                    "origin": "AMS",
                                    "destination": "IST",
                                    "price": 200,
                                    "currency": "RUB",
                                    "flight_number": "KL1959",
                                    "departure_at": "2026-07-09T21:00:00+02:00",
                                    "arrival_at": "2026-07-10T01:20:00+03:00",
                                }
                            ],
                        },
                        "destination_leg": {
                            "leg": "gateway_to_destination",
                            "origin": "IST",
                            "destination": "SVX",
                            "provider": "tutu",
                            "offer_count": 1,
                            "offers": [
                                {
                                    "id": "ist-svx",
                                    "origin": "IST",
                                    "destination": "SVX",
                                    "price": 300,
                                    "currency": "RUB",
                                    "flight_number": "SU2137",
                                    "departure_at": "2026-07-10T12:50:00+03:00",
                                    "arrival_at": "2026-07-10T19:55:00+05:00",
                                }
                            ],
                        },
                    },
                ],
            },
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="NTE",
            requested_destination="SVX",
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["source_type"], "gateway_separate_ticket")
        self.assertEqual(candidate["path_offer_count"], 3)
        self.assertEqual(candidate["price"], 600)
        self.assertEqual(candidate["gateways"], ["AMS", "IST"])
        self.assertEqual(
            [
                (segment["origin"], segment["destination"])
                for segment in candidate["journeys"][0]["segments"]
            ],
            [("NTE", "AMS"), ("AMS", "IST"), ("IST", "SVX")],
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
                            "provider": "tutu",
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
        self.assertEqual(candidate["source_providers"], ["kupibilet", "tutu"])
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
                            "provider": "tutu",
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

    def test_direct_mode_gate_rejects_connected_primary_path_at_ingest(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "direction": "outbound",
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
                        },
                        {
                            "id": "kb-direct",
                            "price": 52000,
                            "currency": "RUB",
                            "segments": [{"origin": "SVX", "destination": "AMS"}],
                        },
                    ],
                }
            ],
            gateway_leg_results={},
            direct_mode={"outbound": True},
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(len(graph["offers"]), 1)
        self.assertEqual(graph["offers"][0]["id"], "primary_offer:kupibilet:kb-direct")
        self.assertIn("direct_mode_gate", graph["coverage"]["skipped_reasons"])

    def test_direct_mode_gate_rejects_atomic_round_trip_when_gated_journey_connected(
        self,
    ) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "LED",
                    "top_offers": [
                        {
                            "id": "tutu-rt-connected-out",
                            "price": 20441,
                            "currency": "RUB",
                            "segments": [
                                {"origin": "SVX", "destination": "SVO"},
                                {"origin": "SVO", "destination": "LED"},
                            ],
                            "journeys": [
                                {
                                    "direction": "outbound",
                                    "segments": [
                                        {"origin": "SVX", "destination": "SVO"},
                                        {"origin": "SVO", "destination": "LED"},
                                    ],
                                },
                                {
                                    "direction": "return",
                                    "segments": [
                                        {"origin": "LED", "destination": "SVX"}
                                    ],
                                },
                            ],
                            "journey_scope": "round_trip",
                        }
                    ],
                }
            ],
            gateway_leg_results={},
            direct_mode={"outbound": True},
            requested_origin="SVX",
            requested_destination="LED",
        )

        self.assertEqual(graph["offers"], [])
        self.assertEqual(graph["edges"], [])
        self.assertIn("direct_mode_gate", graph["coverage"]["skipped_reasons"])

    def test_direct_mode_gate_allows_atomic_round_trip_connected_other_direction(
        self,
    ) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "LED",
                    "top_offers": [
                        {
                            "id": "tutu-rt-connected-return",
                            "price": 20441,
                            "currency": "RUB",
                            "segments": [{"origin": "SVX", "destination": "LED"}],
                            "journeys": [
                                {
                                    "direction": "outbound",
                                    "segments": [
                                        {"origin": "SVX", "destination": "LED"}
                                    ],
                                },
                                {
                                    "direction": "return",
                                    "segments": [
                                        {"origin": "LED", "destination": "SVO"},
                                        {"origin": "SVO", "destination": "SVX"},
                                    ],
                                },
                            ],
                            "journey_scope": "round_trip",
                        }
                    ],
                }
            ],
            gateway_leg_results={},
            direct_mode={"outbound": True},
            requested_origin="SVX",
            requested_destination="LED",
        )

        self.assertEqual(len(graph["offers"]), 1)
        self.assertEqual(len(graph["edges"]), 3)
        envelope = materialize_offer_graph_candidates(
            graph,
            direct_mode={"outbound": True},
            requested_origin="SVX",
            requested_destination="LED",
        )
        self.assertEqual(len(envelope["candidates"]), 1)

    def test_direct_mode_uses_catalog_airport_scope_without_city_code_tables(
        self,
    ) -> None:
        origin_airports = ["AAA", "AAB"]
        destination_airports = ["BBA", "BBB", "BBC"]
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "outbound",
                    "origin": "AAA",
                    "destination": "BBB",
                    "top_offers": [
                        {
                            "id": "catalog-city-direct",
                            "price": 100,
                            "currency": "RUB",
                            "segments": [{"origin": "AAB", "destination": "BBC"}],
                        }
                    ],
                }
            ],
            direct_mode={"outbound": True},
            requested_origin="AAA",
            requested_destination="BBB",
            requested_origin_airports=origin_airports,
            requested_destination_airports=destination_airports,
        )

        self.assertEqual(len(graph["offers"]), 1)
        envelope = materialize_offer_graph_candidates(
            graph,
            direct_mode={"outbound": True},
            requested_origin="AAA",
            requested_destination="BBB",
            requested_origin_airports=origin_airports,
            requested_destination_airports=destination_airports,
        )
        self.assertEqual(len(envelope["candidates"]), 1)
        self.assertTrue(envelope["candidates"][0]["covers_requested_trip"])

    def test_direct_mode_gate_rejects_gateway_candidates_on_materialize(self) -> None:
        graph = self.graph_with_provider_and_gateway()

        envelope = materialize_offer_graph_candidates(
            graph,
            direct_mode={"outbound": True},
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertTrue(
            all(
                candidate["source_type"] != "gateway_separate_ticket"
                for candidate in envelope["candidates"]
            )
        )
        self.assertTrue(
            any(item["reason"] == "direct_mode_gate" for item in envelope["rejected"])
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
        self.assertEqual(candidate["source_providers"], ["kupibilet", "tutu"])
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

    def test_same_provider_itinerary_keeps_cheaper_offer_before_limit(self) -> None:
        segments = [
            {
                "origin": "SVX",
                "destination": "IST",
                "departure_at": "2026-08-15T10:00:00+05:00",
                "arrival_at": "2026-08-15T13:00:00+03:00",
            },
            {
                "origin": "IST",
                "destination": "AMS",
                "departure_at": "2026-08-15T15:00:00+03:00",
                "arrival_at": "2026-08-15T17:30:00+02:00",
            },
        ]
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "provider": provider,
                    "top_offers": [
                        {
                            "id": f"{provider}-offer",
                            "price": price,
                            "currency": "RUB",
                            "segments": segments,
                        }
                    ],
                }
                for provider, price in (("tutu", 45000), ("kupibilet", 39000))
            ],
            gateway_leg_results={},
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        self.assertEqual(envelope["coverage"]["deduped_count"], 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["provider"], "kupibilet")
        self.assertEqual(candidate["price"], 39000)
        self.assertEqual(candidate["source_providers"], ["kupibilet", "tutu"])
        self.assertEqual(candidate["alternate_sources"][0]["price"], 45000)

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

    def test_same_physical_itinerary_without_flight_numbers_dedupes(self) -> None:
        envelope = materialize_offer_graph_candidates(
            self.graph_with_provider_and_gateway(
                provider_first_flight_number=None,
                provider_second_flight_number=None,
                gateway_first_flight_number=None,
                gateway_second_flight_number=None,
            ),
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        self.assertEqual(envelope["coverage"]["deduped_count"], 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["source_type"], "provider_full_route")
        self.assertEqual(len(candidate["alternate_sources"]), 1)
        self.assertEqual(
            candidate["alternate_sources"][0]["source_type"],
            "gateway_separate_ticket",
        )

    def test_same_physical_itinerary_with_different_flight_numbers_dedupes(
        self,
    ) -> None:
        envelope = materialize_offer_graph_candidates(
            self.graph_with_provider_and_gateway(
                provider_first_flight_number="U6 123",
                provider_second_flight_number="TK 1953",
                gateway_first_flight_number="DP 777",
                gateway_second_flight_number="PC 888",
            ),
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 1)
        self.assertEqual(envelope["coverage"]["deduped_count"], 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["source_type"], "provider_full_route")
        self.assertEqual(candidate["price_basis"], "provider_offer_price")
        self.assertEqual(len(candidate["alternate_sources"]), 1)

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

    def test_duplicate_connection_does_not_duplicate_path_candidate(
        self,
    ) -> None:
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
        self.assertEqual(envelope["coverage"]["deduped_count"], 1)
        self.assertEqual(len(candidate["alternate_sources"]), 1)
        self.assertEqual(
            candidate["alternate_sources"][0]["source_type"],
            "gateway_separate_ticket",
        )


if __name__ == "__main__":
    unittest.main()
