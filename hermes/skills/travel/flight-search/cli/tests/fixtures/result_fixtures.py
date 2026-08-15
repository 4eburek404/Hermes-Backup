from __future__ import annotations

from flights_cli.reporting.coverage import CoverageSnapshot
from flights_cli.reporting.user_answer import UserAnswerInput, build_user_answer


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
        "elapsed_min": 1410,
        "elapsed": "23h30m",
        "carriers": ["SU"],
        "risk": {"score": 1, "grade": "good", "reject": False, "top_reasons": []},
        "validation_summary": {"ok": True},
        "connections": [],
        "segments": [
            {
                "direction": "outbound",
                "flight_number": "SU1419",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "SVO",
                "departure_at": "2026-06-01T06:00:00+05:00",
                "arrival_at": "2026-06-01T06:40:00+03:00",
                "aircraft_code": "738",
                "duration_min": 160,
            },
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
                "duration_min": 370,
            },
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
            "failure_count": 0,
            "direct_mode": {},
            "output_limits": {"catalog_limit": 10, "direct_catalog_limit": 30},
        },
        "source_boundaries": [],
        "primary_options": [valid_option()],
        "alternative_options": [],
        "coverage_report": {
            "negative_evidence_type": "bounded_live_probes_only",
            "planned_probes": [
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
            "searched_probes": [],
            "skipped_probes": [],
            "failed_probes": [],
            "unsupported_probes": [],
            "not_executed_probes": [
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
            "deduped_probes": [],
            "coverage_warnings": ["segment_absence_is_not_route_absence"],
            "completeness": {
                "planned_count": 1,
                "terminal_count": 1,
                "all_planned_probes_have_terminal_state": True,
            },
        },
        "stop_policy": {"name": "business_default", "preferred_max_connections": 1},
        "stop_policy_status": {
            "policy": "business_default",
            "max_reported_connections": 1,
            "used_two_stop_tier": False,
            "three_plus_suppressed_count": 0,
            "garbage_options_hidden_from_answer": False,
        },
    }
    report["user_answer"] = build_user_answer(answer_input_from_fixture(report))
    return report


def answer_input_from_fixture(report: dict) -> UserAnswerInput:
    return UserAnswerInput(
        route=report["route"],
        source_boundaries=report["source_boundaries"],
        coverage_snapshot=CoverageSnapshot.from_diagnostics(report["coverage_report"]),
        primary_options=report["primary_options"],
        alternative_options=report["alternative_options"],
        stop_policy=report["stop_policy"],
        stop_policy_status=report["stop_policy_status"],
    )


def report_with_required_caveats() -> dict:
    report = valid_report()
    priority = valid_option()
    priority["id"] = "priority-svo"
    priority["category"] = "moscow_gateway_option"
    report["alternative_options"] = [priority]
    report["coverage_report"]["planned_probes"].append(
        {
            "probe_id": "probe-tutu-failure",
            "provider": "tutu",
            "execution_state": "planned",
        }
    )
    report["coverage_report"]["failed_probes"] = [
        {
            "direction": "outbound",
            "leg": "hub_to_destination",
            "origin": "IST",
            "destination": "LHR",
            "date": "2026-06-01",
            "provider": "tutu",
            "cache_status": "unknown",
            "probe_id": "probe-tutu-failure",
            "error": {"type": "upstream_error", "message": "Tutu unavailable"},
        }
    ]
    report["coverage_report"]["completeness"] = {
        "planned_count": 2,
        "terminal_count": 2,
        "all_planned_probes_have_terminal_state": True,
    }
    return report
