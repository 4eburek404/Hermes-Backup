from __future__ import annotations

import copy
import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from flights_cli.errors import CliError
from flights_cli.reporting.user_answer import (
    USER_ANSWER_SCHEMA_PACKAGE,
    USER_ANSWER_SCHEMA_RESOURCE,
    USER_ANSWER_SCHEMA_VERSION,
    build_user_answer,
    load_user_answer_schema,
    validate_user_answer,
)
from tests.test_agent_report_contract import valid_option, valid_report


class CatalogAnswerContractTests(unittest.TestCase):
    def _round_trip_option(self, option_id: str, *, price: int = 10000) -> dict:
        option = copy.deepcopy(valid_option())
        option.update(
            {
                "id": option_id,
                "category": "assembled_round_trip_control",
                "price": {"amount": price, "currency": "RUB"},
                "price_text": f"{price:,} RUB".replace(",", " "),
                "journey_scope": "round_trip",
                "covers_requested_trip": True,
                "ticketing_model": "separate_segments",
            }
        )
        option["segments"] = [
            {
                "direction": "outbound",
                "flight_number": "SU100",
                "carrier": "SU",
                "origin": "SVX",
                "destination": "SVO",
                "departure_at": "2026-07-14T06:00:00+05:00",
                "arrival_at": "2026-07-14T06:45:00+03:00",
                "duration_min": 165,
            },
            {
                "direction": "outbound",
                "flight_number": "SU220",
                "carrier": "SU",
                "origin": "SVO",
                "destination": "CAN",
                "departure_at": "2026-07-14T19:10:00+03:00",
                "arrival_at": "2026-07-15T09:35:00+08:00",
                "duration_min": 565,
            },
            {
                "direction": "return",
                "flight_number": "SU221",
                "carrier": "SU",
                "origin": "CAN",
                "destination": "SVO",
                "departure_at": "2026-07-25T11:20:00+08:00",
                "arrival_at": "2026-07-25T16:05:00+03:00",
                "duration_min": 585,
            },
            {
                "direction": "return",
                "flight_number": "SU1406",
                "carrier": "SU",
                "origin": "SVO",
                "destination": "SVX",
                "departure_at": "2026-07-25T20:10:00+03:00",
                "arrival_at": "2026-07-26T00:35:00+05:00",
                "duration_min": 145,
            },
        ]
        return option

    def _round_trip_report(self) -> dict:
        report = valid_report()
        report["route"] = {
            **report["route"],
            "origin": "SVX",
            "destination": "CAN",
            "dates": {"depart_date": "2026-07-14", "return_date": "2026-07-25"},
        }
        report["recommended_options"] = [self._round_trip_option("assembled-primary", price=92248)]
        report["priority_options"] = [self._round_trip_option("assembled-alt", price=90142)]
        return report

    def test_v3_schema_declares_catalog_contract(self) -> None:
        schema = load_user_answer_schema()
        text = resources.files(USER_ANSWER_SCHEMA_PACKAGE).joinpath(USER_ANSWER_SCHEMA_RESOURCE).read_text(encoding="utf-8")
        parsed = json.loads(text)

        Draft202012Validator.check_schema(schema)
        self.assertEqual(USER_ANSWER_SCHEMA_VERSION, "flight_search_user_answer.v3")
        self.assertEqual(USER_ANSWER_SCHEMA_RESOURCE, "flight_search_user_answer.v3.schema.json")
        self.assertEqual(parsed["$id"], "urn:hermes:flights-cli:flight-search-user-answer:v3")
        expected_keys = {
            "schema_version",
            "answer_mode",
            "route",
            "catalog",
            "primary_recommendation",
            "alternatives",
            "evidence_status",
            "required_caveats",
            "rendered_text",
            "answer_lines",
            "stop_policy_status",
        }
        self.assertEqual(set(schema["required"]), expected_keys)
        self.assertEqual(set(schema["properties"]), expected_keys)
        self.assertEqual(schema["properties"]["schema_version"]["const"], USER_ANSWER_SCHEMA_VERSION)
        self.assertLessEqual(len(text.encode("utf-8")), 20000)

    def test_round_trip_options_render_as_numbered_catalog_contract(self) -> None:
        answer = build_user_answer(self._round_trip_report())

        validate_user_answer(answer)
        expected_keys = {
            "schema_version",
            "answer_mode",
            "route",
            "catalog",
            "primary_recommendation",
            "alternatives",
            "evidence_status",
            "required_caveats",
            "rendered_text",
            "answer_lines",
            "stop_policy_status",
        }
        self.assertEqual(set(answer), expected_keys)
        self.assertEqual(answer["schema_version"], "flight_search_user_answer.v3")
        self.assertEqual(answer["answer_mode"], "catalog")
        self.assertEqual(answer["catalog"]["presentation"], {"style": "numbered_compact", "language": "ru", "max_items": 10})
        self.assertEqual([item["number"] for item in answer["catalog"]["items"]], [1, 2])
        self.assertEqual(answer["catalog"]["items"][0]["option_id"], "assembled-primary")
        self.assertTrue(answer["catalog"]["items"][0]["covers_requested_trip"])
        self.assertEqual(answer["catalog"]["items"][0]["journey_scope"], "round_trip")
        self.assertEqual(answer["catalog"]["items"][0]["directions"]["outbound"]["segments"][0]["flight_number"], "SU100")
        self.assertEqual(answer["catalog"]["items"][0]["directions"]["return"]["segments"][0]["flight_number"], "SU221")
        self.assertIn("single_pnr_unproven", answer["catalog"]["items"][0]["badges"])
        self.assertIn("1.", answer["rendered_text"])
        self.assertIn("2.", answer["rendered_text"])
        self.assertIn("14.07", answer["rendered_text"])
        self.assertIn("25.07", answer["rendered_text"])
        self.assertEqual(
            answer["catalog"]["items"][0]["render_line"],
            "1. 92 248 руб | туда: SU100 SVX→SVO 14.07 06:00–06:45 -> "
            "SU220 SVO→CAN 14.07 19:10–15.07 09:35 | обратно: "
            "SU221 CAN→SVO 25.07 11:20–16:05 -> SU1406 SVO→SVX 25.07 20:10–26.07 00:35",
        )

    def test_rejects_catalog_when_rendered_text_loses_numbered_items(self) -> None:
        answer = build_user_answer(self._round_trip_report())
        answer["rendered_text"] = "Нашёл варианты SVX→CAN без нумерованного каталога."
        answer["answer_lines"] = [answer["rendered_text"]]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("numbered catalog", messages)
    def test_rejects_legacy_v2_user_answer_without_adapter(self) -> None:
        legacy = build_user_answer(self._round_trip_report())
        legacy["schema_version"] = "flight_search_user_answer.v2"
        legacy.pop("answer_mode")
        legacy.pop("catalog")

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(legacy)

        self.assertEqual(ctx.exception.details["schema_version"], "flight_search_user_answer.v2")
        self.assertTrue(
            any(
                error["path"] == "$.schema_version" and error["validator"] == "const"
                for error in ctx.exception.details["errors"]
            )
        )


if __name__ == "__main__":
    unittest.main()
