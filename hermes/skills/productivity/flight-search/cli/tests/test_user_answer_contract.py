from __future__ import annotations

import copy
import json
import unittest
from importlib import resources
from unittest.mock import patch

from jsonschema import Draft202012Validator

from flights_cli.errors import CliError
from flights_cli.reporting.catalog_order import ordered_user_options
from flights_cli.reporting.user_answer import (
    USER_ANSWER_SCHEMA_PACKAGE,
    USER_ANSWER_SCHEMA_RESOURCE,
    USER_ANSWER_SCHEMA_VERSION,
    aircraft_display_label,
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


def report_with_required_caveats() -> dict:
    report = valid_report()
    priority = valid_option()
    priority["id"] = "priority-svo"
    priority["category"] = "moscow_gateway_control"
    report["priority_options"] = [priority]
    report["provider_failures"] = [
        {
            "direction": "outbound",
            "leg": "hub_to_destination",
            "origin": "IST",
            "destination": "LHR",
            "date": "2026-06-01",
            "provider": "fli",
            "error": {"type": "upstream_error", "message": "FLI MCP unavailable"},
        }
    ]
    report["through_fare_checks"] = [
        {
            "direction": "outbound",
            "route": "SVX->DEL",
            "date": "2026-06-01",
            "carrier": "SU",
            "reason": "Same-carrier route can indicate through-fare opportunity.",
            "verify_with": ["airline website", "booking screen fare rules"],
        }
    ]
    report["answer_lines"] = [
        "Best CLI-ranked option: 10 000 RUB risk=good/1 elapsed=2h.",
        "Provider failure: FLI failed on 1 segment search; first IST->LHR 2026-06-01: FLI MCP unavailable.",
        "Through-fare check required: verify SU SVX->DEL on airline/GDS before pricing it as separate legs.",
        "Coverage is incomplete: planned controls without terminal live evidence are not_executed, not no-flight evidence.",
        "Provider aggregate candidate: ticketing_protection=unknown; verify single-PNR/protection, baggage, fare rules, and final fare on the booking screen.",
        "Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.",
    ]
    return report


class FinalAnswerContractTests(unittest.TestCase):
    def _round_trip_option(self, option_id: str) -> dict:
        option = copy.deepcopy(valid_option())
        option["id"] = option_id
        option["category"] = "assembled_round_trip_control"
        option["segments"] = [
            {
                "direction": "outbound",
                "flight_number": "SU100",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "LHR",
                "departure_at": "2026-07-19T06:00:00+05:00",
                "arrival_at": "2026-07-19T08:00:00+01:00",
                "aircraft_code": "320",
                "duration_min": 360,
            },
            {
                "direction": "return",
                "flight_number": "SU101",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "LHR",
                "destination": "SVX",
                "departure_at": "2026-07-24T09:00:00+01:00",
                "arrival_at": "2026-07-24T19:00:00+05:00",
                "aircraft_code": "320",
                "duration_min": 360,
            },
        ]
        return option

    def _provider_aggregate_option(self, direction: str) -> dict:
        option = copy.deepcopy(valid_option())
        option["rank"] = None
        option["id"] = f"provider-aggregate:{direction}:agg-{direction}"
        option["category"] = "provider_aggregate_candidate"
        option["price_text"] = "21 208 RUB"
        option["elapsed"] = "9h05"
        option["risk"]["grade"] = None
        option["max_connections_per_journey"] = 1
        if direction == "outbound":
            option["segments"] = [
                {
                    "direction": "outbound",
                    "flight_number": "A1",
                    "carrier": "A",
                    "origin": "SVX",
                    "destination": "EVN",
                },
                {
                    "direction": "outbound",
                    "flight_number": "A2",
                    "carrier": "A",
                    "origin": "EVN",
                    "destination": "LTN",
                },
            ]
        else:
            option["segments"] = [
                {
                    "direction": "return",
                    "flight_number": "B1",
                    "carrier": "B",
                    "origin": "LGW",
                    "destination": "AYT",
                },
                {
                    "direction": "return",
                    "flight_number": "B2",
                    "carrier": "B",
                    "origin": "AYT",
                    "destination": "SVX",
                },
            ]
        return option

    def _two_one_way_pair_option(self) -> dict:
        option = copy.deepcopy(valid_option())
        option.update(
            {
                "rank": None,
                "id": "provider-aggregate:two-one-way-pair:agg-outbound+agg-return",
                "category": "provider_aggregate_candidate",
                "reason": "Two directional provider aggregate offers can be shown together for the requested round trip.",
                "detail_status": "summary_only",
                "price": {"amount": 64000, "currency": "RUB"},
                "price_text": "Sum of displayed one-way prices: 64 000 RUB",
                "elapsed_min": None,
                "elapsed": None,
                "outbound_time": {
                    "itinerary_elapsed_min": 660,
                    "flight_time_min": 300,
                    "layover_total_min": 360,
                },
                "return_time": {
                    "itinerary_elapsed_min": 570,
                    "flight_time_min": 440,
                    "layover_total_min": 130,
                },
                "risk": {
                    "score": None,
                    "grade": None,
                    "reject": None,
                    "top_reasons": [],
                },
                "validation_summary": {"candidate_type": "two_one_way_pair"},
                "stop_tier": "T1_ONE_STOP",
                "max_connections_per_journey": 1,
                "journey_scope": "two_one_way_pair",
                "covers_requested_trip": True,
                "direction": None,
                "directional_only": False,
                "composed_of_directional_offers": True,
                "ticketing_model": "separate_one_way_offers",
                "user_facing_label": (
                    "Two separate one-way offers: outbound SVX→LON 21 000 RUB + return LON→SVX 43 000 RUB. "
                    "Sum of displayed one-way prices: 64 000 RUB."
                ),
                "disclaimer": (
                    "Not proven as a single PNR, protected round-trip, baggage-through itinerary, through fare, or final fare. "
                    "Verify ticketing, baggage, refund, and disruption protection on the booking screen."
                ),
                "connections": [],
                "segments": [],
                "ticketing_note": "Two separate one-way offers; verify booking-screen ticketing and protection before purchase.",
            }
        )
        return option

    def _source_label_option(
        self,
        option_id: str,
        *,
        source_type: str,
        ticketing_model: str,
        price_basis: str,
        source_providers: list[str],
        gateway: str | None = None,
        direct: bool = False,
    ) -> dict:
        option = copy.deepcopy(valid_option())
        option.update(
            {
                "id": option_id,
                "category": source_type,
                "source_type": source_type,
                "provider": source_providers[0] if source_providers else None,
                "source_providers": source_providers,
                "gateway": gateway,
                "ticketing_model": ticketing_model,
                "price_basis": price_basis,
                "price": {"amount": 50000, "currency": "RUB"},
                "price_text": "50 000 RUB",
                "max_connections_per_journey": 0 if direct else 1,
                "segments": [
                    {
                        "direction": "outbound",
                        "flight_number": "U6001",
                        "carrier": "U6",
                        "origin": "SVX",
                        "destination": "AMS" if direct else gateway or "IST",
                        "departure_at": "2026-08-06T05:40:00+05:00",
                        "arrival_at": "2026-08-06T08:10:00+03:00",
                        "aircraft_code": "320",
                        "duration_min": 150,
                    }
                ],
            }
        )
        if not direct:
            option["segments"].append(
                {
                    "direction": "outbound",
                    "flight_number": "KL900",
                    "carrier": "KL",
                    "origin": gateway or "IST",
                    "destination": "AMS",
                    "departure_at": "2026-08-06T11:20:00+03:00",
                    "arrival_at": "2026-08-06T13:55:00+02:00",
                    "aircraft_code": "73H",
                    "duration_min": 215,
                }
            )
        return option

    def _source_label_answer(self, option: dict) -> dict:
        report = valid_report()
        report["route"] = {
            "origin": "SVX",
            "destination": "AMS",
            "origin_airports": ["SVX"],
            "destination_airports": ["AMS"],
            "dates": {"depart_date": "2026-08-06"},
            "profile": "business",
            "routing_strategy": "ru-priority",
            "provider_policy": "both",
        }
        report["recommended_options"] = [option]
        report["priority_options"] = []
        return build_user_answer(report)

    def _gateway_leg_results(
        self, *, viable: list[str], failed: list[str] | None = None
    ) -> dict:
        failed = failed or []
        gateways = []
        for index, code in enumerate(["IST", "SAW", "BEG", "DXB"], start=1):
            failures = (
                [
                    {
                        "gateway": code,
                        "provider": "fli",
                        "status": "error",
                        "probe_id": f"probe-{code.lower()}",
                        "error": {"type": "upstream_error"},
                    }
                ]
                if code in failed
                else []
            )
            gateways.append(
                {
                    "gateway": code,
                    "searched": True,
                    "viable": code in viable,
                    "origin_leg": {
                        "provider": "kupibilet",
                        "offer_count": 1,
                        "probe_id": f"probe-origin-{index}",
                    },
                    "destination_leg": {
                        "provider": "fli",
                        "offer_count": 1 if code in viable else 0,
                        "probe_id": f"probe-destination-{index}",
                    },
                    "provider_failures": failures,
                    "skipped_reasons": [],
                    "missing_legs": [] if code in viable else ["destination_leg"],
                }
            )
        for code in ["TBS", "EVN"]:
            gateways.append(
                {
                    "gateway": code,
                    "searched": False,
                    "viable": False,
                    "origin_leg": {"probe_id": f"probe-{code.lower()}-origin"},
                    "destination_leg": {
                        "probe_id": f"probe-{code.lower()}-destination"
                    },
                    "provider_failures": [],
                    "skipped_reasons": ["gateway_probe_budget_exhausted"],
                    "missing_legs": [],
                }
            )
        return {
            "searched_gateways": 4,
            "viable_gateways": len(viable),
            "failed_gateways": len(failed),
            "not_searched_budget": 2,
            "gateways": gateways,
        }

    def _report_with_gateway_coverage(
        self, *, viable: list[str], failed: list[str] | None = None
    ) -> dict:
        report = valid_report()
        report["route"] = {
            "origin": "SVX",
            "destination": "AMS",
            "origin_airports": ["SVX"],
            "destination_airports": ["AMS"],
            "dates": {"depart_date": "2026-08-06"},
            "profile": "business",
            "routing_strategy": "ru-priority",
            "provider_policy": "both",
        }
        report["primary_offer_results"] = [
            {
                "role": "primary_offer_collection",
                "provider": "kupibilet",
                "status": "ok",
                "execution_state": "searched",
                "offer_count": 3,
                "probe_id": "probe-full-route",
            }
        ]
        report["gateway_leg_results"] = self._gateway_leg_results(
            viable=viable, failed=failed
        )
        return report

    def _valid_round_trip_answer(self) -> dict:
        report = report_with_required_caveats()
        report["route"]["dates"] = {
            "depart_date": "2026-07-19",
            "return_date": "2026-07-24",
        }
        report["recommended_options"] = [self._round_trip_option("assembled-primary")]
        return build_user_answer(report)

    def _minimal_alternative(self, alternative_id: str, **overrides: object) -> dict:
        alternative = {
            "id": alternative_id,
            "category": "provider_aggregate_candidate",
            "price_text": "21 208 RUB",
            "elapsed": "9h05",
            "risk_grade": None,
            "segment_count": 2,
            "stop_tier": "T1_ONE_STOP",
            "max_connections_per_journey": 1,
        }
        alternative.update(overrides)
        return alternative

    def test_user_answer_schema_is_valid_package_resource(self) -> None:
        schema = load_user_answer_schema()
        text = (
            resources.files(USER_ANSWER_SCHEMA_PACKAGE)
            .joinpath(USER_ANSWER_SCHEMA_RESOURCE)
            .read_text(encoding="utf-8")
        )
        parsed = json.loads(text)

        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            parsed["$id"], "urn:hermes:flights-cli:flight-search-user-answer:v5"
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
        }
        self.assertEqual(set(schema["required"]), expected_keys)
        self.assertEqual(set(schema["properties"]), expected_keys)
        self.assertEqual(
            schema["properties"]["schema_version"]["const"], USER_ANSWER_SCHEMA_VERSION
        )
        self.assertIn("rendered_text", schema["required"])
        self.assertEqual(
            schema["properties"]["rendered_text"], {"type": "string", "minLength": 1}
        )
        self.assertLessEqual(len(text.encode("utf-8")), 20000)

    def test_builds_valid_user_answer_contract_from_agent_report(self) -> None:
        answer = build_user_answer(report_with_required_caveats())

        validate_user_answer(answer)
        self.assertEqual(answer["schema_version"], USER_ANSWER_SCHEMA_VERSION)
        self.assertEqual(answer["primary_recommendation"]["id"], "assembled-1:SVX-DEL")
        self.assertEqual(
            answer["primary_recommendation"]["max_connections_per_journey"], 0
        )
        self.assertEqual(answer["stop_policy_status"]["policy"], "business_default")
        self.assertEqual(answer["evidence_status"]["provider_failure_count"], 1)
        self.assertTrue(answer["evidence_status"]["execution_complete"])
        self.assertFalse(answer["evidence_status"]["evidence_complete"])
        self.assertFalse(answer["evidence_status"]["coverage_complete"])
        self.assertEqual(
            answer["evidence_status"]["answerability"], "answerable_with_caveats"
        )
        self.assertIn(
            "provider_failures", answer["evidence_status"]["blocking_evidence"]
        )
        self.assertEqual(
            answer["answer_lines"],
            [line for line in answer["rendered_text"].splitlines() if line.strip()],
        )
        self.assertTrue(answer["required_caveats"]["provider_failures_acknowledged"])
        self.assertTrue(
            answer["required_caveats"]["through_fare_verification_required"]
        )

    def test_rejects_metadata_only_direct_absence_claim(self) -> None:
        answer = build_user_answer(report_with_required_caveats())
        answer["evidence_status"]["non_blocking_boundaries"] = ["metadata_only"]
        answer["rendered_text"] = "Нет прямых рейсов SVX→LED."
        answer["answer_lines"] = [answer["rendered_text"]]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn("$.rendered_text", semantic_error_paths(ctx.exception))

    def test_rejects_metadata_only_direct_presence_claim(self) -> None:
        answer = build_user_answer(report_with_required_caveats())
        answer["evidence_status"]["non_blocking_boundaries"] = ["catalog_metadata"]
        answer["rendered_text"] = "Есть прямой рейс SVX→LED."
        answer["answer_lines"] = [answer["rendered_text"]]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn("$.rendered_text", semantic_error_paths(ctx.exception))

    def test_allows_metadata_boundary_without_availability_claim(self) -> None:
        answer = build_user_answer(report_with_required_caveats())
        answer["evidence_status"]["non_blocking_boundaries"] = ["catalog_metadata"]

        validate_user_answer(answer)

    def test_catalog_rendered_text_uses_traveler_line_format_without_raw_badges(
        self,
    ) -> None:
        report = valid_report()
        report["route"] = {
            "origin": "SVX",
            "destination": "LED",
            "dates": {"depart_date": "2026-08-06"},
        }
        direct = copy.deepcopy(valid_option())
        direct.update(
            {
                "id": "assembled-1:SVX-LED",
                "price": {"amount": 10179, "currency": "RUB"},
                "price_text": "10 179 RUB",
                "max_connections_per_journey": 0,
                "segments": [
                    {
                        "direction": "outbound",
                        "flight_number": "DP516",
                        "carrier": "DP",
                        "origin": "SVX",
                        "destination": "LED",
                        "departure_at": "2026-08-06T05:40:00+05:00",
                        "arrival_at": "2026-08-06T06:30:00+03:00",
                        "aircraft_code": "73H",
                        "duration_min": 170,
                    }
                ],
            }
        )
        second = copy.deepcopy(direct)
        second["id"] = "assembled-2:SVX-LED"
        second["rank"] = 2
        second["price"] = {"amount": 10404, "currency": "RUB"}
        second["price_text"] = "10 404 RUB"
        second["segments"][0]["flight_number"] = "5N502"
        second["segments"][0]["departure_at"] = "2026-08-06T07:15:00+05:00"
        second["segments"][0]["arrival_at"] = "2026-08-06T08:05:00+03:00"
        report["recommended_options"] = [direct, second]
        report["priority_options"] = []
        report["status"] = {"direct_mode": {"outbound": True}}
        report["offer_graph"]["truth_language"]["negative_wording"] = (
            "не нашёл в выполненных live/probe источниках; "
            "это не доказательство отсутствия вне границ источника"
        )

        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {
                "SVX": "Екатеринбург",
                "LED": "Санкт-Петербург",
            }.get(code, code),
            create=True,
        ):
            answer = build_user_answer(report)

        validate_user_answer(answer)
        self.assertEqual(answer["catalog"]["presentation"]["max_items"], 2)
        self.assertEqual(
            answer["catalog"]["items"][0]["agent_display"]["style"],
            "canonical_segment_line_v1",
        )
        self.assertEqual(
            [item["number"] for item in answer["catalog"]["items"]], [1, 2]
        )
        self.assertEqual(
            [
                item["directions"]["outbound"]["segments"][0]["flight_number"]
                for item in answer["catalog"]["items"]
            ],
            ["DP516", "5N502"],
        )
        for item in answer["catalog"]["items"]:
            self.assertEqual(item["agent_display"]["text"], item["render_line"])
            self.assertGreaterEqual(len(item["agent_display"]["lines"]), 2)
        self.assertNotIn("1.\n", answer["rendered_text"])
        self.assertNotIn("\n\n2.", answer["rendered_text"])
        self.assertNotIn(" | туда:", answer["rendered_text"])
        self.assertNotIn("риски:", answer["rendered_text"])
        self.assertNotIn("single_pnr_unproven", answer["rendered_text"])
        self.assertNotIn("baggage_unknown", answer["rendered_text"])
        self.assertNotIn("single PNR", answer["rendered_text"])
        self.assertNotIn("through fare", answer["rendered_text"])
        self.assertNotIn("не нашёл в выполненных", answer["rendered_text"])

    def test_rendered_text_labels_provider_full_route_without_protection_claim(
        self,
    ) -> None:
        option = self._source_label_option(
            "provider-full-route",
            source_type="provider_full_route",
            ticketing_model="provider_order_unverified",
            price_basis="provider_offer_price",
            source_providers=["kupibilet"],
            gateway="IST",
        )

        answer = self._source_label_answer(option)

        validate_user_answer(answer)
        text = answer["rendered_text"]
        self.assertIn("источник: полный маршрут от kupibilet", text)
        self.assertIn("цена поставщика", text)
        self.assertIn(
            "единый PNR, сквозной багаж и защита пересадки не подтверждены",
            text,
        )
        self.assertNotIn("provider_full_route", text)
        self.assertEqual(
            answer["catalog"]["items"][0]["ticketing_model"], "provider_aggregate"
        )

    def test_rendered_text_labels_gateway_separate_ticket_price_sum_and_fli_leg(
        self,
    ) -> None:
        option = self._source_label_option(
            "gateway-separate-ticket",
            source_type="gateway_separate_ticket",
            ticketing_model="separate_ticket_sum",
            price_basis="summed_live_leg_prices",
            source_providers=["kupibilet", "fli"],
            gateway="IST",
        )

        answer = self._source_label_answer(option)

        validate_user_answer(answer)
        text = answer["rendered_text"]
        self.assertIn("источник: separate-ticket сборка через IST", text)
        self.assertIn("цена - сумма отдельных плеч", text)
        self.assertIn("FLI/metasearch для non-RU плеча", text)
        self.assertIn(
            "единый PNR, сквозной багаж и защита пересадки не подтверждены",
            text,
        )
        self.assertEqual(
            answer["catalog"]["items"][0]["ticketing_model"], "separate_segments"
        )

    def test_rendered_text_labels_direct_inventory(self) -> None:
        option = self._source_label_option(
            "direct-inventory",
            source_type="direct_inventory",
            ticketing_model="unknown",
            price_basis="provider_offer_price",
            source_providers=["kupibilet"],
            direct=True,
        )

        answer = self._source_label_answer(option)

        validate_user_answer(answer)
        text = answer["rendered_text"]
        self.assertIn("источник: прямой инвентарь (kupibilet)", text)
        self.assertIn("финальный тариф и багаж проверить на booking screen", text)

    def test_rendered_text_labels_two_one_way_offers_as_separate_sum(self) -> None:
        report = report_with_required_caveats()
        report["route"]["dates"] = {
            "depart_date": "2026-07-19",
            "return_date": "2026-07-24",
        }
        report["recommended_options"] = [self._two_one_way_pair_option()]
        report["priority_options"] = []

        answer = build_user_answer(report)

        validate_user_answer(answer)
        text = answer["rendered_text"]
        self.assertIn("источник: две отдельные one-way выдачи", text)
        self.assertIn("цена - сумма отдельных one-way", text)
        self.assertIn("защищённый round-trip не подтверждены", text)

    def test_rendered_text_includes_compact_gateway_coverage_summary(self) -> None:
        answer = build_user_answer(
            self._report_with_gateway_coverage(viable=["IST", "BEG"])
        )

        validate_user_answer(answer)
        text = answer["rendered_text"]
        self.assertIn(
            "Проверил KupiBilet по всему маршруту и 4 gateway: IST, SAW, BEG, DXB.",
            text,
        )
        self.assertIn("Жизнеспособные варианты нашлись через IST и BEG.", text)
        self.assertIn("Не проверено из-за лимита: TBS, EVN.", text)
        self.assertNotIn("probe-", text)
        self.assertNotIn("gateway_leg_results", text)
        self.assertNotIn("{", text)

    def test_gateway_provider_failure_is_omitted_when_viable_gateway_exists(
        self,
    ) -> None:
        answer = build_user_answer(
            self._report_with_gateway_coverage(viable=["IST"], failed=["SAW"])
        )

        validate_user_answer(answer)
        text = answer["rendered_text"]
        self.assertIn("Жизнеспособные варианты нашлись через IST.", text)
        self.assertNotIn("Сбой поставщика затронул gateway", text)
        self.assertNotIn("probe-saw", text)

    def test_gateway_provider_failure_is_summarized_when_no_gateway_is_viable(
        self,
    ) -> None:
        answer = build_user_answer(
            self._report_with_gateway_coverage(viable=[], failed=["SAW"])
        )

        validate_user_answer(answer)
        text = answer["rendered_text"]
        self.assertIn(
            "Жизнеспособных gateway-вариантов среди проверенных не нашлось.",
            text,
        )
        self.assertIn("Сбой поставщика затронул gateway: SAW.", text)
        self.assertNotIn("probe-saw", text)

    def test_catalog_orders_viable_direct_before_cheaper_connections_and_drops_rejects(
        self,
    ) -> None:
        report = valid_report()
        report["route"] = {
            "origin": "SVX",
            "destination": "IST",
            "dates": {"depart_date": "2026-08-06"},
        }
        base = copy.deepcopy(valid_option())
        base["ok"] = True
        base["risk"] = {
            "score": 0,
            "grade": "excellent",
            "reject": False,
            "top_reasons": [],
        }
        base["ticketing_model"] = "separate_segments"

        connected = copy.deepcopy(base)
        connected.update(
            {
                "id": "assembled-cheap-svo",
                "rank": 1,
                "price": {"amount": 29678, "currency": "RUB"},
                "price_text": "29 678 RUB",
                "elapsed_min": 820,
                "max_connections_per_journey": 1,
                "segments": [
                    {
                        "direction": "outbound",
                        "flight_number": "SU1419",
                        "carrier": "SU",
                        "marketing_carrier": "SU",
                        "operating_carrier": "SU",
                        "origin": "SVX",
                        "destination": "SVO",
                        "arrival_terminal": "B",
                        "departure_at": "2026-08-06T00:40:00+05:00",
                        "arrival_at": "2026-08-06T01:10:00+03:00",
                        "aircraft_code": "320",
                        "duration_min": 150,
                    },
                    {
                        "direction": "outbound",
                        "flight_number": "SU2172",
                        "carrier": "SU",
                        "marketing_carrier": "SU",
                        "operating_carrier": "SU",
                        "origin": "SVO",
                        "destination": "IST",
                        "departure_terminal": "C",
                        "departure_at": "2026-08-06T07:20:00+03:00",
                        "arrival_at": "2026-08-06T12:20:00+03:00",
                        "aircraft_code": "320",
                        "duration_min": 300,
                    },
                ],
            }
        )
        direct = copy.deepcopy(base)
        direct.update(
            {
                "id": "assembled-direct-ist",
                "rank": 8,
                "price": {"amount": 33342, "currency": "RUB"},
                "price_text": "33 342 RUB",
                "elapsed_min": 330,
                "max_connections_per_journey": 0,
                "segments": [
                    {
                        "direction": "outbound",
                        "flight_number": "U6773",
                        "carrier": "U6",
                        "marketing_carrier": "U6",
                        "operating_carrier": "U6",
                        "origin": "SVX",
                        "destination": "IST",
                        "departure_at": "2026-08-06T07:20:00+05:00",
                        "arrival_at": "2026-08-06T10:50:00+03:00",
                        "aircraft_code": "319",
                        "duration_min": 330,
                    }
                ],
            }
        )
        invalid = copy.deepcopy(connected)
        invalid["id"] = "assembled-invalid-svo"
        invalid["ok"] = False
        invalid["risk"] = {
            "score": 100,
            "grade": "reject",
            "reject": True,
            "top_reasons": [{"code": "invalid_time_order"}],
        }
        invalid["segments"][0]["flight_number"] = "SU1471"
        invalid["segments"][1]["flight_number"] = "SU2170"
        invalid["segments"][1]["departure_at"] = "2026-08-06T01:00:00+03:00"
        alias = copy.deepcopy(connected)
        alias["id"] = "ru-priority-moscow_gateway:assembled-cheap-svo"
        alias["category"] = "moscow_gateway_control"
        report["recommended_options"] = [connected, direct, invalid]
        report["priority_options"] = [alias]
        report["status"] = {"direct_mode": {}}

        with patch(
            "flights_cli.reporting.user_answer.airport_city_label",
            side_effect=lambda code: {
                "SVX": "Екатеринбург",
                "SVO": "Москва",
                "IST": "Стамбул",
            }.get(code, code),
            create=True,
        ):
            answer = build_user_answer(report)

        validate_user_answer(answer)
        items = answer["catalog"]["items"]
        self.assertEqual(
            [item["option_id"] for item in items],
            ["assembled-direct-ist", "assembled-cheap-svo"],
        )
        self.assertEqual(
            items[0]["directions"]["outbound"]["segments"][0]["flight_number"], "U6773"
        )
        self.assertEqual(
            [
                segment["flight_number"]
                for segment in items[1]["directions"]["outbound"]["segments"]
            ],
            ["SU1419", "SU2172"],
        )
        self.assertNotIn("assembled-invalid-svo", {item["option_id"] for item in items})

    def test_catalog_uses_business_rank_before_price_for_same_stop_count(self) -> None:
        base = copy.deepcopy(valid_option())
        base["ok"] = True
        base["risk"] = {
            "score": 0,
            "grade": "excellent",
            "reject": False,
            "top_reasons": [],
        }
        base["max_connections_per_journey"] = 1

        long_wait_cheap = copy.deepcopy(base)
        long_wait_cheap.update(
            {
                "id": "cheap-long-wait",
                "rank": 42,
                "price": {"amount": 29678, "currency": "RUB"},
                "elapsed_min": 1080,
            }
        )
        short_expensive = copy.deepcopy(base)
        short_expensive.update(
            {
                "id": "short-business-ranked",
                "rank": 7,
                "price": {"amount": 36000, "currency": "RUB"},
                "elapsed_min": 510,
            }
        )

        ordered = ordered_user_options([long_wait_cheap, short_expensive], [], limit=2)

        self.assertEqual(
            [option["id"] for option in ordered],
            ["short-business-ranked", "cheap-long-wait"],
        )

    def test_aircraft_display_label_normalizes_common_equipment_codes(self) -> None:
        self.assertEqual(aircraft_display_label("73H"), "B737")
        self.assertEqual(aircraft_display_label("319"), "A319")
        self.assertEqual(aircraft_display_label("A32A"), "A320")

    def test_renderer_uses_report_truth_language_for_absence_scope(self) -> None:
        report = valid_report()
        report["recommended_options"] = []
        report["priority_options"] = []
        report["offer_graph"]["truth_language"]["negative_wording"] = (
            "truth-boundary-token: не нашёл в выполненных live/probe источниках; "
            "это не доказательство отсутствия вне границ источника"
        )
        report["coverage_diagnostics"]["searched_controls"] = [
            {
                "type": "exact_airport_direct",
                "direction": "outbound",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "execution_state": "searched",
                "status": "ok",
                "offer_count": 0,
                "evidence_type": "provider_empty",
                "absence_class": "provider_empty_not_structural_absence",
            }
        ]
        report["coverage_diagnostics"]["not_executed_controls"] = []
        report["coverage_diagnostics"]["completeness"] = {
            "planned_count": 1,
            "terminal_count": 1,
            "all_planned_controls_have_terminal_state": True,
        }

        answer = build_user_answer(report)

        validate_user_answer(answer)
        self.assertEqual(answer["answer_mode"], "no_viable_options")
        self.assertIn("truth-boundary-token", answer["rendered_text"])
        self.assertIn(
            "provider_empty_not_structural_absence",
            str(report["coverage_diagnostics"]["searched_controls"]),
        )
        self.assertNotIn("structural absence", answer["rendered_text"].lower())

    def test_round_trip_provider_aggregate_alternatives_are_directional_not_full_trip(
        self,
    ) -> None:
        report = report_with_required_caveats()
        report["route"]["dates"] = {
            "depart_date": "2026-07-19",
            "return_date": "2026-07-24",
        }
        report["recommended_options"] = [self._round_trip_option("assembled-primary")]
        report["priority_options"] = [
            self._round_trip_option("assembled-round-trip"),
            self._provider_aggregate_option("outbound"),
            self._provider_aggregate_option("return"),
        ]

        answer = build_user_answer(report)

        validate_user_answer(answer)
        alternatives = {item["id"]: item for item in answer["alternatives"]}
        assembled = alternatives["assembled-round-trip"]
        outbound = alternatives["provider-aggregate:outbound:agg-outbound"]
        inbound = alternatives["provider-aggregate:return:agg-return"]
        self.assertEqual(assembled["journey_scope"], "round_trip")
        self.assertTrue(assembled["covers_requested_trip"])
        self.assertFalse(assembled["directional_only"])
        self.assertEqual(outbound["journey_scope"], "outbound_only")
        self.assertEqual(outbound["direction"], "outbound")
        self.assertTrue(outbound["directional_only"])
        self.assertFalse(outbound["covers_requested_trip"])
        self.assertEqual(inbound["journey_scope"], "return_only")
        self.assertEqual(inbound["direction"], "return")
        self.assertTrue(inbound["directional_only"])
        self.assertFalse(inbound["covers_requested_trip"])
        combined_text = " ".join(
            str(value)
            for item in (outbound, inbound)
            for value in (item.get("user_facing_label"), item.get("disclaimer"))
            if value
        ).lower()
        self.assertNotIn(
            "single pnr", combined_text.replace("not proven as single pnr", "")
        )
        self.assertNotIn(
            "protected round-trip",
            combined_text.replace(
                "not proven as single pnr / protected round-trip", ""
            ),
        )

    def test_build_user_answer_preserves_two_one_way_pair_alternative(self) -> None:
        report = report_with_required_caveats()
        report["route"]["dates"] = {
            "depart_date": "2026-07-19",
            "return_date": "2026-07-24",
        }
        report["recommended_options"] = [self._round_trip_option("assembled-primary")]
        report["priority_options"] = [
            self._round_trip_option(f"assembled-filler-{index}") for index in range(5)
        ] + [self._two_one_way_pair_option()]

        answer = build_user_answer(report)
        validate_user_answer(answer)

        alternatives = {item["id"]: item for item in answer["alternatives"]}
        self.assertIn(
            "provider-aggregate:two-one-way-pair:agg-outbound+agg-return", alternatives
        )
        pair = alternatives[
            "provider-aggregate:two-one-way-pair:agg-outbound+agg-return"
        ]
        self.assertEqual(pair["journey_scope"], "two_one_way_pair")
        self.assertTrue(pair["covers_requested_trip"])
        self.assertIsNone(pair["direction"])
        self.assertFalse(pair["directional_only"])
        self.assertTrue(pair["composed_of_directional_offers"])
        self.assertEqual(pair["ticketing_model"], "separate_one_way_offers")
        self.assertEqual(
            pair["outbound_time"],
            {
                "itinerary_elapsed_min": 660,
                "flight_time_min": 300,
                "layover_total_min": 360,
            },
        )
        self.assertEqual(
            pair["return_time"],
            {
                "itinerary_elapsed_min": 570,
                "flight_time_min": 440,
                "layover_total_min": 130,
            },
        )

    def test_rejects_two_one_way_pair_without_separate_one_way_ticketing_model(
        self,
    ) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad-ticketing",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="provider_aggregate",
                user_facing_label="Two separate one-way offers: outbound SVX→LON + return LON→SVX.",
                disclaimer="Two separate one-way offers; verify ticketing and protection on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.alternatives[0].ticketing_model", semantic_error_paths(ctx.exception)
        )

    def test_rejects_two_one_way_pair_claiming_single_pnr_or_protected_round_trip(
        self,
    ) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad-claim",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="separate_one_way_offers",
                user_facing_label="Two separate one-way offers: outbound SVX→LON + return LON→SVX.",
                disclaimer="Two separate one-way offers. This is a single PNR protected round-trip through fare.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.alternatives[0].disclaimer", semantic_error_paths(ctx.exception)
        )

    def test_rejects_provider_aggregate_travel_time_label_when_only_flight_time_is_known(
        self,
    ) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:outbound:bad-time-label",
                journey_scope="outbound_only",
                covers_requested_trip=False,
                direction="outbound",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
                itinerary_elapsed_min=None,
                flight_time_min=545,
                layover_total_min=None,
                user_facing_label="One-way outbound alternative: SVX→LON, 21 208 RUB. Travel time: 9h05.",
                disclaimer="Provider aggregate one-way offer; verify final fare on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.alternatives[0].user_facing_label", semantic_error_paths(ctx.exception)
        )

    def test_rejects_provider_aggregate_ambiguous_duration_or_elapsed_wording(
        self,
    ) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:outbound:bad-duration-wording",
                journey_scope="outbound_only",
                covers_requested_trip=False,
                direction="outbound",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
                itinerary_elapsed_min=660,
                flight_time_min=300,
                layover_total_min=360,
                user_facing_label="One-way outbound alternative: SVX→LON, 21 208 RUB. Duration: 11h00 elapsed.",
                disclaimer="Provider aggregate one-way offer; verify final fare on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.alternatives[0].user_facing_label", semantic_error_paths(ctx.exception)
        )

    def test_rejects_two_one_way_pair_with_combined_itinerary_elapsed(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad-combined-time",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="separate_one_way_offers",
                itinerary_elapsed_min=1230,
                user_facing_label="Two separate one-way offers: outbound SVX→LON + return LON→SVX. Total journey time: 20h30.",
                disclaimer="Two separate one-way offers; verify ticketing and protection on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.alternatives[0].itinerary_elapsed_min",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_round_trip_outbound_aggregate_without_directional_label(
        self,
    ) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:outbound:bad",
                journey_scope="round_trip",
                covers_requested_trip=True,
                direction="outbound",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        paths = semantic_error_paths(ctx.exception)
        self.assertIn("$.alternatives[0].journey_scope", paths)
        self.assertIn("$.alternatives[0].user_facing_label", paths)

    def test_rejects_round_trip_return_aggregate_without_directional_label(
        self,
    ) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:return:bad",
                journey_scope="round_trip",
                covers_requested_trip=True,
                direction="return",
                directional_only=True,
                composed_of_directional_offers=False,
                ticketing_model="provider_aggregate",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        paths = semantic_error_paths(ctx.exception)
        self.assertIn("$.alternatives[0].journey_scope", paths)
        self.assertIn("$.alternatives[0].user_facing_label", paths)

    def test_rejects_two_one_way_pair_without_separate_one_way_disclaimer(self) -> None:
        answer = self._valid_round_trip_answer()
        answer["alternatives"] = [
            self._minimal_alternative(
                "provider-aggregate:two-one-way-pair:bad",
                journey_scope="two_one_way_pair",
                covers_requested_trip=True,
                direction=None,
                directional_only=False,
                composed_of_directional_offers=True,
                ticketing_model="separate_one_way_offers",
                user_facing_label="Combined provider aggregate offers",
                disclaimer="Verify fare rules and baggage on the booking screen.",
            )
        ]

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.alternatives[0].disclaimer", semantic_error_paths(ctx.exception)
        )

    def test_user_answer_counts_not_supported_controls_without_missing_evidence(
        self,
    ) -> None:
        report = valid_report()
        report["coverage_diagnostics"]["not_executed_controls"] = []
        report["coverage_diagnostics"]["not_supported_controls"] = [
            {
                "type": "full_route_aggregate",
                "direction": "outbound",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "provider": "kupibilet",
                "reason": "provider_capability_not_supported",
                "execution_state": "not_supported",
                "status": "not_supported",
                "probe_id": "agg-probe-001",
            }
        ]
        report["coverage_diagnostics"]["completeness"] = {
            "planned_count": 1,
            "terminal_count": 1,
            "all_planned_controls_have_terminal_state": True,
        }

        answer = build_user_answer(report)

        validate_user_answer(answer)
        self.assertEqual(answer["evidence_status"]["not_supported_control_count"], 1)
        self.assertEqual(answer["evidence_status"]["not_executed_control_count"], 0)
        self.assertTrue(answer["evidence_status"]["execution_complete"])
        self.assertTrue(answer["evidence_status"]["evidence_complete"])
        self.assertTrue(answer["evidence_status"]["coverage_complete"])
        self.assertIn(
            "not_supported_controls",
            answer["evidence_status"]["non_blocking_boundaries"],
        )
        self.assertTrue(
            answer["required_caveats"]["coverage_incompleteness_acknowledged"]
        )

    def test_build_user_answer_does_not_fallback_to_legacy_display_or_answer_lines(
        self,
    ) -> None:
        report = valid_report()
        report["recommended_options"] = []
        report["priority_options"] = []
        report["display"]["text"] = "STALE DISPLAY"
        report["answer_lines"] = ["STALE ANSWER LINE"]

        answer = build_user_answer(report)

        self.assertNotEqual(answer["rendered_text"], "STALE DISPLAY")
        self.assertNotIn("STALE ANSWER LINE", answer["rendered_text"])

    def test_rejects_missing_provider_failure_acknowledgement(self) -> None:
        answer = build_user_answer(report_with_required_caveats())
        answer["required_caveats"]["provider_failures_acknowledged"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertIn(
            "$.required_caveats.provider_failures_acknowledged",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_missing_through_fare_verification(self) -> None:
        answer = build_user_answer(report_with_required_caveats())
        answer["required_caveats"]["through_fare_verification_required"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.required_caveats.through_fare_verification_required",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_missing_coverage_incompleteness_acknowledgement(self) -> None:
        answer = build_user_answer(report_with_required_caveats())
        answer["required_caveats"]["coverage_incompleteness_acknowledged"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        self.assertIn(
            "$.required_caveats.coverage_incompleteness_acknowledged",
            semantic_error_paths(ctx.exception),
        )

    def test_rejects_missing_source_boundary_and_purchase_verification(self) -> None:
        answer = build_user_answer(report_with_required_caveats())
        answer["required_caveats"]["source_boundaries_included"] = False
        answer["required_caveats"]["purchase_screen_verification_required"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer(answer)

        paths = semantic_error_paths(ctx.exception)
        self.assertIn("$.required_caveats.source_boundaries_included", paths)
        self.assertIn("$.required_caveats.purchase_screen_verification_required", paths)


if __name__ == "__main__":
    unittest.main()
