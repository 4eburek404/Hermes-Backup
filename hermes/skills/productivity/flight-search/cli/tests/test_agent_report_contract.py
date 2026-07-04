from __future__ import annotations

import copy
import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from flights_cli.errors import CliError
from flights_cli.reporting.user_answer import build_user_answer, validate_user_answer
from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import (
    AGENT_REPORT_SCHEMA_PACKAGE,
    AGENT_REPORT_SCHEMA_RESOURCE,
    AGENT_REPORT_SCHEMA_VERSION,
    load_agent_report_schema,
    validate_agent_report,
)
from tests.test_provider_aggregate_candidates import report_payload


BANNED_TOP_LEVEL_FIELDS = {
    "diagnostics",
    "human_answer",
    "display",
    "answer_lines",
    "coverage_diagnostics",
    "offer_graph",
    "recommended_options",
    "priority_options",
    "aggregate_controls",
    "segment_searches",
    "hub_viability",
    "primary_offer_results",
    "rejected_pair_warnings",
    "stop_policy_diagnostics",
}
BANNED_EVIDENCE_FIELDS = {
    "coverage_diagnostics",
    "segment_searches",
    "hub_viability",
    "primary_offer_results",
    "aggregate_controls",
    "rejected_pair_warnings",
    "stop_policy_diagnostics",
}
BANNED_FRONTIER_FIELDS = {
    "offer_graph",
    "recommended_options",
    "priority_options",
}


def semantic_error_paths(exc: CliError) -> set[str]:
    return {
        str(error.get("path"))
        for error in (exc.details or {}).get("errors") or []
        if isinstance(error, dict) and error.get("validator") == "semantic"
    }


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
    report = {
        "schema_version": "internal_user_answer_fixture.v1",
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
            "direct_mode": {},
            "output_limits": {"catalog_limit": 10, "direct_catalog_limit": 30},
        },
        "source_boundaries": [],
        "provider_failures": [],
        "recommended_options": [valid_option()],
        "priority_options": [],
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
            "not_supported_controls": [],
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
        "offer_graph": {
            "truth_language": {
                "inventory_scope": "live_provider_returned_inventory",
                "absence_claim": "bounded_live_controls_only",
                "negative_wording": "not no-flight evidence",
            }
        },
        "through_fare_checks": [],
        "stop_policy": {"name": "business_default", "preferred_max_connections": 1},
        "stop_policy_diagnostics": {
            "policy": "business_default",
            "used_two_stop_tier": False,
            "three_plus_suppressed_count": 0,
            "garbage_options_hidden_from_answer": False,
        },
        "answer_lines": ["legacy fixture line ignored by canonical user_answer"],
        "display": {"text": "legacy fixture display ignored by canonical user_answer"},
    }
    report["user_answer"] = build_user_answer(report)
    return report


class AgentReportContractTests(unittest.TestCase):
    def test_schema_is_valid_v4_and_stable(self) -> None:
        schema = load_agent_report_schema()

        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["$id"], "urn:hermes:flights-cli:agent-report:v4")
        self.assertEqual(schema["title"], "Hermes Flights CLI Agent Report v4")
        self.assertEqual(
            schema["properties"]["schema_version"]["const"], AGENT_REPORT_SCHEMA_VERSION
        )
        self.assertEqual(
            schema["required"],
            [
                "schema_version",
                "route",
                "evidence",
                "frontier",
                "user_answer",
                "agent_guidance",
            ],
        )
        self.assertNotIn("diagnostics", schema["properties"])
        self.assertIs(schema["additionalProperties"], False)

    def test_schema_loads_as_package_resource_and_stays_compact(self) -> None:
        text = (
            resources.files(AGENT_REPORT_SCHEMA_PACKAGE)
            .joinpath(AGENT_REPORT_SCHEMA_RESOURCE)
            .read_text(encoding="utf-8")
        )
        parsed = json.loads(text)

        self.assertEqual(parsed["$id"], "urn:hermes:flights-cli:agent-report:v4")
        self.assertLessEqual(len(text.encode("utf-8")), 14000)

    def test_build_agent_report_emits_compact_v4_public_contract(self) -> None:
        report = build_agent_report(report_payload())

        validate_agent_report(report)
        validate_user_answer(report["user_answer"])
        self.assertEqual(report["schema_version"], "agent_report.v4")
        self.assertEqual(
            set(report),
            {
                "schema_version",
                "route",
                "evidence",
                "frontier",
                "user_answer",
                "agent_guidance",
            },
        )
        self.assertFalse(BANNED_TOP_LEVEL_FIELDS & set(report))
        self.assertFalse(BANNED_EVIDENCE_FIELDS & set(report["evidence"]))
        self.assertFalse(BANNED_FRONTIER_FIELDS & set(report["frontier"]))
        self.assertEqual(set(report["frontier"]), {"decision_frontier"})
        self.assertIn("coverage", report["evidence"])
        self.assertIn("rendered_text", report["user_answer"])

    def test_user_answer_rendered_text_is_only_public_final_text_source(self) -> None:
        report = build_agent_report(report_payload())
        serialized = json.loads(json.dumps(report, ensure_ascii=False))

        self.assertIn("rendered_text", serialized["user_answer"])
        self.assertNotIn("diagnostics", serialized)
        self.assertNotIn("human_answer", serialized)
        self.assertNotIn("display", serialized)
        self.assertNotIn("answer_lines", serialized)
        self.assertIn("answer_lines", serialized["user_answer"])

    def test_agent_guidance_matches_compact_coverage(self) -> None:
        payload = report_payload()
        payload["live_search"]["probe_ledger"] = {
            "coverage_mode": "targeted",
            "negative_evidence_type": "bounded_live_controls_only",
            "planned_controls": [
                {
                    "type": "full_route_aggregate",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "probe_id": "agg-probe-001",
                }
            ],
            "searched_controls": [],
            "skipped_controls": [],
            "failed_controls": [],
            "not_supported_controls": [],
            "not_executed_controls": [
                {
                    "type": "full_route_aggregate",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "execution_state": "not_executed",
                    "status": "not_executed",
                    "probe_id": "agg-probe-001",
                }
            ],
            "deduped_controls": [],
            "completeness": {
                "planned_count": 1,
                "terminal_count": 1,
                "all_planned_controls_have_terminal_state": True,
            },
        }
        report = build_agent_report(payload)

        validate_agent_report(report)
        coverage = report["evidence"]["coverage"]
        guidance = report["agent_guidance"]
        self.assertEqual(guidance["execution_complete"], True)
        self.assertEqual(guidance["evidence_complete"], False)
        self.assertEqual(
            guidance["blocking_evidence"], coverage["blocking_evidence"]
        )
        self.assertEqual(
            guidance["next_actions"][0]["id"], "rerun_with_larger_execution_budget"
        )

    def test_source_boundaries_require_metadata_availability_distinction(self) -> None:
        report = build_agent_report(report_payload())
        report["evidence"]["source_boundaries"] = [
            "Segment assembly prices direct one-way legs and does not construct GDS."
        ]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertIn(
            "$.evidence.source_boundaries", semantic_error_paths(ctx.exception)
        )

    def test_legacy_public_fields_fail_semantic_validation(self) -> None:
        report = build_agent_report(report_payload())
        polluted = copy.deepcopy(report)
        polluted["frontier"]["offer_graph"] = {}
        polluted["frontier"]["recommended_options"] = []
        polluted["frontier"]["priority_options"] = []
        polluted["diagnostics"] = {}

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(polluted)

        paths = semantic_error_paths(ctx.exception)
        self.assertIn("$.frontier." + "offer_graph", paths)
        self.assertIn("$.frontier." + "recommended_options", paths)
        self.assertIn("$.frontier." + "priority_options", paths)
        self.assertIn("$.diagnostics", paths)


if __name__ == "__main__":
    unittest.main()
