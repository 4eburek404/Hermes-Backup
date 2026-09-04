from __future__ import annotations

import unittest

from flights_cli.contracts.registry import current_contract
from flights_cli.contracts.validation import validate_user_answer
from flights_cli.reporting.catalog_projection import catalog_item
from flights_cli.reporting.catalog_rendering import answer_display_lines_for_item
from flights_cli.reporting.user_answer import (
    build_user_answer,
    render_user_answer,
)
from tests.fixtures.result_fixtures import (
    answer_input_from_fixture,
    report_with_required_caveats,
)


def _segment(direction: str, origin: str, destination: str, flight_number: str) -> dict:
    return {
        "direction": direction,
        "origin": origin,
        "destination": destination,
        "flight_number": flight_number,
        "carrier": flight_number[:2],
        "departure_at": "2026-09-10T07:00:00+05:00",
        "arrival_at": "2026-09-10T07:50:00+03:00",
        "duration_min": 170,
    }


def _non_stop_round_trip_pair() -> dict:
    """A round trip summed from two non-stop one-way offers, as Tutu returns it."""

    return {
        "id": "round-trip-pair:outbound-1:return-1",
        "source_type": "provider_full_route",
        "provider": "tutu",
        "source_providers": ["tutu"],
        "journey_scope": "round_trip",
        "covers_requested_trip": True,
        "ticketing_model": "one_way_sum",
        "detail_status": "full",
        "price": {"amount": 24_300, "currency": "RUB"},
        "price_basis": "summed_one_way_prices",
        "max_connections_per_journey": 0,
        "ticket_protection": {
            "status": "unprotected",
            "source": "separate_ticket_boundary",
            "reasons": ["separate_tickets"],
        },
        "segments": [
            _segment("outbound", "SVX", "SVO", "DP6544"),
            _segment("return", "SVO", "SVX", "DP6541"),
        ],
    }


class UserAnswerModuleTests(unittest.TestCase):
    def test_build_user_answer_produces_valid_deterministic_output(self) -> None:
        report = report_with_required_caveats()
        answer_input = answer_input_from_fixture(report)
        answer = build_user_answer(answer_input)

        validate_user_answer(answer)
        self.assertEqual(
            answer["schema_version"], current_contract("user_answer")["schema_version"]
        )
        self.assertEqual(
            answer["rendered_text"],
            render_user_answer(answer, answer_input.route),
        )

    def test_authoritative_protected_ticket_status_is_only_projected(self) -> None:
        for ticketing_model in ("single_pnr_proven", "protected_provider_order"):
            with self.subTest(ticketing_model=ticketing_model):
                item = catalog_item(
                    {
                        "id": f"protected-{ticketing_model}",
                        "source_type": "provider_full_route",
                        "provider": "fake",
                        "journey_scope": "round_trip",
                        "ticketing_model": ticketing_model,
                        "ticket_protection": {
                            "status": "protected",
                            "source": "provider_proof",
                            "reasons": [],
                        },
                        "price": {"amount": 20_000, "currency": "RUB"},
                        "segments": [],
                    },
                    number=1,
                    is_round_trip_request=True,
                )

                self.assertEqual(item["ticketing_model"], "single_ticket_proven")
                self.assertEqual(item["ticket_protection"]["status"], "protected")
                self.assertIs(item["protection"]["self_transfer"], False)
                self.assertNotIn("self_transfer", item["badges"])
                self.assertNotIn(
                    "Отдельные билеты:", "\n".join(answer_display_lines_for_item(item))
                )

    def test_round_trip_single_ticket_requires_proof_but_is_not_self_transfer(
        self,
    ) -> None:
        item = catalog_item(
            {
                "id": "round-trip-single-ticket",
                "source_type": "provider_full_route",
                "provider": "fake",
                "journey_scope": "round_trip",
                "ticketing_model": "round_trip_single_ticket",
                "price": {"amount": 20_000, "currency": "RUB"},
                "segments": [],
            },
            number=1,
            is_round_trip_request=True,
        )

        self.assertEqual(item["ticketing_model"], "provider_aggregate")
        self.assertEqual(item["ticket_protection"]["status"], "unknown")
        self.assertIs(item["protection"]["self_transfer"], False)
        self.assertNotIn("self_transfer", item["badges"])
        self.assertNotIn(
            "Отдельные билеты:", "\n".join(answer_display_lines_for_item(item))
        )

    def test_non_stop_round_trip_pair_drops_transfer_only_warnings(self) -> None:
        item = catalog_item(
            _non_stop_round_trip_pair(),
            number=1,
            is_round_trip_request=True,
        )

        self.assertEqual(item["ticketing_model"], "separate_one_way_offers")
        self.assertEqual(item["protection"]["through_baggage_status"], "not_applicable")
        self.assertIs(item["protection"]["self_transfer"], False)
        self.assertNotIn("through_baggage_unproven", item["badges"])
        self.assertNotIn("self_transfer", item["badges"])
        self.assertNotIn(
            "Отдельные билеты:", "\n".join(answer_display_lines_for_item(item))
        )
        source_note = item["caveats"][0]
        self.assertNotIn("сквозной багаж и защищённый round-trip", source_note)
        self.assertIn("пересадок нет", source_note)

    def test_non_stop_round_trip_pair_still_reports_separate_tickets(self) -> None:
        item = catalog_item(
            _non_stop_round_trip_pair(),
            number=1,
            is_round_trip_request=True,
        )

        self.assertIn("separate_one_way_offers", item["badges"])
        self.assertIn("single_pnr_unproven", item["badges"])
        self.assertEqual(item["protection"]["single_pnr_status"], "unproven")
        self.assertIn("разными билетами", item["caveats"][0])

    def test_single_non_stop_offer_has_no_ticketing_protection_warning(self) -> None:
        item = catalog_item(
            {
                "id": "provider-aggregate:outbound:1",
                "source_type": "provider_full_route",
                "provider": "tutu",
                "source_providers": ["tutu"],
                "journey_scope": "one_way",
                "ticketing_model": "provider_order_unverified",
                "detail_status": "full",
                "price": {"amount": 12_500, "currency": "RUB"},
                "price_basis": "provider_offer_price",
                "max_connections_per_journey": 0,
                "segments": [_segment("outbound", "SVX", "SVO", "DP6544")],
            },
            number=1,
            is_round_trip_request=False,
        )

        self.assertEqual(item["protection"]["single_pnr_status"], "not_applicable")
        self.assertEqual(item["protection"]["through_baggage_status"], "not_applicable")
        self.assertNotIn("single_pnr_unproven", item["badges"])
        self.assertNotIn("through_baggage_unproven", item["badges"])
        self.assertNotIn(
            "single PNR/protection not proven; verify on booking screen",
            item["caveats"],
        )

    def test_connecting_itinerary_keeps_transfer_protection_warnings(self) -> None:
        option = _non_stop_round_trip_pair()
        option["segments"] = [
            _segment("outbound", "SVX", "SVO", "SU1419"),
            _segment("outbound", "SVO", "DEL", "SU232"),
            _segment("return", "DEL", "SVX", "SU233"),
        ]
        option["max_connections_per_journey"] = 1

        item = catalog_item(option, number=1, is_round_trip_request=True)

        self.assertEqual(item["protection"]["through_baggage_status"], "unproven")
        self.assertIn("through_baggage_unproven", item["badges"])
        self.assertIn("single_pnr_unproven", item["badges"])
        self.assertIn("self_transfer", item["badges"])
        self.assertIn("сквозной багаж", item["caveats"][0])

    def test_itinerary_without_visible_segments_stays_conservative(self) -> None:
        option = _non_stop_round_trip_pair()
        option["segments"] = []
        option["detail_status"] = "summary_only"

        item = catalog_item(option, number=1, is_round_trip_request=True)

        self.assertEqual(item["protection"]["through_baggage_status"], "unproven")
        self.assertIn("through_baggage_unproven", item["badges"])
        self.assertIn("сквозной багаж", item["caveats"][0])

    def test_not_applicable_protection_satisfies_the_answer_contract(self) -> None:
        report = report_with_required_caveats()
        report["primary_options"] = [_non_stop_round_trip_pair()]
        report["alternative_options"] = []
        answer = build_user_answer(answer_input_from_fixture(report))

        validate_user_answer(answer)
        item = answer["catalog"]["items"][0]
        self.assertEqual(item["protection"]["through_baggage_status"], "not_applicable")

    def test_catalog_renderer_does_not_recompute_ticket_semantics(self) -> None:
        lines = answer_display_lines_for_item(
            {
                "number": 1,
                "total_price": {"amount": 20_000, "currency": "RUB"},
                "directions": {"outbound": None, "return": None},
                "badges": [],
                "caveats": [],
                "protection": {"self_transfer": True},
                "ticket_protection": {"status": "unprotected"},
            }
        )

        self.assertNotIn("Отдельные билеты:", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
