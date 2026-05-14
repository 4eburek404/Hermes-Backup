from __future__ import annotations

import copy
import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from flights_cli.errors import CliError
from flights_cli.reporting.final_answer_contract import (
    USER_ANSWER_SCHEMA_PACKAGE,
    USER_ANSWER_SCHEMA_RESOURCE,
    USER_ANSWER_SCHEMA_VERSION,
    build_user_answer_contract,
    load_user_answer_schema,
    validate_user_answer_contract,
)
from tests.test_agent_report_contract import valid_option, valid_report


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
    def test_user_answer_schema_is_valid_package_resource(self) -> None:
        schema = load_user_answer_schema()
        text = resources.files(USER_ANSWER_SCHEMA_PACKAGE).joinpath(USER_ANSWER_SCHEMA_RESOURCE).read_text(encoding="utf-8")
        parsed = json.loads(text)

        Draft202012Validator.check_schema(schema)
        self.assertEqual(parsed["$id"], "urn:hermes:flights-cli:flight-search-user-answer:v1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], USER_ANSWER_SCHEMA_VERSION)
        self.assertLessEqual(len(text.encode("utf-8")), 10000)

    def test_builds_valid_user_answer_contract_from_agent_report(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())

        validate_user_answer_contract(answer)
        self.assertEqual(answer["schema_version"], USER_ANSWER_SCHEMA_VERSION)
        self.assertEqual(answer["primary_recommendation"]["id"], "assembled-1:SVX-DEL")
        self.assertEqual(answer["primary_recommendation"]["max_connections_per_journey"], 0)
        self.assertEqual(answer["stop_policy_status"]["policy"], "business_default")
        self.assertEqual(answer["evidence_status"]["provider_failure_count"], 1)
        self.assertTrue(answer["required_caveats"]["provider_failures_acknowledged"])
        self.assertTrue(answer["required_caveats"]["through_fare_verification_required"])

    def test_rejects_missing_provider_failure_acknowledgement(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["provider_failures_acknowledged"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertTrue(any("provider failures" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_missing_through_fare_verification(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["through_fare_verification_required"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertTrue(any("through-fare" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_missing_coverage_incompleteness_acknowledgement(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["coverage_incompleteness_acknowledged"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        self.assertTrue(any("incomplete coverage" in error["message"] for error in ctx.exception.details["errors"]))

    def test_rejects_missing_source_boundary_and_purchase_verification(self) -> None:
        answer = build_user_answer_contract(report_with_required_caveats())
        answer["required_caveats"]["source_boundaries_included"] = False
        answer["required_caveats"]["purchase_screen_verification_required"] = False

        with self.assertRaises(CliError) as ctx:
            validate_user_answer_contract(answer)

        messages = " ".join(error["message"] for error in ctx.exception.details["errors"])
        self.assertIn("source-boundary", messages)
        self.assertIn("purchase-screen", messages)


if __name__ == "__main__":
    unittest.main()
