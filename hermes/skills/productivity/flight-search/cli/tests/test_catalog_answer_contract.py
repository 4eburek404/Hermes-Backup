from __future__ import annotations

import copy
import json
import re
import unittest
from importlib import resources
from unittest.mock import patch

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


def semantic_error_paths(exc: CliError) -> set[str]:
    return {
        str(error.get("path"))
        for error in (exc.details or {}).get("errors") or []
        if isinstance(error, dict) and error.get("validator") == "semantic"
    }


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
                "arrival_terminal": "B",
                "departure_at": "2026-07-14T06:00:00+05:00",
                "arrival_at": "2026-07-14T06:45:00+03:00",
                "aircraft_code": "32A",
                "duration_min": 165,
            },
            {
                "direction": "outbound",
                "flight_number": "SU220",
                "carrier": "SU",
                "origin": "SVO",
                "destination": "CAN",
                "departure_terminal": "C",
                "departure_at": "2026-07-14T19:10:00+03:00",
                "arrival_at": "2026-07-15T09:35:00+08:00",
                "aircraft_code": "333",
                "duration_min": 565,
            },
            {
                "direction": "return",
                "flight_number": "SU221",
                "carrier": "SU",
                "origin": "CAN",
                "destination": "SVO",
                "arrival_terminal": "C",
                "departure_at": "2026-07-25T11:20:00+08:00",
                "arrival_at": "2026-07-25T16:05:00+03:00",
                "aircraft_code": "333",
                "duration_min": 585,
            },
            {
                "direction": "return",
                "flight_number": "SU1406",
                "carrier": "SU",
                "origin": "SVO",
                "destination": "SVX",
                "departure_terminal": "B",
                "departure_at": "2026-07-25T20:10:00+03:00",
                "arrival_at": "2026-07-26T00:35:00+05:00",
                "aircraft_code": "73H",
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
        report["recommended_options"] = [
            self._round_trip_option("assembled-primary", price=92248)
        ]
        report["priority_options"] = [
            self._round_trip_option("assembled-alt", price=90142)
        ]
        return report

    def test_v6_schema_declares_catalog_contract(self) -> None:
        schema = load_user_answer_schema()
        text = (
            resources.files(USER_ANSWER_SCHEMA_PACKAGE)
            .joinpath(USER_ANSWER_SCHEMA_RESOURCE)
            .read_text(encoding="utf-8")
        )
        parsed = json.loads(text)

        Draft202012Validator.check_schema(schema)
        self.assertEqual(USER_ANSWER_SCHEMA_VERSION, "flight_search_user_answer.v6")
        self.assertEqual(
            USER_ANSWER_SCHEMA_RESOURCE, "flight_search_user_answer.v6.schema.json"
        )
        self.assertEqual(
            parsed["$id"], "urn:hermes:flights-cli:flight-search-user-answer:v6"
        )
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
            "constraint_conflict",
        }
        self.assertEqual(set(schema["required"]), expected_keys)
        self.assertEqual(set(schema["properties"]), expected_keys)
        self.assertEqual(
            schema["properties"]["schema_version"]["const"], USER_ANSWER_SCHEMA_VERSION
        )
        self.assertLessEqual(len(text.encode("utf-8")), 20000)

    def test_round_trip_options_render_as_numbered_catalog_contract(self) -> None:
        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {
                "SVX": "Екатеринбург",
                "SVO": "Москва",
                "CAN": "Гуанчжоу",
            }.get(code, code),
            create=True,
        ):
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
            "constraint_conflict",
        }
        self.assertEqual(set(answer), expected_keys)
        self.assertEqual(answer["schema_version"], "flight_search_user_answer.v6")
        self.assertEqual(answer["answer_mode"], "catalog")
        self.assertEqual(
            answer["catalog"]["presentation"],
            {
                "style": "numbered_inline_itinerary_v1",
                "language": "ru",
                "max_items": 10,
            },
        )
        self.assertEqual(
            [item["number"] for item in answer["catalog"]["items"]], [1, 2]
        )
        self.assertEqual(
            answer["catalog"]["items"][0]["option_id"], "assembled-primary"
        )
        self.assertTrue(answer["catalog"]["items"][0]["covers_requested_trip"])
        self.assertEqual(answer["catalog"]["items"][0]["journey_scope"], "round_trip")
        self.assertEqual(
            answer["catalog"]["items"][0]["directions"]["outbound"]["segments"][0][
                "flight_number"
            ],
            "SU100",
        )
        self.assertEqual(
            answer["catalog"]["items"][0]["directions"]["return"]["segments"][0][
                "flight_number"
            ],
            "SU221",
        )
        self.assertEqual(
            answer["catalog"]["items"][0]["agent_display"]["style"],
            "canonical_segment_line_v1",
        )
        self.assertIn("single_pnr_unproven", answer["catalog"]["items"][0]["badges"])
        self.assertEqual(
            answer["catalog"]["items"][0]["agent_display"]["text"],
            answer["catalog"]["items"][0]["render_line"],
        )
        self.assertEqual(
            [
                segment["flight_number"]
                for segment in answer["catalog"]["items"][0]["directions"]["outbound"][
                    "segments"
                ]
            ],
            ["SU100", "SU220"],
        )
        self.assertEqual(
            [
                segment["flight_number"]
                for segment in answer["catalog"]["items"][0]["directions"]["return"][
                    "segments"
                ]
            ],
            ["SU221", "SU1406"],
        )
        self.assertNotIn("1.\n", answer["catalog"]["items"][0]["agent_display"]["text"])

    def test_city_scope_endpoint_renders_actual_multi_airport_and_terminal(
        self,
    ) -> None:
        report = valid_report()
        report["route"] = {
            **report["route"],
            "origin": "MOW",
            "destination": "MCT",
            "dates": {"depart_date": "2026-09-05", "return_date": "2026-09-08"},
        }
        option = copy.deepcopy(valid_option())
        option.update(
            {
                "id": "assembled-svo-mct",
                "category": "assembled_round_trip_control",
                "price": {"amount": 44001, "currency": "RUB"},
                "price_text": "44 001 RUB",
                "journey_scope": "round_trip",
                "covers_requested_trip": True,
                "ticketing_model": "separate_segments",
                "segments": [
                    {
                        "direction": "outbound",
                        "flight_number": "WY184",
                        "carrier": "WY",
                        "origin": "SVO",
                        "destination": "MCT",
                        "departure_terminal": "C",
                        "departure_at": "2026-09-05T22:05:00+03:00",
                        "arrival_at": "2026-09-06T05:25:00+04:00",
                        "aircraft_code": "7M8",
                        "duration_min": 380,
                    },
                    {
                        "direction": "return",
                        "flight_number": "WY183",
                        "carrier": "WY",
                        "origin": "MCT",
                        "destination": "SVO",
                        "arrival_terminal": "C",
                        "departure_at": "2026-09-08T15:55:00+04:00",
                        "arrival_at": "2026-09-08T21:05:00+03:00",
                        "aircraft_code": "7M8",
                        "duration_min": 370,
                    },
                ],
            }
        )
        report["recommended_options"] = [option]
        report["priority_options"] = []

        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {"MCT": "Маскат"}.get(code, code),
            create=True,
        ):
            answer = build_user_answer(report)
            validate_user_answer(answer)
        item = answer["catalog"]["items"][0]
        outbound = item["directions"]["outbound"]["segments"][0]
        returned = item["directions"]["return"]["segments"][0]
        self.assertEqual(
            (
                outbound["flight_number"],
                outbound["origin"],
                outbound["destination"],
                outbound["departure_terminal"],
            ),
            ("WY184", "SVO", "MCT", "C"),
        )
        self.assertEqual(
            (
                returned["flight_number"],
                returned["origin"],
                returned["destination"],
                returned["arrival_terminal"],
            ),
            ("WY183", "MCT", "SVO", "C"),
        )

    def test_segment_display_contract_renders_city_code_terminal_time_range_aircraft_duration(
        self,
    ) -> None:
        report = valid_report()
        report["route"] = {
            **report["route"],
            "origin": "NTE",
            "destination": "CDG",
            "dates": {"depart_date": "2026-07-09"},
        }
        option = copy.deepcopy(valid_option())
        option.update(
            {
                "id": "nte-cdg-display-contract",
                "price": {"amount": 12345, "currency": "RUB"},
                "price_text": "12 345 RUB",
                "journey_scope": "one_way",
                "covers_requested_trip": True,
                "segments": [
                    {
                        "direction": "outbound",
                        "flight_number": "AF7507",
                        "carrier": "AF",
                        "origin": "NTE",
                        "destination": "CDG",
                        "arrival_terminal": "2F",
                        "departure_at": "2026-07-09T18:45:00+02:00",
                        "arrival_at": "2026-07-09T19:55:00+02:00",
                        "aircraft_code": "320",
                        "duration_min": 110,
                    }
                ],
            }
        )
        report["recommended_options"] = [option]
        report["priority_options"] = []

        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {
                "NTE": "Нант",
                "CDG": "Париж",
            }.get(code, code),
            create=True,
        ):
            answer = build_user_answer(report)

        validate_user_answer(answer)
        first_line = answer["catalog"]["items"][0]["agent_display"]["lines"][0]
        self.assertEqual(
            first_line,
            "1. 09.07 Нант NTE → Париж CDG(2F) 18:45–19:55 борт A320 в пути 1ч 50мин",
        )
        self.assertIn(first_line, answer["rendered_text"])
        self.assertNotIn("CDG09.07", answer["rendered_text"])
        self.assertNotIn("NTE09.07", answer["rendered_text"])

    def test_rejects_catalog_when_segment_line_uses_legacy_inline_format(self) -> None:
        report = valid_report()
        report["route"] = {
            **report["route"],
            "origin": "NTE",
            "destination": "CDG",
            "dates": {"depart_date": "2026-07-09"},
        }
        option = copy.deepcopy(valid_option())
        option["segments"] = [
            {
                "direction": "outbound",
                "flight_number": "AF7507",
                "carrier": "AF",
                "origin": "NTE",
                "destination": "CDG",
                "arrival_terminal": "2F",
                "departure_at": "2026-07-09T18:45:00+02:00",
                "arrival_at": "2026-07-09T19:55:00+02:00",
                "aircraft_code": "320",
                "duration_min": 110,
            }
        ]
        report["recommended_options"] = [option]
        report["priority_options"] = []

        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {
                "NTE": "Нант",
                "CDG": "Париж",
            }.get(code, code),
            create=True,
        ):
            answer = build_user_answer(report)

        original_line = answer["catalog"]["items"][0]["agent_display"]["lines"][0]
        legacy_line = "1. AF7507 09.07 NTE - CDG 18:45 19:55 A320 в пути 1:50"
        answer["catalog"]["items"][0]["agent_display"]["lines"][0] = legacy_line
        answer["catalog"]["items"][0]["agent_display"]["text"] = "\n".join(
            answer["catalog"]["items"][0]["agent_display"]["lines"]
        )
        answer["catalog"]["items"][0]["render_line"] = answer["catalog"]["items"][0][
            "agent_display"
        ]["text"]
        answer["rendered_text"] = answer["rendered_text"].replace(
            original_line, legacy_line
        )
        answer["answer_lines"] = answer["rendered_text"].splitlines()

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.catalog.items[0].agent_display.lines",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_catalog_when_rendered_text_loses_numbered_items(self) -> None:
        answer = build_user_answer(self._round_trip_report())
        answer["rendered_text"] = "Нашёл варианты SVX→CAN без нумерованного каталога."
        answer["answer_lines"] = [answer["rendered_text"]]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn("$.rendered_text", semantic_error_paths(ctx.exception))

    def test_rejects_catalog_when_agent_display_drifts_from_render_line(self) -> None:
        answer = build_user_answer(self._round_trip_report())
        answer["catalog"]["items"][0]["agent_display"]["lines"] = [
            "1. BROKEN",
            "    92 248 рублей",
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.catalog.items[0].agent_display.lines",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_catalog_when_agent_display_segment_loses_aircraft_duration(
        self,
    ) -> None:
        answer = build_user_answer(self._round_trip_report())
        original_line = answer["catalog"]["items"][0]["agent_display"]["lines"][0]
        broken_line = re.sub(
            r" борт (?:[A-Z0-9][A-Z0-9-]*|н/д) в пути "
            r"(?:(?:\d+ч(?: \d+мин)?)|(?:\d+мин)|н/д)$",
            "",
            original_line,
        )
        answer["catalog"]["items"][0]["agent_display"]["lines"][0] = broken_line
        answer["catalog"]["items"][0]["agent_display"]["text"] = "\n".join(
            answer["catalog"]["items"][0]["agent_display"]["lines"]
        )
        answer["catalog"]["items"][0]["render_line"] = answer["catalog"]["items"][0][
            "agent_display"
        ]["text"]
        answer["rendered_text"] = answer["rendered_text"].replace(
            original_line, broken_line
        )

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.catalog.items[0].agent_display.lines[0]",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_catalog_when_layover_is_not_between_adjacent_segments(
        self,
    ) -> None:
        answer = build_user_answer(self._round_trip_report())
        item = answer["catalog"]["items"][0]
        original_block = item["render_line"]
        original_lines = item["agent_display"]["lines"]
        bad_lines = [
            original_lines[0],
            original_lines[2],
            original_lines[1],
            *original_lines[3:],
        ]
        item["agent_display"]["lines"] = bad_lines
        item["agent_display"]["text"] = "\n".join(bad_lines)
        item["render_line"] = item["agent_display"]["text"]
        answer["rendered_text"] = answer["rendered_text"].replace(
            original_block, item["render_line"]
        )
        answer["answer_lines"] = answer["rendered_text"].splitlines()

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.catalog.items[0].agent_display.lines",
            semantic_error_paths(ctx.exception),
        )

    def test_airport_label_removes_non_terminal_parentheses(self) -> None:
        option = self._round_trip_option("assembled-primary", price=92248)
        option["segments"][0]["destination"] = "IST"
        option["segments"][0]["arrival_terminal"] = None
        option["segments"][1]["origin"] = "IST"
        option["segments"][1]["departure_terminal"] = None
        report = self._round_trip_report()
        report["recommended_options"] = [option]
        report["priority_options"] = []

        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {
                "SVX": "Екатеринбург",
                "IST": "Стамбул",
                "CAN": "Гуанчжоу",
            }.get(code, code),
            create=True,
        ):
            answer = build_user_answer(report)
            validate_user_answer(answer)
        item = answer["catalog"]["items"][0]
        self.assertEqual(
            item["directions"]["outbound"]["segments"][0]["destination"], "IST"
        )
        self.assertEqual(item["directions"]["outbound"]["segments"][1]["origin"], "IST")
        self.assertNotIn("Новый (Стамбул)", answer["rendered_text"])

    def test_rejects_catalog_when_agent_display_uses_standalone_number_line(
        self,
    ) -> None:
        answer = build_user_answer(self._round_trip_report())
        first_line = answer["catalog"]["items"][0]["agent_display"]["lines"][0]
        answer["catalog"]["items"][0]["agent_display"]["lines"] = [
            "1.",
            first_line.removeprefix("1. "),
            *answer["catalog"]["items"][0]["agent_display"]["lines"][1:],
        ]
        answer["catalog"]["items"][0]["agent_display"]["text"] = "\n".join(
            answer["catalog"]["items"][0]["agent_display"]["lines"]
        )
        answer["catalog"]["items"][0]["render_line"] = answer["catalog"]["items"][0][
            "agent_display"
        ]["text"]
        answer["rendered_text"] = answer["rendered_text"].replace(
            first_line, "1.\n" + first_line.removeprefix("1. ")
        )

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.catalog.items[0].agent_display.lines[0]",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_legacy_v2_user_answer_without_adapter(self) -> None:
        legacy = build_user_answer(self._round_trip_report())
        legacy["schema_version"] = "flight_search_user_answer.v2"
        legacy.pop("answer_mode")
        legacy.pop("catalog")

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(legacy)

        self.assertEqual(
            ctx.exception.details["schema_version"], "flight_search_user_answer.v2"
        )
        self.assertTrue(
            any(
                error["path"] == "$.schema_version" and error["validator"] == "const"
                for error in ctx.exception.details["errors"]
            )
        )


if __name__ == "__main__":
    unittest.main()
