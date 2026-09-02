from __future__ import annotations

from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import Any

from flights_cli.orchestrators.search_plan_builder import SearchPlanBuilder
from flights_cli.pipeline.result_builder import build_projection_input
from flights_cli.pipeline.candidate_directness import candidate_is_direct
from flights_cli.pipeline.frontier_selection import build_decision_frontier
from flights_cli.pipeline.search_decision import SearchDecisionBuilder
from flights_cli.store import Store
from helpers import future_departure_date, live_assembly_args


def _plan(depart: date) -> SimpleNamespace:
    return SimpleNamespace(
        route=SimpleNamespace(dates={"depart": depart.isoformat(), "return": None}),
        phases=SimpleNamespace(
            primary=(
                SimpleNamespace(
                    direction="outbound", query={"date": depart.isoformat()}
                ),
            )
        ),
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


def _evidence(depart: date) -> SimpleNamespace:
    route = {
        "origin": "SVX",
        "destination": "LED",
        "origin_airports": ["SVX"],
        "destination_airports": ["LED"],
        "dates": {"depart": depart.isoformat(), "return": None},
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
                        "departure_at": f"{depart.isoformat()}T08:00:00+05:00",
                        "arrival_at": f"{depart.isoformat()}T10:30:00+03:00",
                    }
                ],
            }
        ],
    }
    return SimpleNamespace(
        route_context=route,
        search_plan={
            "schema_version": "flight_search_plan.v6",
            "route": route,
            "gateway_policy": {"discovery": {}},
        },
        provider_policy="all",
        primary_offer_results=(primary_result,),
        probe_ledger={
            "planned_probes": [],
            "searched_probes": [],
            "skipped_probes": [],
            "failed_probes": [],
            "unsupported_probes": [],
            "not_executed_probes": [],
            "deduped_probes": [],
        },
        direct_inventory_searches=(),
    )


def test_search_decision_builder_is_a_pure_evidence_projection() -> None:
    depart = future_departure_date()
    decision = SearchDecisionBuilder.build(_plan(depart), _evidence(depart))

    assert decision.offer_graph["coverage"]["offer_count"] == 1
    assert decision.offer_candidates["coverage"]["candidate_count"] == 1
    assert [option["id"] for option in decision.decision_frontier["options"]] == [
        "candidate:primary_offer:fake:fake-direct"
    ]
    assert decision.research_status["needed"] is False
    assert decision.research_status["audit"] == []


def test_research_status_marks_evidence_incomplete_from_the_probe_ledger() -> None:
    depart = future_departure_date()
    evidence = _evidence(depart)
    evidence.primary_offer_results = ()
    evidence.probe_ledger["not_executed_probes"] = [
        {"probe_id": "budget", "reason": "provider_attempt_budget_exhausted"}
    ]

    decision = SearchDecisionBuilder.build(_plan(depart), evidence)

    # Незавершённость доказательств теперь читается только по журналу проб.
    # Раньше её вторым источником был аудит маршрутных гипотез — шлюзовых
    # плеч, которых больше не существует.
    assert decision.research_status["evidence_incomplete"] is True
    assert decision.research_status["needed"] is False
    assert decision.research_status["audit"] == []


def test_search_decision_uses_plan_limits_when_request_limits_conflict() -> None:
    depart = future_departure_date()
    request = live_assembly_args(
        origin="SVX",
        destination="LED",
        depart_date=depart.isoformat(),
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
    evidence = _evidence(depart)
    evidence.primary_offer_results[0]["top_offers"].append(
        {
            "id": "fake-direct-second",
            "price": 13_000,
            "currency": "RUB",
            "segments": [
                {
                    "origin": "SVX",
                    "destination": "LED",
                    "departure_at": f"{depart.isoformat()}T11:00:00+05:00",
                    "arrival_at": f"{depart.isoformat()}T13:30:00+03:00",
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
    depart = future_departure_date()
    plan = _plan(depart)
    evidence = _evidence(depart)
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
        == "flight_search_plan.v6"
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
