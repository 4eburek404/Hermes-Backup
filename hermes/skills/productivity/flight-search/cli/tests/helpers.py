from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
TEST_CACHE_DIR = Path(tempfile.mkdtemp(prefix="flight-search-test-cache-"))
TEST_ENV = {
    "PYTHONPATH": str(PROJECT),
    "FLIGHTS_CATALOG_REFRESH": "never",
    "FLIGHTS_CACHE_DIR": str(TEST_CACHE_DIR),
    "PYTHONDONTWRITEBYTECODE": "1",
}


def decision_frontier_from_details(
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        ranked = detail.get("ranked") if isinstance(detail.get("ranked"), dict) else {}
        candidate = (
            detail.get("candidate") if isinstance(detail.get("candidate"), dict) else {}
        )
        validation = (
            ranked.get("validation_summary")
            if isinstance(ranked.get("validation_summary"), dict)
            else {}
        )
        option = {
            "id": ranked.get("id") or candidate.get("id"),
            "rank": ranked.get("rank") or detail.get("rank"),
            "source_type": candidate.get("source_type"),
            "provider": candidate.get("provider"),
            "source_providers": candidate.get("source_providers") or [],
            "gateway": candidate.get("gateway"),
            "covers_requested_trip": candidate.get("covers_requested_trip", True),
            "journey_scope": candidate.get("journey_scope") or "one_way",
            "price": ranked.get("price"),
            "currency": ranked.get("currency"),
            "price_basis": candidate.get("price_basis"),
            "ticketing_model": candidate.get("ticketing_model"),
            "detail_status": detail.get("detail_status") or "full",
            "journeys": candidate.get("journeys") or [],
            "warnings": candidate.get("warnings") or [],
            "elapsed_min": ranked.get("elapsed_min"),
            "connection_risk_score": (
                ranked.get("risk", {}).get("score")
                if isinstance(ranked.get("risk"), dict)
                else None
            ),
            "selection_reasons": [detail.get("category") or "fixture_frontier"],
            "connection_count": validation.get("max_connections_per_journey"),
        }
        options.append(
            {key: value for key, value in option.items() if value is not None}
        )
    return {
        "schema_version": "flight_decision_frontier.v1",
        "options": options,
        "controls": [],
        "coverage_summary": {
            "candidate_count": len(options),
            "acceptable_count": len(options),
            "selected_count": len(options),
            "rejected_count": 0,
            "control_count": 0,
        },
    }


def subparser_choices(
    parser: argparse.ArgumentParser,
) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def parser_leaf_defaults(parser: argparse.ArgumentParser) -> dict[str, dict[str, Any]]:
    leaves: dict[str, dict[str, Any]] = {}

    def walk(current: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        children = subparser_choices(current)
        if not children:
            leaves[" ".join(path)] = dict(getattr(current, "_defaults", {}))
            return
        for name, child in children.items():
            walk(child, (*path, name))

    walk(parser, ())
    return leaves


def live_assembly_args(**overrides: Any) -> Any:
    """Build typed live-assembly options through the canonical search request adapter."""

    from flights_cli.commands.search import live_assembly_options_from_search_request

    def as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    route_option_keys = {
        "hubs": "hubs",
        "hub": "hubs",
        "routing_strategy": "routing_strategy",
        "origin_airports": "origin_airports",
        "origin_airport": "origin_airports",
        "destination_airports": "destination_airports",
        "destination_airport": "destination_airports",
        "max_airports_per_city": "max_airports_per_city",
        "coverage_mode": "coverage_mode",
        "coverage_controls": "coverage_controls",
        "coverage_control": "coverage_controls",
        "coverage_control_limit": "coverage_control_limit",
        "min_same_airport_min": "min_same_airport_min",
        "min_cross_airport_min": "min_cross_airport_min",
        "stop_policy": "stop_policy",
        "date_window_end": "date_window_end",
        "max_connections": "max_connections",
        "tier2_max_connections": "tier2_max_connections",
        "use_gateway_discovery_for_fallback_hubs": (
            "use_gateway_discovery_for_fallback_hubs"
        ),
        "gateway_discovery_limit": "gateway_discovery_limit",
        "gateway_probe_batch_size": "gateway_probe_batch_size",
        "gateway_probe_max_batches": "gateway_probe_max_batches",
    }
    evidence_keys = {
        "segment_limit": "segment_limit",
        "timeout": "timeout",
        "outbound_second_leg_day_offsets": "outbound_second_leg_day_offsets",
        "outbound_second_leg_day_offset": "outbound_second_leg_day_offsets",
        "return_second_leg_day_offsets": "return_second_leg_day_offsets",
        "return_second_leg_day_offset": "return_second_leg_day_offsets",
        "search_wave_max_waves": "search_wave_max_waves",
        "search_wave_probe_limit": "search_wave_probe_limit",
        "search_wave_top_k": "search_wave_top_k",
        "aggregate_control_limit": "aggregate_control_limit",
        "aggregate_control_carriers": "aggregate_control_carriers",
        "aggregate_control_carrier": "aggregate_control_carriers",
        "max_segment_searches": "max_segment_searches",
        "fail_fast": "fail_fast",
        "live_cache_ttl_seconds": "live_cache_ttl_seconds",
        "no_live_cache": "no_live_cache",
        "fli_mcp_url": "fli_mcp_url",
    }
    output_keys = {
        "catalog_limit": "catalog_limit",
        "direct_catalog_limit": "direct_catalog_limit",
    }
    filter_keys = {
        "only_carriers": "only_carriers",
        "only_carrier": "only_carriers",
        "exclude_carriers": "exclude_carriers",
        "exclude_carrier": "exclude_carriers",
        "prefer_carriers": "prefer_carriers",
        "prefer_carrier": "prefer_carriers",
        "avoid_carriers": "avoid_carriers",
        "avoid_carrier": "avoid_carriers",
    }
    values = dict(overrides)
    request: dict[str, Any] = {
        "schema_version": "flight_search_request.v1",
        "origin": values.pop("origin", "SVX"),
        "destination": values.pop("destination", "CDG"),
        "depart_date": values.pop("depart_date", "2026-08-15"),
        "currency": values.pop("currency", "RUB"),
        "profile": values.pop("profile", "business"),
        "ticketing": values.pop("ticketing", "separate"),
        "provider_policy": values.pop("provider_policy", "auto"),
    }
    return_date = values.pop("return_date", None)
    if return_date is not None:
        request["return_date"] = return_date

    route_options: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    output: dict[str, Any] = {}
    filters: dict[str, Any] = {}
    for key, target in route_option_keys.items():
        if key in values:
            value = values.pop(key)
            if target in {
                "hubs",
                "origin_airports",
                "destination_airports",
                "coverage_controls",
            }:
                value = as_list(value)
            route_options[target] = value
    for key, target in evidence_keys.items():
        if key in values:
            value = values.pop(key)
            if target in {
                "outbound_second_leg_day_offsets",
                "return_second_leg_day_offsets",
                "aggregate_control_carriers",
            }:
                value = as_list(value)
            evidence[target] = value
    for key, target in output_keys.items():
        if key in values:
            output[target] = values.pop(key)
    for key, target in filter_keys.items():
        if key in values:
            filters[target] = as_list(values.pop(key))
    if route_options:
        request["route_options"] = route_options
    if evidence:
        request["evidence"] = evidence
    if output:
        request["output"] = output
    if filters:
        request["filters"] = filters

    if values:
        unknown = ", ".join(sorted(values))
        raise AssertionError(f"unsupported live_assembly_args overrides: {unknown}")
    return live_assembly_options_from_search_request(request)


class CliSubprocessMixin:
    def _parse_raw(
        self,
        payload: dict,
        leg: str,
        origin: str | None,
        destination: str | None,
        *,
        direction: str = "outbound",
        date: str = "2026-07-19",
    ) -> dict:
        """Build a normalized segment-result fixture without the retired parser CLI."""
        raw = payload.get("data", payload)
        request_variables = {}
        if isinstance(raw, dict) and isinstance(raw.get("request"), dict):
            request_variables = raw.get("request", {}).get("variables", {}) or {}
        if isinstance(raw, dict) and isinstance(raw.get("fetched"), dict):
            raw = raw.get("fetched", {}).get("data", raw)
        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            raw = raw["data"]

        if origin is None:
            origin = (
                str(
                    request_variables.get("destination")
                    if direction == "return"
                    else request_variables.get("origin") or ""
                )
                or None
            )
        if destination is None:
            destination = (
                str(
                    request_variables.get("origin")
                    if direction == "return"
                    else request_variables.get("destination") or ""
                )
                or None
            )

        items = raw.get("prices_one_way") or raw.get("prices_round_trip") or []
        selected_index = (
            1 if direction == "return" and raw.get("prices_round_trip") else 0
        )
        offers = []
        for index, item in enumerate(items):
            trip_segments = item.get("segments") or []
            if selected_index >= len(trip_segments):
                continue
            trip = trip_segments[selected_index]
            legs = trip.get("flight_legs") or []
            normalized_legs = []
            transfers = trip.get("transfers") or []
            for leg_index, flight_leg in enumerate(legs):
                segment = {
                    "origin": flight_leg.get("origin"),
                    "destination": flight_leg.get("destination"),
                    "departure_at": flight_leg.get("departure_at")
                    or trip.get("departure_at"),
                    "arrival_at": flight_leg.get("arrival_at")
                    or trip.get("arrival_at"),
                    "flight_number": flight_leg.get("flight_number"),
                    "carrier": flight_leg.get("operating_carrier")
                    or item.get("main_airline"),
                    "operating_carrier": flight_leg.get("operating_carrier"),
                    "aircraft_code": flight_leg.get("aircraft_code"),
                }
                if leg_index < len(transfers):
                    segment["transfer_after"] = transfers[leg_index]
                normalized_legs.append(segment)
            if not normalized_legs:
                continue
            offers.append(
                {
                    "id": f"fixture:{direction}:{leg}:{index}",
                    "direction": direction,
                    "leg": leg,
                    "query_origin": origin,
                    "query_destination": destination,
                    "query_date": date,
                    "origin": normalized_legs[0]["origin"],
                    "destination": normalized_legs[-1]["destination"],
                    "departure_airport": normalized_legs[0]["origin"],
                    "arrival_airport": normalized_legs[-1]["destination"],
                    "departure_at": normalized_legs[0]["departure_at"],
                    "arrival_at": normalized_legs[-1]["arrival_at"],
                    "price": item.get("value"),
                    "currency": "RUB",
                    "carrier": item.get("main_airline"),
                    "main_airline": item.get("main_airline"),
                    "changes": item.get("number_of_changes"),
                    "duration_min": item.get("duration"),
                    "segments": normalized_legs,
                    "transfers": transfers,
                    "selected_trip_segment_index": selected_index,
                }
            )

        return {
            "ok": True,
            "command": "normalized segment fixture",
            "data": {
                "segment_result": {
                    "direction": direction,
                    "leg": leg,
                    "query": {
                        "origin": origin,
                        "destination": destination,
                        "date": date,
                        "currency": "RUB",
                    },
                    "source_key": "normalized_fixture",
                    "raw_count": len(items),
                    "parse_errors": 0,
                    "offers": offers,
                }
            },
            "issues": [],
        }

    def _assemble(self, payload: dict, *extra_args: str) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "assemble",
                "--profile",
                "safe",
                "--input",
                "-",
                *extra_args,
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)
