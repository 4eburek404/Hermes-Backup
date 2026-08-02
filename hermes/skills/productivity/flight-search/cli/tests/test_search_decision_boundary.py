from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from flights_cli.orchestrators.search_plan_builder import SearchPlanBuilder
from flights_cli.pipeline.result_builder import build_projection_input
from flights_cli.pipeline.direct_gate import candidate_is_direct
from flights_cli.pipeline.frontier_selection import build_decision_frontier
from flights_cli.pipeline.search_decision import SearchDecisionBuilder
from flights_cli.store import Store
from helpers import live_assembly_args


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        route=SimpleNamespace(dates={"depart": "2026-08-01", "return": None}),
        decision_policy=SimpleNamespace(
            max_connections_per_journey=2,
            preferred_connections=1,
            min_same_airport_connection_min=120,
            min_cross_airport_connection_min=300,
            max_layover_min=1440,
            preferred_layover_max_min=360,
        ),
        output_policy=SimpleNamespace(
            catalog_limit=10,
            direct_catalog_limit=30,
            max_gateway_alternatives=2,
            max_primary_gateway_options=4,
            max_options_per_first_carrier=2,
            max_round_trip_pairs=12,
        ),
    )


def _evidence() -> SimpleNamespace:
    route = {
        "origin": "SVX",
        "destination": "LED",
        "origin_airports": ["SVX"],
        "destination_airports": ["LED"],
        "dates": {"depart": "2026-08-01", "return": None},
        "currency": "RUB",
        "direct_only": False,
        "hubs": [],
    }
    primary_result: dict[str, Any] = {
        "provider": "fake",
        "source_type": "provider_full_route",
        "direction": "outbound",
        "origin": "SVX",
        "destination": "LED",
        "top_offers": [
            {
                "id": "fake-direct",
                "price": 12_000,
                "currency": "RUB",
                "segments": [
                    {
                        "origin": "SVX",
                        "destination": "LED",
                        "departure_at": "2026-08-01T08:00:00+05:00",
                        "arrival_at": "2026-08-01T10:30:00+03:00",
                    }
                ],
            }
        ],
    }
    return SimpleNamespace(
        route_context=route,
        search_plan={
            "schema_version": "flight_search_plan.v5",
            "route": route,
            "gateway_policy": {"discovery": {}},
        },
        provider_policy="all",
        primary_offer_results=(primary_result,),
        gateway_leg_results={},
        observed_gateway_diagnostics={},
        probe_ledger={
            "planned_probes": [],
            "searched_probes": [],
            "skipped_probes": [],
            "failed_probes": [],
            "unsupported_probes": [],
            "not_executed_probes": [],
            "deduped_probes": [],
        },
        direct_mode={"outbound": True},
        max_connections_by_direction={"outbound": 0},
        direct_presence_gate={"direct_mode": {"outbound": True}},
        direct_inventory_searches=(),
    )


def test_search_decision_builder_is_a_pure_evidence_projection() -> None:
    decision = SearchDecisionBuilder.build(_plan(), _evidence())

    assert decision.offer_graph["coverage"]["offer_count"] == 1
    assert decision.offer_candidates["coverage"]["candidate_count"] == 1
    assert [option["id"] for option in decision.decision_frontier["options"]] == [
        "candidate:primary_offer:fake:fake-direct"
    ]


def test_search_decision_uses_plan_limits_when_request_limits_conflict() -> None:
    request = live_assembly_args(
        origin="SVX",
        destination="LED",
        depart_date="2026-08-01",
        return_date=None,
    )
    built = SearchPlanBuilder(Store()).build(request)
    plan = replace(
        built,
        decision_policy=replace(
            built.decision_policy,
            min_same_airport_connection_min=777,
            max_layover_min=888,
            preferred_layover_max_min=333,
        ),
        output_policy=replace(
            built.output_policy,
            direct_catalog_limit=1,
            max_gateway_alternatives=0,
            max_primary_gateway_options=1,
            max_options_per_first_carrier=1,
            max_round_trip_pairs=2,
        ),
    )
    assert (
        request.output.direct_catalog_limit != plan.output_policy.direct_catalog_limit
    )
    evidence = _evidence()
    evidence.primary_offer_results[0]["top_offers"].append(
        {
            "id": "fake-direct-second",
            "price": 13_000,
            "currency": "RUB",
            "segments": [
                {
                    "origin": "SVX",
                    "destination": "LED",
                    "departure_at": "2026-08-01T11:00:00+05:00",
                    "arrival_at": "2026-08-01T13:30:00+03:00",
                }
            ],
        }
    )
    evidence.primary_offer_results[0]["offer_count"] = 2

    decision = SearchDecisionBuilder.build(plan, evidence)
    scorer = decision.scored_decisions["scorer"]

    assert len(decision.decision_frontier["options"]) == 1
    assert scorer["max_options"] == 1
    assert scorer["min_same_airport_connection_min"] == 777
    assert scorer["max_layover_min"] == 888
    assert scorer["preferred_layover_max_min"] == 333
    assert scorer["max_gateway_alternatives"] == 0
    assert scorer["max_primary_gateway_options"] == 1
    assert scorer["max_options_per_first_carrier"] == 1
    assert scorer["max_round_trip_pairs"] == 2


def test_projection_input_binds_existing_decision_and_optional_inventory() -> None:
    plan = _plan()
    evidence = _evidence()
    evidence.probe_ledger["failed_probes"] = [
        {
            "probe_id": "provider-failure",
            "provider": "fake",
            "error": {"type": "upstream_error", "message": "offline"},
        }
    ]
    decision = SearchDecisionBuilder.build(plan, evidence)
    inventory = {"schema_version": "flight_date_window_inventory.v1"}

    projection = build_projection_input(
        plan,
        evidence,
        decision,
        date_window_inventory=inventory,
    )

    assert projection["count"] == 1
    assert projection["live_search"]["candidate_input_ids"] == [
        "candidate:primary_offer:fake:fake-direct"
    ]
    assert projection["live_search"]["date_window_inventory"] == inventory
    assert (
        projection["live_search"]["diagnostics"]["search_plan"]["schema_version"]
        == "flight_search_plan.v5"
    )
    assert "failure_count" not in projection["live_search"]
    assert "failures" not in projection["live_search"]
    assert len(projection["live_search"]["probe_ledger"]["failed_probes"]) == 1


def test_atomic_round_trip_uses_the_same_direct_predicate_in_frontier() -> None:
    candidate = {
        "id": "direct-round-trip",
        "rank": 1,
        "source_type": "provider_full_route",
        "covers_requested_trip": True,
        "journeys": [
            {"direction": "outbound", "segments": [{"id": "out"}]},
            {"direction": "return", "segments": [{"id": "back"}]},
        ],
        "rank_components": {
            "not_covers_requested_trip": 0,
            "rejected_or_impossible_connection": 0,
            "max_connections_per_journey": 0,
        },
        "validation": {"status": "valid", "blocking_reasons": []},
    }

    assert candidate_is_direct(candidate)
    frontier = build_decision_frontier({"ranked_candidates": [candidate]})
    assert [option["id"] for option in frontier["options"]] == ["direct-round-trip"]


def test_frontier_consumes_validation_outcome_instead_of_recomputing_it() -> None:
    candidate = {
        "id": "invalid-despite-zero-score",
        "rank": 1,
        "covers_requested_trip": True,
        "journeys": [{"direction": "outbound", "segments": [{"id": "segment"}]}],
        "rank_components": {
            "not_covers_requested_trip": 0,
            "rejected_or_impossible_connection": 0,
            "max_connections_per_journey": 0,
        },
        "validation": {
            "status": "invalid",
            "blocking_reasons": ["airport_change_forbidden"],
        },
    }

    frontier = build_decision_frontier({"ranked_candidates": [candidate]})

    assert frontier["options"] == []
