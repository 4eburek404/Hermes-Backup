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
        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {
                "SVX": "Екатеринбург",
                "SVO": "Москва",
                "CAN": "Гуанчжоу",
            }.get(code, code),
            create=True,
        ), patch(
            "flights_cli.reporting.user_answer.airport_name_label",
            side_effect=lambda code: {
                "SVO": "Шереметьево",
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
        }
        self.assertEqual(set(answer), expected_keys)
        self.assertEqual(answer["schema_version"], "flight_search_user_answer.v3")
        self.assertEqual(answer["answer_mode"], "catalog")
        self.assertEqual(answer["catalog"]["presentation"], {"style": "numbered_inline_itinerary_v1", "language": "ru", "max_items": 10})
        self.assertEqual([item["number"] for item in answer["catalog"]["items"]], [1, 2])
        self.assertEqual(answer["catalog"]["items"][0]["option_id"], "assembled-primary")
        self.assertTrue(answer["catalog"]["items"][0]["covers_requested_trip"])
        self.assertEqual(answer["catalog"]["items"][0]["journey_scope"], "round_trip")
        self.assertEqual(answer["catalog"]["items"][0]["directions"]["outbound"]["segments"][0]["flight_number"], "SU100")
        self.assertEqual(answer["catalog"]["items"][0]["directions"]["return"]["segments"][0]["flight_number"], "SU221")
        self.assertEqual(answer["catalog"]["items"][0]["agent_display"]["style"], "inline_number_itinerary_with_aircraft_duration_v1")
        self.assertIn("single_pnr_unproven", answer["catalog"]["items"][0]["badges"])
        self.assertIn("1.", answer["rendered_text"])
        self.assertIn("2.", answer["rendered_text"])
        self.assertIn("14.07", answer["rendered_text"])
        self.assertIn("25.07", answer["rendered_text"])
        self.assertEqual(
            answer["catalog"]["items"][0]["render_line"],
            "1. SU100 14.07 Екатеринбург - Шереметьево(B) 06:00 06:45 A320 в пути 2:45\n"
            "    пересадка 12:25,\n"
            "    SU220 14.07 Шереметьево(C) - Гуанчжоу 19:10 09:35 (15.07) A333 в пути 9:25\n"
            "    SU221 25.07 Гуанчжоу - Шереметьево(C) 11:20 16:05 A333 в пути 9:45\n"
            "    пересадка 4:05,\n"
            "    SU1406 25.07 Шереметьево(B) - Екатеринбург 20:10 00:35 (26.07) B737 в пути 2:25\n"
            "    92 248 рублей",
        )
        self.assertEqual(answer["catalog"]["items"][0]["agent_display"]["text"], answer["catalog"]["items"][0]["render_line"])
        self.assertNotIn("1.\n", answer["catalog"]["items"][0]["agent_display"]["text"])

    def test_rejects_catalog_when_rendered_text_loses_numbered_items(self) -> None:
        answer = build_user_answer(self._round_trip_report())
        answer["rendered_text"] = "Нашёл варианты SVX→CAN без нумерованного каталога."
        answer["answer_lines"] = [answer["rendered_text"]]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("numbered catalog", messages)

    def test_rejects_catalog_when_agent_display_drifts_from_render_line(self) -> None:
        answer = build_user_answer(self._round_trip_report())
        answer["catalog"]["items"][0]["agent_display"]["lines"] = ["1. BROKEN", "    92 248 рублей"]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("agent_display.lines", messages)

    def test_rejects_catalog_when_agent_display_segment_loses_aircraft_duration(self) -> None:
        answer = build_user_answer(self._round_trip_report())
        original_line = answer["catalog"]["items"][0]["agent_display"]["lines"][0]
        broken_line = re.sub(r" (?:[A-Z0-9][A-Z0-9-]*|борт н/д) в пути (?:\d+:\d{2}|н/д)$", "", original_line)
        answer["catalog"]["items"][0]["agent_display"]["lines"][0] = broken_line
        answer["catalog"]["items"][0]["agent_display"]["text"] = "\n".join(
            answer["catalog"]["items"][0]["agent_display"]["lines"]
        )
        answer["catalog"]["items"][0]["render_line"] = answer["catalog"]["items"][0]["agent_display"]["text"]
        answer["rendered_text"] = answer["rendered_text"].replace(original_line, broken_line)

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("aircraft", messages)

    def test_rejects_catalog_when_layover_is_not_between_adjacent_segments(self) -> None:
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
        answer["rendered_text"] = answer["rendered_text"].replace(original_block, item["render_line"])
        answer["answer_lines"] = answer["rendered_text"].splitlines()

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("segment/layover/price", messages)

    def test_rejects_catalog_when_agent_display_uses_standalone_number_line(self) -> None:
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
        answer["catalog"]["items"][0]["render_line"] = answer["catalog"]["items"][0]["agent_display"]["text"]
        answer["rendered_text"] = answer["rendered_text"].replace(first_line, "1.\n" + first_line.removeprefix("1. "))

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("standalone", messages)

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
