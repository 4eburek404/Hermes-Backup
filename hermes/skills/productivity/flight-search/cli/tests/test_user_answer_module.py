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
