from __future__ import annotations

from flights_cli.reporting.user_answer import UserAnswerInput, build_user_answer


def aggregate_offer() -> dict:
    return {
        "id": "agg-su-del",
        "price": 42000,
        "currency": "RUB",
        "change_count": 1,
        "duration_min": 520,
        "flight_numbers": ["SU1419", "SU232"],
        "carriers": ["SU"],
        "segments": [
            {
                "flight_number": "SU1419",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "SVO",
                "departure_at": "2026-06-01T06:00:00+05:00",
                "arrival_at": "2026-06-01T06:40:00+03:00",
            },
            {
                "flight_number": "SU232",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "DEL",
                "departure_at": "2026-06-01T10:30:00+03:00",
                "arrival_at": "2026-06-01T18:50:00+05:30",
            },
        ],
        "ticketing_note": "Provider-assembled route offer; verify single-PNR/protection, baggage, and final fare on the booking screen.",
    }


def return_aggregate_offer(*, price: int = 43000, currency: str = "RUB") -> dict:
    return {
        **aggregate_offer(),
        "id": "agg-return",
        "price": price,
        "currency": currency,
        "segments": [
            {
                "flight_number": "SU233",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "DEL",
                "destination": "SVO",
                "departure_at": "2026-07-24T08:00:00+05:30",
                "arrival_at": "2026-07-24T12:30:00+03:00",
            },
            {
                "flight_number": "SU1418",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "SVX",
                "departure_at": "2026-07-24T15:30:00+03:00",
                "arrival_at": "2026-07-24T20:00:00+05:00",
            },
        ],
    }


def add_return_aggregate_control(payload: dict, offer: dict | None = None) -> None:
    payload["live_search"]["aggregate_controls"].append(
        {
            "direction": "return",
            "origin": "DEL",
            "destination": "SVX",
            "date": "2026-07-24",
            "status": "ok",
            "provider": "kupibilet",
            "filters": {"direct_only": False},
            "offer_count": 1,
            "raw_variant_count": 1,
            "top_offers": [offer or return_aggregate_offer()],
            "error": None,
        }
    )


def provider_report_payload() -> dict:
    return {
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
            "aggregate_controls": [
                {
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "DEL",
                    "date": "2026-06-01",
                    "status": "ok",
                    "provider": "kupibilet",
                    "filters": {"direct_only": False, "only_carriers": ["SU"]},
                    "offer_count": 1,
                    "raw_variant_count": 1,
                    "top_offers": [aggregate_offer()],
                    "error": None,
                }
            ],
            "failure_count": 0,
            "failures": [],
        },
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
            "candidate_pool_truncated": False,
            "failure_count": 0,
            "direct_mode": {},
            "output_limits": {"catalog_limit": 10, "direct_catalog_limit": 30},
        },
        "source_boundaries": [],
        "provider_failures": [],
        "primary_options": [valid_option()],
        "alternative_options": [],
        "coverage_report": {
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
        "truth_language": {
            "inventory_scope": "live_provider_returned_inventory",
            "absence_claim": "bounded_live_controls_only",
            "negative_wording": "not no-flight evidence",
        },
        "through_fare_checks": [],
        "stop_policy": {"name": "business_default", "preferred_max_connections": 1},
        "stop_policy_status": {
            "policy": "business_default",
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
        status=report["status"],
        source_boundaries=report["source_boundaries"],
        provider_failures=report["provider_failures"],
        primary_options=report["primary_options"],
        alternative_options=report["alternative_options"],
        coverage_report=report["coverage_report"],
        stop_policy=report["stop_policy"],
        stop_policy_status=report["stop_policy_status"],
        through_fare_checks=report["through_fare_checks"],
        truth_language=report["truth_language"],
    )


def report_with_required_caveats() -> dict:
    report = valid_report()
    priority = valid_option()
    priority["id"] = "priority-svo"
    priority["category"] = "moscow_gateway_control"
    report["alternative_options"] = [priority]
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
    return report
