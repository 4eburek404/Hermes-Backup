from __future__ import annotations

import contextlib
import copy
import io
import json
import unittest
from importlib import resources
from unittest.mock import patch

from jsonschema import Draft202012Validator

from flights_cli.cli import main
from flights_cli.errors import CliError
from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import (
    AGENT_REPORT_SCHEMA_PACKAGE,
    AGENT_REPORT_SCHEMA_RESOURCE,
    AGENT_REPORT_SCHEMA_VERSION,
    load_agent_report_schema,
    validate_agent_report,
)


EXPECTED_TOP_LEVEL_REQUIRED = [
    "schema_version",
    "route",
    "status",
    "source_boundaries",
    "hub_viability",
    "segment_searches",
    "provider_failures",
    "recommended_options",
    "priority_options",
    "aggregate_controls",
    "coverage_diagnostics",
    "through_fare_checks",
    "rejected_pair_warnings",
    "answer_lines",
    "display",
]


def valid_option() -> dict:
    return {
        "rank": 1,
        "id": "assembled-1:SVX-DEL",
        "category": None,
        "reason": None,
        "detail_status": "full",
        "ok": True,
        "price": {"amount": 10000, "currency": "RUB"},
        "price_text": "10 000 RUB",
        "elapsed_min": 120,
        "elapsed": "2h",
        "carriers": ["SU"],
        "risk": {"score": 1, "grade": "good", "reject": False, "top_reasons": []},
        "validation_summary": {"ok": True},
        "connections": [],
        "segments": [
            {
                "direction": "outbound",
                "flight_number": "SU232",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "DEL",
                "departure_at": "2026-06-01T21:20:00+03:00",
                "arrival_at": "2026-06-02T06:00:00+05:30",
                "aircraft_code": "333",
                "duration_min": 310,
            }
        ],
        "ticketing_note": "Assume separate/self-transfer until the booking screen confirms protected through-ticketing and baggage.",
    }


def valid_report() -> dict:
    return {
        "schema_version": AGENT_REPORT_SCHEMA_VERSION,
        "route": {
            "origin": "SVX",
            "destination": "DEL",
            "origin_airports": ["SVX"],
            "destination_airports": ["DEL"],
            "dates": {"depart_date": "2026-06-01"},
            "profile": "business",
            "routing_strategy": "ru-priority",
            "provider_policy": "kupibilet",
        },
        "status": {
            "ranked_output_count": 1,
            "ranked_total_count": 1,
            "candidate_count": 1,
            "candidate_pool_truncated": False,
            "failure_count": 0,
        },
        "source_boundaries": [
            "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares."
        ],
        "hub_viability": [],
        "segment_searches": [],
        "provider_failures": [],
        "recommended_options": [valid_option()],
        "priority_options": [],
        "aggregate_controls": [],
        "coverage_diagnostics": {
            "coverage_mode": "targeted",
            "negative_evidence_type": "bounded_live_controls_only",
            "planned_controls": [
                {
                    "type": "exact_airport_direct",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "execution_state": "planned",
                    "probe_id": "probe-001",
                }
            ],
            "searched_controls": [],
            "skipped_controls": [],
            "failed_controls": [],
            "not_executed_controls": [
                {
                    "type": "exact_airport_direct",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "execution_state": "not_executed",
                    "status": "not_executed",
                    "reason": "not_reached_by_current_live_execution",
                    "cache_status": "unknown",
                    "probe_id": "probe-001",
                }
            ],
            "deduped_controls": [],
            "coverage_warnings": ["segment_absence_is_not_route_absence"],
            "limits": {},
            "completeness": {
                "planned_count": 1,
                "terminal_count": 1,
                "all_planned_controls_have_terminal_state": True,
            },
        },
        "through_fare_checks": [],
        "rejected_pair_warnings": [],
        "answer_lines": [
            "Best CLI-ranked option: 10 000 RUB risk=good/1 elapsed=2h.",
            "Segments: SU232 SVO 21:20->DEL 06:00",
            "Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.",
        ],
        "display": {
            "format_version": "flight_display.v1",
            "text": "10 000 RUB | всего 6:10 | пересадок 0\nSU232 01JUN SVO - DEL 21:20 - 06:00 борт 333 в полете 5:10",
            "options": [
                {
                    "id": "assembled-1:SVX-DEL",
                    "category": None,
                    "price_text": "10 000 RUB",
                    "total_elapsed": "6:10",
                    "connection_count": 0,
                    "lines": ["SU232 01JUN SVO - DEL 21:20 - 06:00 борт 333 в полете 5:10"],
                    "text": "10 000 RUB | всего 6:10 | пересадок 0\nSU232 01JUN SVO - DEL 21:20 - 06:00 борт 333 в полете 5:10",
                }
            ],
        },
    }


def ru_priority_branch(
    *,
    execution_state: str = "not_generated",
    viable: bool = False,
    visible: bool = False,
    priority_option_id: str | None = None,
    evidence_option_ids: list[str] | None = None,
) -> dict:
    return {
        "checked": True,
        "execution_state": execution_state,
        "viable": viable,
        "visible": visible,
        "priority_option_id": priority_option_id,
        "evidence_option_ids": evidence_option_ids or [],
    }


def valid_ru_priority_controls() -> dict:
    return {
        "requested": True,
        "checked": True,
        "route_family": "ru_priority",
        "scope": {
            "origin": "SVX",
            "destination": "LON",
            "origin_airports": ["SVX"],
            "destination_airports": ["LHR", "LGW", "STN", "LTN"],
            "moscow_airports": ["SVO", "DME", "VKO"],
            "primary_hub": "IST",
        },
        "direct_destination_control": ru_priority_branch(),
        "ist_primary_hub_control": ru_priority_branch(),
        "moscow_gateway_control": ru_priority_branch(),
        "moscow_via_ist_fallback_control": ru_priority_branch(),
        "decision": "no_viable_ru_priority_control",
    }


class AgentReportContractTests(unittest.TestCase):
    def test_schema_is_valid_and_stable(self) -> None:
        schema = load_agent_report_schema()

        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["$id"], "urn:hermes:flights-cli:agent-report:v1")
        self.assertEqual(schema["title"], "Hermes Flights CLI Agent Report v1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], AGENT_REPORT_SCHEMA_VERSION)
        self.assertEqual(schema["required"], EXPECTED_TOP_LEVEL_REQUIRED)
        self.assertIs(schema["additionalProperties"], False)

    def test_schema_loads_as_package_resource_and_stays_compact(self) -> None:
        text = resources.files(AGENT_REPORT_SCHEMA_PACKAGE).joinpath(AGENT_REPORT_SCHEMA_RESOURCE).read_text(encoding="utf-8")
        parsed = json.loads(text)

        self.assertEqual(parsed["$id"], "urn:hermes:flights-cli:agent-report:v1")
        self.assertLessEqual(len(text.splitlines()), 700)
        self.assertLessEqual(len(text.encode("utf-8")), 16000)

    def test_valid_synthetic_agent_report_passes(self) -> None:
        validate_agent_report(valid_report())

    def test_schema_accepts_ru_priority_controls_for_ru_touching_international_route(self) -> None:
        report = valid_report()
        report["route"]["destination"] = "LON"
        report["route"]["destination_airports"] = ["LHR", "LGW", "STN", "LTN"]
        report["route"]["routing_strategy"] = "ru-priority"
        report["ru_priority_controls"] = valid_ru_priority_controls()

        validate_agent_report(report)

    def test_ru_priority_branch_without_execution_state_fails_semantic_validation(self) -> None:
        report = valid_report()
        report["ru_priority_controls"] = valid_ru_priority_controls()
        del report["ru_priority_controls"]["moscow_gateway_control"]["execution_state"]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertTrue(
            any(
                error["validator"] == "semantic"
                and error["path"] == "$.ru_priority_controls.moscow_gateway_control.execution_state"
                and "execution_state" in error["message"]
                for error in ctx.exception.details["errors"]
            )
        )

    def test_ru_priority_visible_true_with_viable_false_fails_semantic_validation(self) -> None:
        report = valid_report()
        option = copy.deepcopy(valid_option())
        option["id"] = "priority-direct"
        option["control_family"] = "ru_priority"
        option["control_branch"] = "direct_destination"
        option["visibility_role"] = "priority_control"
        report["priority_options"] = [option]
        report["ru_priority_controls"] = valid_ru_priority_controls()
        report["ru_priority_controls"]["direct_destination_control"] = ru_priority_branch(
            execution_state="executed_no_viable_result",
            viable=False,
            visible=True,
            priority_option_id="priority-direct",
            evidence_option_ids=["priority-direct"],
        )

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertTrue(
            any(
                error["validator"] == "semantic" and "cannot be visible when viable is false" in error["message"]
                for error in ctx.exception.details["errors"]
            )
        )

    def test_ru_priority_visibility_is_structural_not_answer_line_text(self) -> None:
        report = valid_report()
        report["route"]["destination"] = "LON"
        report["route"]["destination_airports"] = ["LHR", "LGW", "STN", "LTN"]
        option = copy.deepcopy(valid_option())
        option["id"] = "priority-ist-primary"
        option["category"] = "ist_primary_hub_control"
        option["control_family"] = "ru_priority"
        option["control_branch"] = "ist_primary_hub"
        option["visibility_role"] = "priority_control"
        report["priority_options"] = [option]
        report["ru_priority_controls"] = valid_ru_priority_controls()
        report["ru_priority_controls"]["ist_primary_hub_control"] = ru_priority_branch(
            execution_state="executed",
            viable=True,
            visible=True,
            priority_option_id="priority-ist-primary",
            evidence_option_ids=["priority-ist-primary"],
        )
        report["ru_priority_controls"]["decision"] = "ist_primary_viable"
        report["answer_lines"] = [
            "Best CLI-ranked option: 10 000 RUB.",
            "Ветка через IST проверена: найден годный вариант.",
            "Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.",
        ]
        answer_text = "\n".join(report["answer_lines"])
        self.assertNotIn("control", answer_text.lower())
        self.assertNotIn("priority", answer_text.lower())
        self.assertNotIn("Контроль", answer_text)

        validate_agent_report(report)

    def test_summary_only_display_rejects_detailed_flight_lines(self) -> None:
        report = valid_report()
        summary_option = copy.deepcopy(valid_option())
        summary_option["id"] = "option-summary"
        summary_option["rank"] = 2
        summary_option["detail_status"] = "summary_only"
        summary_option["segments"] = []
        report["recommended_options"].append(summary_option)
        report["display"]["options"].append(
            {
                "id": "option-summary",
                "category": None,
                "price_text": "12 000 RUB",
                "total_elapsed": "6:00",
                "connection_count": 1,
                "lines": [
                    "SVX→IST U6 123 10:00–13:00",
                    "пересадка IST 2:00",
                    "IST→LHR TK1985 15:00–17:00",
                ],
                "text": "12 000 RUB | всего 6:00 | пересадок 1\nSVX→IST U6 123 10:00–13:00\nпересадка IST 2:00\nIST→LHR TK1985 15:00–17:00",
            }
        )
        report["display"]["text"] = "\n\n".join(option["text"] for option in report["display"]["options"])

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertTrue(
            any(
                error["validator"] == "semantic" and "summary_only display must not include detailed flight lines" in error["message"]
                for error in ctx.exception.details["errors"]
            )
        )

    def test_canonical_coverage_diagnostics_requires_terminal_fields(self) -> None:
        report = valid_report()

        validate_agent_report(report)

    def test_canonical_coverage_diagnostics_rejects_old_minimal_shape(self) -> None:
        report = valid_report()
        for key in ("planned_controls", "failed_controls", "not_executed_controls", "deduped_controls", "completeness"):
            del report["coverage_diagnostics"][key]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("planned_controls", messages)
        self.assertIn("completeness", messages)

    def test_canonical_coverage_diagnostics_rejects_incomplete_terminal_semantics(self) -> None:
        report = valid_report()
        report["coverage_diagnostics"]["completeness"] = {
            "planned_count": 2,
            "terminal_count": 1,
            "all_planned_controls_have_terminal_state": False,
        }

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertTrue(any(error["validator"] == "semantic" for error in ctx.exception.details["errors"]))

    def test_v1_accepts_optional_omitted_counts(self) -> None:
        report = valid_report()
        report["omitted_counts"] = {
            "recommended_options": 2,
            "coverage_controls": 15,
            "option_segments": 3,
        }

        validate_agent_report(report)

    def test_v1_accepts_runtime_evidence_optional_fields(self) -> None:
        report = valid_report()
        report["segment_searches"] = [
            {
                "direction": "outbound",
                "leg": "direct_outbound",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "provider": "kupibilet",
                "status": "deduped",
                "reason": "duplicate_segment_probe",
                "offer_count": 1,
                "cache_status": "cache_hit",
                "probe_id": "segment-probe-002",
                "original_probe_id": "segment-probe-001",
            }
        ]
        report["provider_failures"] = [
            {
                "direction": "outbound",
                "leg": "direct_outbound",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "provider": "kupibilet",
                "cache_status": "unknown",
                "probe_id": "segment-probe-003",
                "error": {
                    "type": "upstream_error",
                    "message": "Kupibilet HTTP 429",
                    "classification": "rate_limited",
                    "retryable": True,
                    "http_status": 429,
                },
            }
        ]
        report["answer_lines"].append("Provider failure: 1 probe failed; see provider_failures for details.")

        validate_agent_report(report)

    def test_v1_accepts_optional_stop_policy_fields(self) -> None:
        report = valid_report()
        report["stop_policy"] = {
            "name": "business_default",
            "preferred_max_connections": 1,
            "fallback_max_connections": 2,
            "hard_max_connections": 2,
            "two_stop_allowed_only_if_no_preferred": True,
            "three_plus_reportable": False,
        }
        report["stop_policy_diagnostics"] = {
            "policy": "business_default",
            "preferred_candidate_count": 1,
            "two_stop_candidate_count": 0,
            "three_plus_suppressed_count": 0,
            "used_two_stop_fallback": False,
            "garbage_options_hidden_from_answer": False,
        }
        report["recommended_options"][0]["stop_tier"] = "T0_DIRECT"
        report["recommended_options"][0]["max_connections_per_journey"] = 0

        validate_agent_report(report)

    def test_structured_risk_reasons_are_allowed(self) -> None:
        report = valid_report()
        report["recommended_options"][0]["risk"]["top_reasons"] = [
            {"scope": "carrier", "code": "preferred_carrier_match", "points": 0, "message": "Uses preferred carrier."}
        ]
        report["recommended_options"][0]["connections"] = [
            {
                "direction": "outbound",
                "arrival_airport": "IST",
                "departure_airport": "IST",
                "status": "ok",
                "severity": "ok",
                "actual_min": 240,
                "actual": "4h",
                "required_min": 120,
                "required": "2h",
                "risk": {
                    "score": 3,
                    "grade": "good",
                    "reasons": [
                        {
                            "scope": "connection",
                            "code": "below_ideal_buffer",
                            "points": 3,
                            "message": "Connection is valid but below ideal buffer.",
                        }
                    ],
                },
                "tradeoffs": [],
            }
        ]

        validate_agent_report(report)

    def test_missing_required_top_level_field_fails(self) -> None:
        report = valid_report()
        del report["source_boundaries"]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertIn("source_boundaries", ctx.exception.details["errors"][0]["message"])

    def test_wrong_schema_version_fails(self) -> None:
        report = valid_report()
        report["schema_version"] = "agent_report.v2"

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertEqual(ctx.exception.details["schema_version"], "agent_report.v2")

    def test_extra_top_level_field_fails(self) -> None:
        report = valid_report()
        report["debug_dump"] = {}

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertTrue(any(error["validator"] == "additionalProperties" for error in ctx.exception.details["errors"]))

    def test_priority_options_do_not_require_answer_line_keywords(self) -> None:
        report = valid_report()
        priority = copy.deepcopy(valid_option())
        priority["category"] = "all_su_svo"
        priority["rank"] = 4
        report["priority_options"] = [priority]
        report["answer_lines"] = ["Best CLI-ranked option: 10 000 RUB."]

        validate_agent_report(report)

    def test_through_fare_checks_must_surface_in_answer_lines(self) -> None:
        report = valid_report()
        report["through_fare_checks"] = [
            {
                "direction": "outbound",
                "route": "SVX->DEL",
                "date": "2026-06-01",
                "carrier": "SU",
                "reason": "Same-carrier priority option can be better priced or protected as an airline/GDS through fare.",
                "verify_with": ["airline website", "GDS/Sirena/Amadeus-capable seller", "booking screen fare rules"],
            }
        ]
        report["answer_lines"] = ["Best CLI-ranked option: 10 000 RUB."]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertTrue(any("through-fare verification" in error["message"] for error in ctx.exception.details["errors"]))

    def test_provider_failures_must_surface_in_answer_lines(self) -> None:
        report = valid_report()
        report["provider_failures"] = [
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "origin": "IST",
                "destination": "FRA",
                "date": "2026-08-14",
                "provider": "fli",
                "error": {"type": "upstream_error", "message": "FLI MCP request failed: connection refused"},
            }
        ]
        report["answer_lines"] = ["Best CLI-ranked option: 10 000 RUB."]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertTrue(any("provider failures" in error["message"] for error in ctx.exception.details["errors"]))

    def test_build_agent_report_surfaces_fli_failures(self) -> None:
        report = build_agent_report(
            {
                "live_search": {
                    "failures": [
                        {
                            "direction": "outbound",
                            "leg": "hub_to_destination",
                            "origin": "IST",
                            "destination": "FRA",
                            "date": "2026-08-14",
                            "provider": "fli",
                            "error": {
                                "type": "upstream_error",
                                "message": "FLI MCP request failed: URLError: <urlopen error [Errno 61] Connection refused>",
                            },
                        }
                    ]
                },
                "ranked_candidates": [],
                "ranked": [],
                "assembly": {},
            }
        )

        validate_agent_report(report)
        self.assertEqual(report["provider_failures"][0]["provider"], "fli")
        self.assertIn("Provider failure: FLI failed", " ".join(report["answer_lines"]))

    def test_json_cli_envelope_reports_contract_failure(self) -> None:
        payload = {
            "segment_results": [
                {
                    "direction": "outbound",
                    "leg": "origin_to_hub",
                    "query": {"origin": "SVX", "destination": "SVO", "date": "2026-06-01", "currency": "RUB"},
                    "offers": [
                        {
                            "id": "svx-svo",
                            "origin": "SVX",
                            "destination": "SVO",
                            "departure_airport": "SVX",
                            "arrival_airport": "SVO",
                            "departure_at": "2026-06-01T16:30:00+05:00",
                            "arrival_at": "2026-06-01T17:15:00+03:00",
                            "price": 10000,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVX",
                                    "destination": "SVO",
                                    "departure_at": "2026-06-01T16:30:00+05:00",
                                    "arrival_at": "2026-06-01T17:15:00+03:00",
                                    "flight_number": "SU1403",
                                    "carrier": "SU",
                                }
                            ],
                        }
                    ],
                },
                {
                    "direction": "outbound",
                    "leg": "hub_to_destination",
                    "query": {"origin": "SVO", "destination": "DEL", "date": "2026-06-01", "currency": "RUB"},
                    "offers": [
                        {
                            "id": "svo-del",
                            "origin": "SVO",
                            "destination": "DEL",
                            "departure_airport": "SVO",
                            "arrival_airport": "DEL",
                            "departure_at": "2026-06-01T21:20:00+03:00",
                            "arrival_at": "2026-06-02T06:00:00+05:30",
                            "price": 20000,
                            "currency": "RUB",
                            "segments": [
                                {
                                    "origin": "SVO",
                                    "destination": "DEL",
                                    "departure_at": "2026-06-01T21:20:00+03:00",
                                    "arrival_at": "2026-06-02T06:00:00+05:30",
                                    "flight_number": "SU232",
                                    "carrier": "SU",
                                }
                            ],
                        }
                    ],
                },
            ]
        }
        forced_error = CliError(
            "agent_report failed contract validation",
            error_type="contract_error",
            details={"schema_version": AGENT_REPORT_SCHEMA_VERSION, "errors": [{"path": "$", "message": "forced"}]},
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch(
            "flights_cli.services.agent_report.validate_agent_report", side_effect=forced_error
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "flights",
                    "--json",
                    "route",
                    "assemble",
                    "--profile",
                    "safe",
                    "--agent-brief",
                    "--input",
                    "-",
                ]
            )

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        error_payload = json.loads(stderr.getvalue())
        self.assertFalse(error_payload["ok"])
        self.assertEqual(error_payload["error"]["type"], "contract_error")
        self.assertEqual(error_payload["error"]["details"]["schema_version"], AGENT_REPORT_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
