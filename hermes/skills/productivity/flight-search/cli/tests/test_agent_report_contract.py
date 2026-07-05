from __future__ import annotations

import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from flights_cli.errors import CliError
from flights_cli.output import render_agent_report_user_text
from flights_cli.reporting.user_answer import validate_user_answer
from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import (
    AGENT_REPORT_SCHEMA_PACKAGE,
    AGENT_REPORT_SCHEMA_RESOURCE,
    AGENT_REPORT_SCHEMA_VERSION,
    load_agent_report_schema,
    validate_agent_report,
)
from tests.fixtures.agent_reports import aggregate_offer, provider_report_payload


def semantic_error_paths(exc: CliError) -> set[str]:
    return {
        str(error.get("path"))
        for error in (exc.details or {}).get("errors") or []
        if isinstance(error, dict) and error.get("validator") == "semantic"
    }


def recursive_mapping_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(recursive_mapping_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(recursive_mapping_keys(item))
        return keys
    return set()


class AgentReportContractTests(unittest.TestCase):
    def test_schema_is_valid_v5_and_stable(self) -> None:
        schema = load_agent_report_schema()

        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["$id"], "urn:hermes:flights-cli:agent-report:v5")
        self.assertEqual(schema["title"], "Hermes Flights CLI Agent Report v5")
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
        self.assertIs(schema["additionalProperties"], False)

    def test_schema_loads_as_package_resource_and_stays_compact(self) -> None:
        text = (
            resources.files(AGENT_REPORT_SCHEMA_PACKAGE)
            .joinpath(AGENT_REPORT_SCHEMA_RESOURCE)
            .read_text(encoding="utf-8")
        )
        parsed = json.loads(text)

        self.assertEqual(parsed["$id"], "urn:hermes:flights-cli:agent-report:v5")
        self.assertLessEqual(len(text.encode("utf-8")), 14000)

    def test_build_agent_report_emits_compact_v5_public_contract(self) -> None:
        report = build_agent_report(provider_report_payload())

        validate_agent_report(report)
        validate_user_answer(report["user_answer"])
        self.assertEqual(report["schema_version"], "agent_report.v5")
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
        self.assertNotIn("flow_decision", report["route"])
        self.assertNotIn("evidence_plan", report["route"])
        self.assertEqual(set(report["frontier"]), {"decision_frontier"})
        self.assertEqual(
            report["frontier"]["decision_frontier"]["schema_version"],
            "flight_decision_frontier.public.v1",
        )
        self.assertEqual(
            set(report["evidence"]),
            {
                "coverage",
                "direct_flights",
                "provider_failures",
                "ru_priority_controls",
                "source_boundaries",
                "through_fare_checks",
            },
        )
        self.assertEqual(
            set(report["user_answer"]),
            {
                "schema_version",
                "answer_mode",
                "route",
                "catalog",
                "primary_recommendation",
                "alternatives",
                "evidence_status",
                "required_caveats",
                "stop_policy_status",
                "rendered_text",
                "answer_lines",
            },
        )

    def test_public_frontier_is_compact_projection_only(self) -> None:
        payload = provider_report_payload()
        payload["live_search"]["decision_frontier"] = {
            "schema_version": "flight_decision_frontier.v1",
            "options": [
                {
                    "id": "frontier-1",
                    "rank": 1,
                    "source_type": "provider_full_route",
                    "provider": "kupibilet",
                    "source_providers": ["kupibilet"],
                    "gateway": "SVO",
                    "covers_requested_trip": True,
                    "journey_scope": "one_way",
                    "price": 42000,
                    "currency": "RUB",
                    "price_basis": "provider_offer",
                    "ticketing_model": "provider_aggregate",
                    "detail_status": "full",
                    "connection_count": 1,
                    "selection_reasons": ["primary"],
                    "evidence_sources": [
                        {
                            "source_type": "provider_full_route",
                            "source_providers": ["kupibilet"],
                        }
                    ],
                    "price_comparison": {"cheapest": True},
                    "journeys": [
                        {
                            "direction": "outbound",
                            "segments": aggregate_offer()["segments"],
                        }
                    ],
                    "connections": [{"arrival_airport": "SVO"}],
                    "rank_features": {"price_score": 0.9},
                    "graph_data": {"node_count": 3},
                    "raw_evidence": {"body": {"offers": [aggregate_offer()]}},
                }
            ],
            "controls": [
                {
                    "id": "control-1",
                    "type": "full_route_aggregate",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "status": "ok",
                    "provider": "kupibilet",
                    "offer_count": 1,
                    "top_offer_count": 1,
                    "error": {"raw_body": "hidden"},
                    "top_offers": [aggregate_offer()],
                }
            ],
            "coverage_summary": {"option_count": 1, "control_count": 1},
        }

        report = build_agent_report(payload)

        validate_agent_report(report)
        frontier = report["frontier"]["decision_frontier"]
        option = frontier["options"][0]
        control = frontier["controls"][0]
        self.assertEqual(frontier["schema_version"], "flight_decision_frontier.public.v1")
        self.assertEqual(option["id"], "frontier-1")
        self.assertEqual(option["catalog_item_number"], 1)
        self.assertEqual(
            option["catalog_item_path"],
            "data.agent_report.user_answer.catalog.items[0]",
        )
        self.assertNotIn("journeys", option)
        self.assertNotIn("connections", option)
        self.assertNotIn("rank_features", option)
        self.assertNotIn("raw_evidence", option)
        self.assertNotIn("error", control)
        self.assertNotIn("top_offers", control)
        self.assertFalse(
            {"journeys", "connections", "rank_features", "graph_data", "raw_evidence"}
            & recursive_mapping_keys(frontier)
        )

    def test_user_text_report_renderer_preserves_canonical_answer_lines(self) -> None:
        report = build_agent_report(provider_report_payload())
        user_answer = report["user_answer"]

        rendered = render_agent_report_user_text(report)

        self.assertEqual(rendered, user_answer["rendered_text"])
        self.assertEqual(
            [line for line in rendered.splitlines() if line.strip()],
            user_answer["answer_lines"],
        )
        self.assertGreater(len(user_answer["answer_lines"]), 1)

    def test_agent_guidance_matches_compact_coverage(self) -> None:
        payload = provider_report_payload()
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
        self.assertEqual(guidance["blocking_evidence"], coverage["blocking_evidence"])
        self.assertEqual(
            guidance["next_actions"][0]["id"], "rerun_with_larger_execution_budget"
        )

    def test_source_boundaries_require_metadata_availability_distinction(self) -> None:
        report = build_agent_report(provider_report_payload())
        report["evidence"]["source_boundaries"] = [
            "Segment assembly prices direct one-way legs and does not construct GDS."
        ]

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertIn(
            "$.evidence.source_boundaries", semantic_error_paths(ctx.exception)
        )


if __name__ == "__main__":
    unittest.main()
