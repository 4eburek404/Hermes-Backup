from __future__ import annotations

import copy
import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from flights_cli.errors import CliError
from flights_cli.reporting.agent_report_projector import project_agent_report
from flights_cli.reporting.user_answer import build_user_answer, validate_user_answer
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
    "evidence",
    "frontier",
    "user_answer",
    "agent_guidance",
    "diagnostics",
]
LEGACY_TOP_LEVEL_FIELDS = {
    "status",
    "source_boundaries",
    "hub_viability",
    "segment_searches",
    "provider_failures",
    "recommended_options",
    "priority_options",
    "aggregate_controls",
    "coverage_diagnostics",
    "offer_graph",
    "through_fare_checks",
    "rejected_pair_warnings",
    "answer_lines",
    "display",
    "human_answer",
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


def valid_offer_graph() -> dict:
    return {
        "algorithm": "unified_offer_graph.v1",
        "constraints": {
            "origin": "SVX",
            "destination": "DEL",
            "dates": {"depart_date": "2026-06-01"},
            "profile": "business",
            "routing_strategy": "ru-priority",
            "provider_policy": "kupibilet",
        },
        "collection": {
            "mode": "progressive",
            "phases": [
                "primary_segment_search",
                "targeted_controls",
                "frontier_projection",
            ],
            "stop_reason": "bounded_terminal_controls",
        },
        "evidence": {
            "coverage_mode": "targeted",
            "planned_control_count": 1,
            "terminal_control_count": 1,
            "searched_control_count": 0,
            "failed_control_count": 0,
            "not_supported_control_count": 0,
            "missing_evidence_count": 1,
            "provider_failure_count": 0,
        },
        "frontier": [
            {
                "option_id": "assembled-1:SVX-DEL",
                "source": "recommended_options",
                "role": "best_practical",
                "detail_status": "full",
                "evidence_status": "full",
            }
        ],
        "missing_evidence": [
            {
                "type": "exact_airport_direct",
                "direction": "outbound",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "reason": "not_reached_by_current_live_execution",
            }
        ],
        "capability_boundaries": [],
        "truth_language": {
            "inventory_scope": "live_provider_returned_inventory",
            "absence_claim": "bounded_live_controls_only",
            "direct_wording": "нашёл все прямые, которые вернул live-поставщик",
        },
    }


def valid_report() -> dict:
    report = {
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
            "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares.",
            "Static city, airport, route, carrier, and aircraft catalogs are metadata only and cannot prove flight availability or absence.",
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
        "offer_graph": valid_offer_graph(),
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
                    "lines": [
                        "SU232 01JUN SVO - DEL 21:20 - 06:00 борт 333 в полете 5:10"
                    ],
                    "text": "10 000 RUB | всего 6:10 | пересадок 0\nSU232 01JUN SVO - DEL 21:20 - 06:00 борт 333 в полете 5:10",
                }
            ],
        },
        "human_answer": {
            "format_version": "flight_human_answer.v1",
            "text": "Нашёл варианты SVX→DEL.\n\n**Лучшая пара / рекомендация**\n- SU232 21:20–06:00 +1 | 01 июн | без пересадки | всего 5ч10 | 10 000 ₽\n\n**Проверить перед покупкой**\n- single PNR/багаж не доказаны — проверить на booking screen.",
            "sections": [
                {
                    "title": "Лучшая пара / рекомендация",
                    "lines": [
                        "SU232 21:20–06:00 +1 | 01 июн | без пересадки | всего 5ч10 | 10 000 ₽"
                    ],
                },
                {
                    "title": "Проверить перед покупкой",
                    "lines": [
                        "single PNR/багаж не доказаны — проверить на booking screen."
                    ],
                },
            ],
        },
    }
    report["user_answer"] = build_user_answer(report)
    report["human_answer"]["text"] = report["user_answer"]["rendered_text"]
    return report


def valid_agent_report_v2(report: dict | None = None) -> dict:
    return project_agent_report(report or valid_report())


def validate_flat_agent_report(report: dict) -> None:
    validate_agent_report(valid_agent_report_v2(report))


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
        "moscow_via_ist_secondary_control": ru_priority_branch(),
        "decision": "no_viable_ru_priority_control",
    }


class AgentReportContractTests(unittest.TestCase):
    def test_schema_is_valid_and_stable(self) -> None:
        schema = load_agent_report_schema()

        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertEqual(schema["$id"], "urn:hermes:flights-cli:agent-report:v3")
        self.assertEqual(schema["title"], "Hermes Flights CLI Agent Report v3")
        self.assertEqual(
            schema["properties"]["schema_version"]["const"], AGENT_REPORT_SCHEMA_VERSION
        )
        self.assertEqual(schema["required"], EXPECTED_TOP_LEVEL_REQUIRED)
        self.assertNotIn("display", schema["required"])
        self.assertNotIn("answer_lines", schema["required"])
        self.assertNotIn("human_answer", schema["required"])
        self.assertIn("evidence", schema["properties"])
        self.assertIn("frontier", schema["properties"])
        self.assertIn("agent_guidance", schema["properties"])
        self.assertIn("diagnostics", schema["properties"])
        self.assertIn("user_answer", schema["properties"])
        self.assertIs(schema["additionalProperties"], False)

    def test_agent_guidance_projects_next_actions_for_missing_evidence(self) -> None:
        report = valid_agent_report_v2()

        guidance = report["agent_guidance"]
        self.assertEqual(guidance["primary_command"], "search --request")
        self.assertEqual(
            guidance["canonical_answer_path"],
            "data.agent_report.user_answer.rendered_text",
        )
        self.assertTrue(guidance["execution_complete"])
        self.assertFalse(guidance["evidence_complete"])
        self.assertEqual(guidance["answer_readiness"], "answerable_with_caveats")
        self.assertIn("not_executed_controls", guidance["blocking_evidence"])
        self.assertEqual(
            guidance["next_actions"][0]["id"], "rerun_with_larger_execution_budget"
        )
        self.assertEqual(
            guidance["next_actions"][0]["request_patch"]["evidence"]["no_live_cache"],
            True,
        )

    def test_schema_loads_as_package_resource_and_stays_compact(self) -> None:
        text = (
            resources.files(AGENT_REPORT_SCHEMA_PACKAGE)
            .joinpath(AGENT_REPORT_SCHEMA_RESOURCE)
            .read_text(encoding="utf-8")
        )
        parsed = json.loads(text)

        self.assertEqual(parsed["$id"], "urn:hermes:flights-cli:agent-report:v3")
        self.assertLessEqual(len(text.splitlines()), 700)
        self.assertLessEqual(len(text.encode("utf-8")), 12000)

    def test_valid_synthetic_agent_report_passes(self) -> None:
        report = valid_report()
        validate_flat_agent_report(report)
        validate_user_answer(report["user_answer"])
        self.assertEqual(
            report["user_answer"]["rendered_text"], report["human_answer"]["text"]
        )

    def test_source_boundaries_require_metadata_availability_distinction(self) -> None:
        report = valid_report()
        report["source_boundaries"] = [
            "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares."
        ]
        report["user_answer"] = build_user_answer(report)
        report["human_answer"]["text"] = report["user_answer"]["rendered_text"]

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertIn(
            "$.evidence.source_boundaries", semantic_error_paths(ctx.exception)
        )

    def test_agent_report_v2_runtime_mapping_does_not_expose_legacy_aliases(
        self,
    ) -> None:
        report = valid_agent_report_v2()

        self.assertEqual(
            set(report.keys()),
            {
                "schema_version",
                "route",
                "evidence",
                "frontier",
                "user_answer",
                "agent_guidance",
                "diagnostics",
            },
        )
        for legacy_key in LEGACY_TOP_LEVEL_FIELDS:
            with self.subTest(legacy_key=legacy_key):
                self.assertNotIn(legacy_key, report)
                self.assertIsNone(report.get(legacy_key))
                with self.assertRaises(KeyError):
                    _ = report[legacy_key]

    def test_schema_accepts_ru_priority_controls_for_ru_touching_international_route(
        self,
    ) -> None:
        report = valid_report()
        report["route"]["destination"] = "LON"
        report["route"]["destination_airports"] = ["LHR", "LGW", "STN", "LTN"]
        report["route"]["routing_strategy"] = "ru-priority"
        report["ru_priority_controls"] = valid_ru_priority_controls()

        validate_flat_agent_report(report)

    def test_ru_priority_branch_without_execution_state_fails_semantic_validation(
        self,
    ) -> None:
        report = valid_report()
        report["ru_priority_controls"] = valid_ru_priority_controls()
        del report["ru_priority_controls"]["moscow_gateway_control"]["execution_state"]

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertIn(
            "$.evidence.ru_priority_controls.moscow_gateway_control.execution_state",
            semantic_error_paths(ctx.exception),
        )

    def test_ru_priority_visible_true_with_viable_false_fails_semantic_validation(
        self,
    ) -> None:
        report = valid_report()
        option = copy.deepcopy(valid_option())
        option["id"] = "priority-direct"
        option["control_family"] = "ru_priority"
        option["control_branch"] = "direct_destination"
        option["visibility_role"] = "priority_control"
        report["priority_options"] = [option]
        report["ru_priority_controls"] = valid_ru_priority_controls()
        report["ru_priority_controls"]["direct_destination_control"] = (
            ru_priority_branch(
                execution_state="executed_no_viable_result",
                viable=False,
                visible=True,
                priority_option_id="priority-direct",
                evidence_option_ids=["priority-direct"],
            )
        )

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertIn(
            "$.evidence.ru_priority_controls.direct_destination_control.visible",
            semantic_error_paths(ctx.exception),
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

        validate_flat_agent_report(report)

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
        report["display"]["text"] = "\n\n".join(
            option["text"] for option in report["display"]["options"]
        )

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertIn(
            "$.diagnostics.display.options[1]", semantic_error_paths(ctx.exception)
        )

    def test_canonical_coverage_diagnostics_requires_terminal_fields(self) -> None:
        report = valid_report()

        validate_flat_agent_report(report)

    def test_canonical_coverage_diagnostics_rejects_old_minimal_shape(self) -> None:
        report = valid_report()
        for key in (
            "planned_controls",
            "failed_controls",
            "not_executed_controls",
            "deduped_controls",
            "completeness",
        ):
            del report["coverage_diagnostics"][key]

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        paths = semantic_error_paths(ctx.exception)
        self.assertIn("$.evidence.coverage_diagnostics.planned_controls", paths)
        self.assertIn("$.evidence.coverage_diagnostics.completeness", paths)

    def test_canonical_coverage_diagnostics_rejects_incomplete_terminal_semantics(
        self,
    ) -> None:
        report = valid_report()
        report["coverage_diagnostics"]["completeness"] = {
            "planned_count": 2,
            "terminal_count": 1,
            "all_planned_controls_have_terminal_state": False,
        }

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertTrue(
            any(
                error["validator"] == "semantic"
                for error in ctx.exception.details["errors"]
            )
        )

    def test_build_agent_report_always_projects_unified_offer_graph(self) -> None:
        report = build_agent_report(
            {
                "profile": "business",
                "assembly": {
                    "ranked_output_count": 0,
                    "ranked_total_count": 0,
                    "candidate_count": 0,
                    "candidate_pool_truncated": False,
                },
                "ranked_candidates": [],
                "frontier_candidates": [],
                "rejected_pairs": [],
                "live_search": {
                    "provider_policy": "kupibilet",
                    "plan": {
                        "origin": "SVX",
                        "destination": "DEL",
                        "origin_airports": ["SVX"],
                        "destination_airports": ["DEL"],
                        "dates": {"depart": "2026-06-01", "return": None},
                        "profile": "business",
                        "routing_strategy": "ru-priority",
                        "coverage_mode": "targeted",
                        "coverage_controls": [
                            {
                                "type": "full_route_aggregate",
                                "direction": "outbound",
                                "origin": "SVX",
                                "destination": "DEL",
                                "date": "2026-06-01",
                            }
                        ],
                    },
                    "hub_viability": [],
                    "segment_searches": [],
                    "aggregate_controls": [],
                    "failure_count": 0,
                    "failures": [],
                },
            }
        )

        graph = report["frontier"]["offer_graph"]
        self.assertEqual(graph["algorithm"], "unified_offer_graph.v1")
        self.assertEqual(graph["collection"]["mode"], "progressive")
        self.assertEqual(
            graph["truth_language"]["inventory_scope"],
            "live_provider_returned_inventory",
        )
        self.assertEqual(
            graph["truth_language"]["absence_claim"], "bounded_live_controls_only"
        )
        self.assertEqual(graph["evidence"]["planned_control_count"], 1)
        self.assertEqual(graph["evidence"]["terminal_control_count"], 1)
        self.assertEqual(graph["evidence"]["missing_evidence_count"], 1)
        self.assertEqual(
            graph["missing_evidence"][0]["reason"],
            "not_reached_by_current_live_execution",
        )
        self.assertEqual(report["schema_version"], "agent_report.v3")
        self.assertIn("evidence", report)
        self.assertIn("frontier", report)
        self.assertIn("diagnostics", report)
        serialized_report = json.loads(json.dumps(report, ensure_ascii=False))
        self.assertFalse(LEGACY_TOP_LEVEL_FIELDS & set(serialized_report))
        self.assertEqual(serialized_report["frontier"]["offer_graph"], graph)
        validate_user_answer(report["user_answer"])
        self.assertEqual(
            report["user_answer"]["rendered_text"],
            report["diagnostics"]["human_answer"]["text"],
        )

    def test_build_agent_report_projects_constraint_conflict_from_ranked_directs(
        self,
    ) -> None:
        direct_segment = {
            "direction": "outbound",
            "flight_number": "DP516",
            "carrier": "DP",
            "origin": "SVX",
            "destination": "MOW",
            "departure_at": "2026-08-06T05:40:00+05:00",
            "arrival_at": "2026-08-06T06:30:00+03:00",
            "aircraft_code": "73H",
            "duration_min": 170,
        }
        fallback_segments = [
            {
                "direction": "outbound",
                "flight_number": "SU1400",
                "carrier": "SU",
                "origin": "SVX",
                "destination": "KZN",
                "departure_at": "2026-08-06T15:35:00+05:00",
                "arrival_at": "2026-08-06T15:55:00+03:00",
                "aircraft_code": "32A",
                "duration_min": 140,
            },
            {
                "direction": "outbound",
                "flight_number": "SU1197",
                "carrier": "SU",
                "origin": "KZN",
                "destination": "MOW",
                "departure_at": "2026-08-06T18:00:00+03:00",
                "arrival_at": "2026-08-06T19:35:00+03:00",
                "aircraft_code": "32A",
                "duration_min": 95,
            },
        ]
        direct_candidate = {
            "id": "direct-morning",
            "rank": 2,
            "source_type": "provider_full_route",
            "provider": "tutu",
            "source_providers": ["tutu"],
            "covers_requested_trip": True,
            "journey_scope": "one_way",
            "ticketing_model": "unknown",
            "price": 10179,
            "currency": "RUB",
            "elapsed_min": 170,
            "journeys": [{"direction": "outbound", "segments": [direct_segment]}],
            "hard_constraint_violation": True,
            "hard_constraint_violations": [
                {
                    "reason": "first_departure_before_requested_time",
                    "first_departure_after": "15:00",
                    "actual_first_departure": "05:40",
                }
            ],
            "rank_components": {
                "hard_constraint_violation": 1,
                "not_covers_requested_trip": 0,
                "rejected_or_impossible_connection": 0,
                "max_connections_per_journey": 0,
            },
        }
        fallback_item = {
            "id": "one-stop-after-1500",
            "rank": 1,
            "source_type": "gateway_separate_ticket",
            "provider": "tutu",
            "source_providers": ["tutu"],
            "covers_requested_trip": True,
            "journey_scope": "one_way",
            "ticketing_model": "separate_segments",
            "price": 18100,
            "currency": "RUB",
            "elapsed_min": 360,
            "connection_count": 1,
            "journeys": [{"direction": "outbound", "segments": fallback_segments}],
            "selection_reasons": ["best_practical"],
        }

        report = build_agent_report(
            {
                "profile": "business",
                "assembly": {
                    "direct_mode": {"outbound": False},
                    "ranked_output_count": 1,
                    "ranked_total_count": 2,
                    "candidate_count": 2,
                    "candidate_pool_truncated": False,
                },
                "live_search": {
                    "provider_policy": "tutu",
                    "plan": {
                        "origin": "SVX",
                        "destination": "MOW",
                        "origin_airports": ["SVX"],
                        "destination_airports": ["SVO", "DME", "VKO"],
                        "dates": {"depart": "2026-08-06", "return": None},
                        "profile": "business",
                        "routing_strategy": "default",
                    },
                    "decision_frontier": {
                        "options": [fallback_item],
                        "coverage_summary": {
                            "candidate_count": 2,
                            "acceptable_count": 1,
                            "direct_option_count": 1,
                        },
                    },
                    "mixed_candidate_ranking": {
                        "ranked_candidates": [fallback_item, direct_candidate],
                        "rejected": [],
                    },
                    "direct_presence_gate": {
                        "schema_version": "flight_direct_presence_gate.v1",
                        "direct_evidence_present": {"outbound": True},
                        "direct_mode": {"outbound": True},
                        "source": "wave0_primary_offer_results",
                        "fallback": {
                            "status": "executed",
                            "reason": "constraints_emptied_direct_set",
                            "directions": ["outbound"],
                            "max_connections_per_journey": 1,
                        },
                    },
                    "hub_viability": [],
                    "segment_searches": [],
                    "aggregate_controls": [],
                    "failure_count": 0,
                    "failures": [],
                },
            }
        )

        validate_agent_report(report)
        user_answer = report["user_answer"]
        self.assertEqual(
            user_answer["primary_recommendation"]["id"], "one-stop-after-1500"
        )
        self.assertEqual(
            user_answer["evidence_status"]["answerability"],
            "answerable_with_caveats",
        )
        conflict = user_answer["constraint_conflict"]
        self.assertEqual(
            conflict["directions"][0]["direct_schedule"]["items"][0]["option_id"],
            "direct-morning",
        )
        self.assertIn("прямых рейсов после 15:00 нет", user_answer["rendered_text"])

    def test_v1_accepts_optional_omitted_counts(self) -> None:
        report = valid_report()
        report["omitted_counts"] = {
            "recommended_options": 2,
            "coverage_controls": 15,
            "option_segments": 3,
        }

        validate_flat_agent_report(report)

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
        report["answer_lines"].append(
            "Provider failure: 1 probe failed; see provider_failures for details."
        )

        validate_flat_agent_report(report)

    def test_v1_accepts_optional_stop_policy_fields(self) -> None:
        report = valid_report()
        report["stop_policy"] = {
            "name": "business_default",
            "preferred_max_connections": 1,
            "tier2_max_connections": 2,
            "hard_max_connections": 2,
            "two_stop_allowed_only_if_no_preferred": True,
            "three_plus_reportable": False,
        }
        report["stop_policy_diagnostics"] = {
            "policy": "business_default",
            "preferred_candidate_count": 1,
            "two_stop_candidate_count": 0,
            "three_plus_suppressed_count": 0,
            "used_two_stop_tier": False,
            "garbage_options_hidden_from_answer": False,
        }
        report["recommended_options"][0]["stop_tier"] = "T0_DIRECT"
        report["recommended_options"][0]["max_connections_per_journey"] = 0

        validate_flat_agent_report(report)

    def test_structured_risk_reasons_are_allowed(self) -> None:
        report = valid_report()
        report["recommended_options"][0]["risk"]["top_reasons"] = [
            {
                "scope": "carrier",
                "code": "preferred_carrier_match",
                "points": 0,
                "message": "Uses preferred carrier.",
            }
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

        validate_flat_agent_report(report)

    def test_coverage_diagnostics_requires_not_supported_bucket(self) -> None:
        report = valid_report()
        del report["coverage_diagnostics"]["not_supported_controls"]

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertTrue(
            any(
                error["validator"] == "semantic"
                and error["path"]
                == "$.evidence.coverage_diagnostics.not_supported_controls"
                for error in ctx.exception.details["errors"]
            )
        )

    def test_schema_defines_canonical_not_supported_coverage_bucket(self) -> None:
        schema = load_agent_report_schema()

        coverage_schema = schema["$defs"]["coverage_diagnostics"]
        self.assertIn("not_supported_controls", coverage_schema["required"])
        self.assertEqual(
            schema["$defs"]["search_evidence"]["properties"]["coverage_diagnostics"],
            {"$ref": "#/$defs/coverage_diagnostics"},
        )
        not_supported_schema = coverage_schema["properties"]["not_supported_controls"][
            "items"
        ]
        self.assertEqual(
            not_supported_schema["properties"]["execution_state"],
            {"const": "not_supported"},
        )
        self.assertEqual(
            not_supported_schema["properties"]["status"], {"const": "not_supported"}
        )

    def test_coverage_diagnostics_rejects_non_list_control_bucket(self) -> None:
        report = valid_report()
        report["coverage_diagnostics"]["not_supported_controls"] = "not-a-list"

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertIn(
            "$.evidence.coverage_diagnostics.not_supported_controls",
            semantic_error_paths(ctx.exception),
        )

    def test_not_supported_controls_require_not_supported_terminal_state(self) -> None:
        report = valid_report()
        report["coverage_diagnostics"]["not_supported_controls"] = [
            {
                "type": "full_route_aggregate",
                "direction": "outbound",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "provider": "fli",
                "execution_state": "not_executed",
                "status": "not_executed",
                "probe_id": "probe-not-supported-001",
            }
        ]

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertIn(
            "$.evidence.coverage_diagnostics.not_supported_controls[0].execution_state",
            semantic_error_paths(ctx.exception),
        )

    def test_missing_required_top_level_field_fails(self) -> None:
        report = valid_report()
        del report["source_boundaries"]

        with self.assertRaises(CliError) as ctx:
            validate_flat_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertIn(
            "$.evidence.source_boundaries", semantic_error_paths(ctx.exception)
        )

    def test_wrong_schema_version_fails(self) -> None:
        report = valid_agent_report_v2()
        report["schema_version"] = "agent_report.v2"

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertEqual(ctx.exception.details["schema_version"], "agent_report.v2")

    def test_extra_top_level_field_fails(self) -> None:
        report = valid_agent_report_v2()
        report["debug_dump"] = {}

        with self.assertRaises(CliError) as ctx:
            validate_agent_report(report)

        self.assertEqual(ctx.exception.error_type, "contract_error")
        self.assertTrue(
            any(
                error["validator"] == "additionalProperties"
                for error in ctx.exception.details["errors"]
            )
        )

    def test_priority_options_do_not_require_answer_line_keywords(self) -> None:
        report = valid_report()
        priority = copy.deepcopy(valid_option())
        priority["category"] = "all_su_svo"
        priority["rank"] = 4
        report["priority_options"] = [priority]
        report["answer_lines"] = ["Best CLI-ranked option: 10 000 RUB."]

        validate_flat_agent_report(report)

    def test_through_fare_checks_are_structured_evidence_not_answer_line_keywords(
        self,
    ) -> None:
        report = valid_report()
        report["through_fare_checks"] = [
            {
                "direction": "outbound",
                "route": "SVX->DEL",
                "date": "2026-06-01",
                "carrier": "SU",
                "reason": "Same-carrier priority option can be better priced or protected as an airline/GDS through fare.",
                "verify_with": [
                    "airline website",
                    "GDS/Sirena/Amadeus-capable seller",
                    "booking screen fare rules",
                ],
            }
        ]
        report["answer_lines"] = ["Best CLI-ranked option: 10 000 RUB."]

        validate_flat_agent_report(report)

    def test_provider_failures_are_structured_evidence_not_answer_line_keywords(
        self,
    ) -> None:
        report = valid_report()
        report["provider_failures"] = [
            {
                "direction": "outbound",
                "leg": "hub_to_destination",
                "origin": "IST",
                "destination": "FRA",
                "date": "2026-08-14",
                "provider": "fli",
                "error": {
                    "type": "upstream_error",
                    "message": "FLI MCP request failed: connection refused",
                },
            }
        ]
        report["answer_lines"] = ["Best CLI-ranked option: 10 000 RUB."]

        validate_flat_agent_report(report)

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
        self.assertEqual(report["evidence"]["provider_failures"][0]["provider"], "fli")

if __name__ == "__main__":
    unittest.main()
