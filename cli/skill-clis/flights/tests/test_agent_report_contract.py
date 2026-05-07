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
    "through_fare_checks",
    "rejected_pair_warnings",
    "answer_lines",
]


def valid_option() -> dict:
    return {
        "rank": 1,
        "id": "assembled-1:SVX-DEL",
        "category": None,
        "reason": None,
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
        "through_fare_checks": [],
        "rejected_pair_warnings": [],
        "answer_lines": [
            "Best CLI-ranked option: 10 000 RUB risk=good/1 elapsed=2h.",
            "Segments: SU232 SVO 21:20->DEL 06:00",
            "Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.",
        ],
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
                            "code": "long_layover",
                            "points": 3,
                            "message": "Connection is longer than the profile's ideal range.",
                        }
                    ],
                },
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

    def test_priority_options_must_surface_in_answer_lines(self) -> None:
        report = valid_report()
        priority = copy.deepcopy(valid_option())
        priority["category"] = "all_su_svo"
        priority["rank"] = 4
        report["priority_options"] = [priority]
        report["answer_lines"] = ["Best CLI-ranked option: 10 000 RUB."]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertTrue(any("priority/control" in error["message"] for error in ctx.exception.details["errors"]))

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
