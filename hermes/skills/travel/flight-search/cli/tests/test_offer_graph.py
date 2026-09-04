from __future__ import annotations

import unittest

from flights_cli.contracts.validation import validate_contract_payload
from flights_cli.pipeline.offer_graph_builder import build_offer_graph
from flights_cli.pipeline.offer_graph_materializer import (
    materialize_offer_graph_candidates,
)
from flights_cli.pipeline.offer_graph_model import OFFER_GRAPH_SCHEMA_VERSION


def gateway_leg_result(
    *,
    leg: str,
    origin: str,
    destination: str,
    offer_id: str,
    departure_at: str,
    arrival_at: str,
) -> dict:
    return {
        "leg": leg,
        "origin": origin,
        "destination": destination,
        "provider": "tutu",
        "status": "ok",
        "execution_state": "searched",
        "offer_count": 1,
        "offers": [
            {
                "id": offer_id,
                "price": 10000,
                "currency": "RUB",
                "journeys": [
                    {
                        # A one-way provider labels every standalone query outbound.
                        "direction": "outbound",
                        "segments": [
                            {
                                "origin": origin,
                                "destination": destination,
                                "departure_at": departure_at,
                                "arrival_at": arrival_at,
                            }
                        ],
                    }
                ],
            }
        ],
    }


class OfferGraphTests(unittest.TestCase):
    def graph_with_two_provider_sources(
        self,
        *,
        provider_price: int = 39000,
        second_source_price: int = 40000,
        second_source_departure_at: str = "2026-08-15T15:00:00+03:00",
        provider_first_flight_number: str | None = "U6 123",
        provider_second_flight_number: str | None = "TK 1953",
        second_source_first_flight_number: str | None = "U6123",
        second_source_second_flight_number: str | None = "TK1953",
        with_direct_offer: bool = False,
    ) -> dict:
        """Один физический маршрут SVX-IST-AMS от двух провайдеров.

        Так выглядит `provider_policy: auto`: предложения обоих попадают в
        один граф и дедуплицируются по физическому маршруту.
        """

        direct_offers = (
            [
                {
                    "id": "kb-direct",
                    "price": 52000,
                    "currency": "RUB",
                    "segments": [
                        {
                            "origin": "SVX",
                            "destination": "AMS",
                            "flight_number": "KL 1234",
                            "departure_at": "2026-08-15T09:00:00+05:00",
                            "arrival_at": "2026-08-15T12:00:00+02:00",
                        }
                    ],
                }
            ]
            if with_direct_offer
            else []
        )
        return build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "origin": "SVX",
                    "destination": "AMS",
                    "top_offers": [
                        *direct_offers,
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
                        },
                    ],
                },
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "origin": "SVX",
                    "destination": "AMS",
                    "top_offers": [
                        {
                            "id": "tt-full-1",
                            "price": second_source_price,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "IST",
                                    "flight_number": second_source_first_flight_number,
                                    "departure_at": "2026-08-15T10:00:00+05:00",
                                    "arrival_at": "2026-08-15T13:00:00+03:00",
                                },
                                {
                                    "origin": "IST",
                                    "destination": "AMS",
                                    "flight_number": (
                                        second_source_second_flight_number
                                    ),
                                    "departure_at": second_source_departure_at,
                                    "arrival_at": "2026-08-15T17:30:00+02:00",
                                },
                            ],
                        }
                    ],
                },
            ],
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
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
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

    def test_result_direction_overrides_provider_one_way_journey_label(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "tutu",
                    "direction": "return",
                    "origin": "IST",
                    "destination": "SVX",
                    "top_offers": [
                        {
                            "id": "tutu-return-connected",
                            "price": 12000,
                            "currency": "RUB",
                            "journey_scope": "one_way",
                            "journeys": [
                                {
                                    "direction": "outbound",
                                    "segments": [
                                        {"origin": "IST", "destination": "AER"},
                                        {"origin": "AER", "destination": "SVX"},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        self.assertEqual(graph["offers"][0]["direction"], "return")
        self.assertEqual(
            [edge["direction"] for edge in graph["edges"]],
            ["return", "return"],
        )
        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="IST",
        )
        self.assertEqual(len(envelope["candidates"]), 1)
        candidate = envelope["candidates"][0]
        self.assertEqual(candidate["journeys"][0]["direction"], "return")
        self.assertTrue(candidate["covers_requested_trip"])
        self.assertEqual(envelope["rejected"], [])

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
        )

        self.assertEqual(len(graph["offers"]), 1)
        self.assertEqual(len(graph["edges"]), 2)
        self.assertNotIn(
            "direct_mode_gate", graph["coverage"].get("skipped_reasons", [])
        )
        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="LED",
        )
        self.assertEqual(envelope["coverage"]["candidate_count"], 1)

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

    def test_offer_departing_outside_requested_dates_is_rejected(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "AMS",
                    "date": "2026-08-16",
                    "top_offers": [
                        {
                            "id": "kb-right-day",
                            "price": 42000,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "AMS",
                                    "departure_at": "2026-08-16T08:00:00+05:00",
                                    "arrival_at": "2026-08-16T10:30:00+02:00",
                                }
                            ],
                        },
                        {
                            "id": "kb-next-day",
                            "price": 21000,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "AMS",
                                    "departure_at": "2026-08-17T08:00:00+05:00",
                                    "arrival_at": "2026-08-17T10:30:00+02:00",
                                }
                            ],
                        },
                    ],
                }
            ],
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
            requested_dates={"outbound": {"2026-08-16"}},
        )

        # Дешевле — не значит «то, что просили»: вылет на сутки позже
        # к путешественнику не едет.
        self.assertEqual(
            [candidate["id"] for candidate in envelope["candidates"]],
            ["candidate:primary_offer:kupibilet:kb-right-day"],
        )
        self.assertEqual(
            envelope["rejected"][0]["reason"], "departure_date_outside_request"
        )

    def test_date_window_keeps_every_probed_day(self) -> None:
        graph = build_offer_graph(
            primary_offer_results=[
                {
                    "role": "primary_offer_collection",
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "AMS",
                    "date": date_iso,
                    "top_offers": [
                        {
                            "id": f"kb-{date_iso}",
                            "price": 42000,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "AMS",
                                    "departure_at": f"{date_iso}T08:00:00+05:00",
                                    "arrival_at": f"{date_iso}T10:30:00+02:00",
                                }
                            ],
                        }
                    ],
                }
                for date_iso in ("2026-08-16", "2026-08-17", "2026-08-18")
            ],
        )

        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
            requested_dates={"outbound": {"2026-08-16", "2026-08-17", "2026-08-18"}},
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 3)
        self.assertEqual(envelope["rejected"], [])

    def test_direct_mode_gate_rejects_connected_primary_path_at_materialize(
        self,
    ) -> None:
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
        )

        self.assertEqual(len(graph["offers"]), 2)
        self.assertNotIn(
            "direct_mode_gate", graph["coverage"].get("skipped_reasons", [])
        )
        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="AMS",
        )
        self.assertEqual(
            [candidate["id"] for candidate in envelope["candidates"]],
            ["candidate:primary_offer:kupibilet:kb-direct"],
        )
        self.assertEqual(envelope["rejected"][0]["reason"], "direct_mode_gate")

    def test_direct_mode_gate_rejects_atomic_round_trip_when_gated_journey_connected(
        self,
    ) -> None:
        # Правило состава стоит на самих кандидатах: чтобы спрятать стыковку
        # на туда-плече, прямой рейс туда должен в выдаче быть.
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
                            "id": "tutu-direct-out",
                            "price": 18000,
                            "currency": "RUB",
                            "segments": [{"origin": "SVX", "destination": "LED"}],
                        },
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
                        },
                    ],
                }
            ],
        )

        self.assertEqual(len(graph["offers"]), 2)
        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="SVX",
            requested_destination="LED",
        )
        self.assertEqual(
            [candidate["id"] for candidate in envelope["candidates"]],
            ["candidate:primary_offer:tutu:tutu-direct-out"],
        )
        self.assertEqual(envelope["rejected"][0]["reason"], "direct_mode_gate")
        self.assertEqual(envelope["rejected"][0]["direction"], "outbound")

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
        )

        self.assertEqual(len(graph["offers"]), 1)
        self.assertEqual(len(graph["edges"]), 3)
        envelope = materialize_offer_graph_candidates(
            graph,
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
        )

        self.assertEqual(len(graph["offers"]), 1)
        envelope = materialize_offer_graph_candidates(
            graph,
            requested_origin="AAA",
            requested_destination="BBB",
            requested_origin_airports=origin_airports,
            requested_destination_airports=destination_airports,
        )
        self.assertEqual(len(envelope["candidates"]), 1)
        self.assertTrue(envelope["candidates"][0]["covers_requested_trip"])

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
            self.graph_with_two_provider_sources(),
            requested_origin="SVX",
            requested_destination="AMS",
        )

        # Дешёвый вариант выигрывает, дорогой остаётся альтернативным
        # источником: ни один провайдер не прячет предложение другого.
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
        self.assertEqual(alternate["source_type"], "provider_full_route")
        self.assertEqual(alternate["price"], 40000)
        self.assertEqual(alternate["price_basis"], "provider_offer_price")

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
            self.graph_with_two_provider_sources(
                second_source_departure_at="2026-08-15T16:00:00+03:00"
            ),
            requested_origin="SVX",
            requested_destination="AMS",
        )

        self.assertEqual(envelope["coverage"]["candidate_count"], 2)
        self.assertEqual(envelope["coverage"]["deduped_count"], 0)
        self.assertEqual(
            [candidate["source_type"] for candidate in envelope["candidates"]],
            ["provider_full_route", "provider_full_route"],
        )

    def test_same_physical_itinerary_without_flight_numbers_dedupes(self) -> None:
        envelope = materialize_offer_graph_candidates(
            self.graph_with_two_provider_sources(
                provider_first_flight_number=None,
                provider_second_flight_number=None,
                second_source_first_flight_number=None,
                second_source_second_flight_number=None,
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
            "provider_full_route",
        )

    def test_same_physical_itinerary_with_different_flight_numbers_dedupes(
        self,
    ) -> None:
        envelope = materialize_offer_graph_candidates(
            self.graph_with_two_provider_sources(
                provider_first_flight_number="U6 123",
                provider_second_flight_number="TK 1953",
                second_source_first_flight_number="DP 777",
                second_source_second_flight_number="PC 888",
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
