from __future__ import annotations

from copy import deepcopy
import unittest

from flights_cli.commands.search import build_search_result
from flights_cli.commands.common import validate_contract_payload
from flights_cli.errors import CliError
from flights_cli.execution.search_evidence import SearchEvidence
from flights_cli.pipeline.result_contract import validate_flight_search_result
from flights_cli.reporting.user_answer import render_user_answer
from tests.fixtures.result_fixtures import valid_report


def valid_result() -> dict:
    fixture = valid_report()
    answer = fixture["user_answer"]
    option_ids = [item["option_id"] for item in answer["catalog"]["items"]]
    projection = {
        "route": {
            "origin": "SVX",
            "destination": "DEL",
            "origin_airports": ["SVX"],
            "destination_airports": ["DEL"],
            "dates": {"depart": "2026-06-01", "return": None},
            "profile": "business",
            "routing_strategy": "ru-priority",
            "provider_policy": "kupibilet",
        },
        "evidence": {
            "source_boundaries": [],
            "coverage": {
                "coverage_mode": "targeted",
                "negative_evidence_type": "bounded_live_controls_only",
                "coverage_warnings": ["segment_absence_is_not_route_absence"],
                "counts": {
                    "planned_controls": 1,
                    "searched_controls": 0,
                    "skipped_controls": 0,
                    "failed_controls": 0,
                    "not_supported_controls": 0,
                    "not_executed_controls": 1,
                    "deduped_controls": 0,
                },
                "completeness": {
                    "planned_count": 1,
                    "terminal_count": 1,
                    "all_planned_controls_have_terminal_state": True,
                },
                "blocking_evidence": ["not_executed_controls"],
                "non_blocking_boundaries": [],
            },
            "provider_failures": [],
            "through_fare_checks": [],
        },
        "frontier": {
            "schema_version": "flight_decision_frontier.result.v1",
            "option_ids": option_ids,
            "coverage_summary": {
                "candidate_count": 1,
                "acceptable_count": 1,
                "selected_count": 1,
                "rejected_count": 0,
                "control_count": 1,
            },
        },
        "answer": answer,
    }
    request = {
        "schema_version": "flight_search_request.v1",
        "origin": "SVX",
        "destination": "DEL",
        "depart_date": "2026-06-01",
        "return_date": None,
        "currency": "RUB",
        "profile": "business",
        "ticketing": "separate",
        "provider_policy": "kupibilet",
    }
    return build_search_result(request, projection)


class ResultContractTests(unittest.TestCase):
    def test_search_evidence_is_deeply_frozen_and_trace_is_defensive(self) -> None:
        evidence = SearchEvidence.freeze(
            search_plan={"route_context": {"origin": "SVX", "nested": {"items": [1]}}},
            provider_policy="tutu",
            primary_offer_results=[
                {
                    "raw_payload": {"secret": True},
                    "session_id": "provider-session",
                    "offer_count": 0,
                }
            ],
            gateway_leg_results={},
            aggregate_controls=[],
            observed_gateway_diagnostics={},
            probe_ledger={},
            failures=[],
            direct_mode={},
            max_connections_by_direction={},
            direct_presence_gate={},
            direct_inventory_searches=[],
            direct_inventory_results=[],
            date_window_inventory=None,
        )

        with self.assertRaises(TypeError):
            evidence.route_context["origin"] = "LED"
        with self.assertRaises(TypeError):
            evidence.route_context["nested"]["items"].append(2)
        trace = evidence.to_trace_dict()
        trace["provider_policy"] = "changed"
        self.assertEqual(evidence.provider_policy, "tutu")
        self.assertEqual(trace["primary_offer_results"], [{"offer_count": 0}])

    def test_result_v6_has_one_public_output_path(self) -> None:
        result = valid_result()

        self.assertEqual(
            set(result),
            {"schema_version", "request", "route", "evidence", "frontier", "answer"},
        )
        self.assertEqual(
            result["answer"]["rendered_text"],
            render_user_answer(result["answer"], result["route"]),
        )

    def test_catalog_order_must_equal_frontier_order(self) -> None:
        result = valid_result()
        result["frontier"]["option_ids"] = ["unknown"]

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_unknown_result_property_is_rejected(self) -> None:
        result = valid_result()
        result["unknown"] = True

        with self.assertRaises(CliError):
            validate_contract_payload("search_result", result)

    def test_segment_continuity_and_layover_drift_are_rejected(self) -> None:
        result = valid_result()
        item = result["answer"]["catalog"]["items"][0]
        first = item["directions"]["outbound"]["segments"][0]
        second = deepcopy(first)
        second.update(
            {
                "flight_number": "SU999",
                "origin": "SVO",
                "origin_label": "SVO",
                "destination": "LED",
                "destination_label": "LED",
                "departure_at": "2026-06-02T09:00:00+03:00",
                "arrival_at": "2026-06-02T10:30:00+03:00",
            }
        )
        item["directions"]["outbound"]["segments"].append(second)
        item["directions"]["outbound"]["layovers"].append(
            {"airport": "SVO", "duration_min": 1}
        )

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_arrival_before_departure_is_rejected(self) -> None:
        result = valid_result()
        segment = result["answer"]["catalog"]["items"][0]["directions"]["outbound"][
            "segments"
        ][0]
        segment["arrival_at"] = "2026-06-01T20:00:00+03:00"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_incomplete_visible_direction_is_rejected(self) -> None:
        result = valid_result()
        direction = result["answer"]["catalog"]["items"][0]["directions"]["outbound"]
        direction["segments"] = []
        direction["layovers"] = []
        direction["elapsed_min"] = None

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_direction_endpoints_must_match_request(self) -> None:
        result = valid_result()
        segment = result["answer"]["catalog"]["items"][0]["directions"]["outbound"][
            "segments"
        ][0]
        segment["origin"] = "LED"
        segment["origin_label"] = "LED"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_segment_and_elapsed_durations_must_match_timestamps(self) -> None:
        result = valid_result()
        direction = result["answer"]["catalog"]["items"][0]["directions"]["outbound"]
        direction["segments"][0]["duration_min"] += 1
        direction["elapsed_min"] += 1

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_currency_mismatch_is_rejected(self) -> None:
        result = valid_result()
        result["answer"]["catalog"]["items"][0]["total_price"]["currency"] = "EUR"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_evidence_count_and_required_caveat_drift_are_rejected(self) -> None:
        result = valid_result()
        result["answer"]["evidence_status"]["terminal_control_count"] = 0
        result["answer"]["required_caveats"]["source_boundaries_included"] = False

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_round_trip_requires_return_direction(self) -> None:
        result = valid_result()
        result["request"]["return_date"] = "2026-06-10"
        result["route"]["dates"]["return"] = "2026-06-10"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_rendered_text_drift_is_rejected(self) -> None:
        result = valid_result()
        result["answer"]["rendered_text"] += " changed"

        with self.assertRaises(CliError):
            validate_flight_search_result(result)

    def test_segment_requires_offset_timestamp(self) -> None:
        result = valid_result()
        changed = deepcopy(result)
        segment = changed["answer"]["catalog"]["items"][0]["directions"]["outbound"][
            "segments"
        ][0]
        segment["departure_at"] = "2026-06-01T21:20:00"

        with self.assertRaises(CliError):
            validate_flight_search_result(changed)

    def test_missing_flight_number_is_allowed(self) -> None:
        result = valid_result()
        result["answer"]["catalog"]["items"][0]["directions"]["outbound"]["segments"][
            0
        ]["flight_number"] = None
        result["answer"]["rendered_text"] = render_user_answer(
            result["answer"], result["route"]
        )

        validate_flight_search_result(result)
        self.assertIn("номер рейса не предоставлен", result["answer"]["rendered_text"])


if __name__ == "__main__":
    unittest.main()
