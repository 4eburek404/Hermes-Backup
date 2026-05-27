from __future__ import annotations

import copy
import unittest

from flights_cli.output import render_agent_report_human
from flights_cli.reporting.human_answer_renderer import build_human_answer
from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import validate_agent_report
from tests.test_agent_report_contract import valid_option, valid_report
from tests.test_provider_aggregate_candidates import report_payload


FORBIDDEN_DIAGNOSTIC_MARKERS = (
    "agent report:",
    "Best CLI-ranked option",
    "Coverage diagnostics",
    "coverage_diagnostics",
    "provider_aggregate_candidate",
    "provider-aggregate:",
    "probe_id",
    "rank=",
    "Kupibilet",
    "Travelpayouts",
)


def round_trip_option(option_id: str = "assembled-su-round-trip") -> dict:
    option = copy.deepcopy(valid_option())
    option.update(
        {
            "id": option_id,
            "price": {"amount": 33328, "currency": "RUB"},
            "price_text": "33 328 RUB",
            "elapsed_min": 690,
            "elapsed": "туда 5ч45; обратно 5ч45",
            "carriers": ["SU"],
            "max_connections_per_journey": 1,
            "journey_scope": "round_trip",
            "covers_requested_trip": True,
            "directional_only": False,
            "ticketing_model": "separate_segments",
            "segments": [
                {
                    "direction": "outbound",
                    "flight_number": "SU1437",
                    "carrier": "SU",
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "origin": "SVX",
                    "destination": "SVO",
                    "departure_at": "2026-08-01T18:10:00+05:00",
                    "arrival_at": "2026-08-01T18:55:00+03:00",
                    "duration_min": 165,
                },
                {
                    "direction": "outbound",
                    "flight_number": "SU1844",
                    "carrier": "SU",
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "origin": "SVO",
                    "destination": "MSQ",
                    "departure_at": "2026-08-01T20:35:00+03:00",
                    "arrival_at": "2026-08-01T21:55:00+03:00",
                    "duration_min": 80,
                },
                {
                    "direction": "return",
                    "flight_number": "SU1845",
                    "carrier": "SU",
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "origin": "MSQ",
                    "destination": "SVO",
                    "departure_at": "2026-08-08T09:40:00+03:00",
                    "arrival_at": "2026-08-08T11:05:00+03:00",
                    "duration_min": 85,
                },
                {
                    "direction": "return",
                    "flight_number": "SU1436",
                    "carrier": "SU",
                    "marketing_carrier": "SU",
                    "operating_carrier": "SU",
                    "origin": "SVO",
                    "destination": "SVX",
                    "departure_at": "2026-08-08T12:45:00+03:00",
                    "arrival_at": "2026-08-08T17:25:00+05:00",
                    "duration_min": 160,
                },
            ],
        }
    )
    return option


def directional_option(direction: str, option_id: str, price: str, first: str, second: str, *, layover_min: int) -> dict:
    option = copy.deepcopy(valid_option())
    if direction == "outbound":
        segments = [
            {
                "direction": "outbound",
                "flight_number": first,
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "SVO",
                "departure_at": "2026-08-01T00:40:00+05:00",
                "arrival_at": "2026-08-01T01:20:00+03:00",
                "duration_min": 160,
            },
            {
                "direction": "outbound",
                "flight_number": second,
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "MSQ",
                "departure_at": "2026-08-01T18:50:00+03:00",
                "arrival_at": "2026-08-01T20:10:00+03:00",
                "duration_min": 80,
            },
        ]
    else:
        segments = [
            {
                "direction": "return",
                "flight_number": first,
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "MSQ",
                "destination": "SVO",
                "departure_at": "2026-08-08T09:40:00+03:00",
                "arrival_at": "2026-08-08T11:05:00+03:00",
                "duration_min": 85,
            },
            {
                "direction": "return",
                "flight_number": second,
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "SVX",
                "departure_at": "2026-08-08T12:45:00+03:00",
                "arrival_at": "2026-08-08T17:25:00+05:00",
                "duration_min": 160,
            },
        ]
    option.update(
        {
            "id": option_id,
            "category": "provider_aggregate_candidate",
            "price_text": price,
            "price": {"amount": int("".join(price.split()[:-1])), "currency": "RUB"},
            "segments": segments,
            "journey_scope": "outbound_only" if direction == "outbound" else "return_only",
            "direction": direction,
            "directional_only": True,
            "covers_requested_trip": False,
            "max_connections_per_journey": 1,
            "itinerary_elapsed_min": None,
            "layover_total_min": layover_min,
            "ticketing_model": "provider_aggregate",
            "ticketing_note": "Provider aggregate offer; verify ticketing/protection, baggage, fare rules, and final fare on the booking screen.",
        }
    )
    return option


class HumanAnswerRendererTests(unittest.TestCase):
    def test_round_trip_answer_is_provider_neutral_traveler_text(self) -> None:
        report = valid_report()
        report["route"]["origin"] = "SVX"
        report["route"]["destination"] = "MSQ"
        report["route"]["dates"] = {"depart_date": "2026-08-01", "return_date": "2026-08-08"}
        report["recommended_options"] = [round_trip_option()]
        report["priority_options"] = [
            directional_option("outbound", "provider-aggregate:outbound:su-early", "17 650 RUB", "SU1419", "SU1832", layover_min=1050),
            directional_option("return", "provider-aggregate:return:su-midday", "16 664 RUB", "SU1845", "SU1436", layover_min=100),
        ]
        report["through_fare_checks"] = [
            {
                "direction": "round_trip",
                "route": "SVX->MSQ->SVX",
                "date": "2026-08-01/2026-08-08",
                "carrier": "SU",
                "reason": "same-carrier routing requires through-fare verification",
                "verify_with": ["booking screen", "fare rules"],
            }
        ]

        answer = build_human_answer(report)
        text = answer["text"]

        self.assertEqual(answer["format_version"], "flight_human_answer.v1")
        self.assertTrue(text.startswith("Нашёл варианты SVX→MSQ"))
        self.assertIn("**Лучшая пара / рекомендация**", text)
        self.assertIn("Туда: SU1437 18:10–18:55 → SU1844 20:35–21:55 | 01 авг | SVO 1ч40 | всего 5ч45 | 33 328 ₽", text)
        self.assertIn("Обратно: SU1845 09:40–11:05 → SU1436 12:45–17:25 | 08 авг | SVO 1ч40 | всего 5ч45 | 33 328 ₽", text)
        self.assertNotIn("SU1437→SU1844 | 01 авг 18:10–21:55", text)
        self.assertIn("**Альтернативы туда**", text)
        self.assertIn("33 328 ₽\n\n**Альтернативы туда**", text)
        self.assertIn("SU1419 00:40–01:20 → SU1832 18:50–20:10 | 01 авг | SVO 17ч30 | всего 21ч30 | 17 650 ₽ | длинная стыковка", text)
        self.assertIn("**Альтернативы обратно**", text)
        self.assertIn("SU1845 09:40–11:05 → SU1436 12:45–17:25 | 08 авг | SVO 1ч40 | всего 5ч45 | 16 664 ₽", text)
        self.assertIn("single PNR/багаж не доказаны", text)
        for marker in FORBIDDEN_DIAGNOSTIC_MARKERS:
            self.assertNotIn(marker, text)

    def test_later_segment_departure_date_is_visible_when_connection_crosses_midnight(self) -> None:
        report = valid_report()
        report["route"]["origin"] = "SVX"
        report["route"]["destination"] = "MSQ"
        report["recommended_options"] = [
            directional_option("outbound", "provider-aggregate:outbound:overnight", "17 650 RUB", "SU1419", "SU1832", layover_min=1950)
        ]
        report["recommended_options"][0]["segments"][1]["departure_at"] = "2026-08-02T09:50:00+03:00"
        report["recommended_options"][0]["segments"][1]["arrival_at"] = "2026-08-02T11:15:00+03:00"

        text = build_human_answer(report)["text"]

        self.assertIn("SU1419 00:40–01:20 → SU1832 02 авг 09:50–11:15", text)
        self.assertNotIn("SU1419 00:40–01:20 → SU1832 09:50–11:15 | 01 авг", text)

    def test_agent_report_attaches_human_answer_and_cli_human_render_uses_it(self) -> None:
        report = build_agent_report(report_payload())

        validate_agent_report(report)
        text = report["human_answer"]["text"]
        self.assertIn("Нашёл варианты SVX→DEL", text)
        self.assertNotIn("agent report:", render_agent_report_human(report))
        self.assertEqual(render_agent_report_human(report), text)


if __name__ == "__main__":
    unittest.main()
