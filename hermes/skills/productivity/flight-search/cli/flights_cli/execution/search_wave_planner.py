from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from ..config import LATE_ARRIVAL_NEXT_DAY_THRESHOLD_HOUR
from .gateway_leg_probe_executor import (
    _coverage,
    _gateway_query_groups,
    _not_searched_gateway,
)


class GatewayWaveExecutor(Protocol):
    def run(
        self, queries: list[dict[str, Any]], plan: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class SearchWavePlannerOptions:
    max_waves: int
    probes_per_wave: int
    max_segment_searches: int
    top_k_partial_paths: int
    timeout_seconds: int


class SearchWavePlanner:
    """Bounded wave planner for gateway-leg probes.

    The pair executor remains responsible for executing one wave. This planner
    owns breadth, global budget, cross-day expansions from actual arrival times,
    and partial-answer diagnostics.
    """

    def __init__(
        self, *, options: SearchWavePlannerOptions, executor: GatewayWaveExecutor
    ) -> None:
        self.options = options
        self.executor = executor

    def run(
        self, queries: list[dict[str, Any]], plan: dict[str, Any]
    ) -> dict[str, Any]:
        max_waves = max(1, int(self.options.max_waves))
        probes_per_wave = max(1, int(self.options.probes_per_wave))
        remaining_budget = max(0, int(self.options.max_segment_searches))
        top_k = max(1, int(self.options.top_k_partial_paths))
        timeout_seconds = max(1, int(self.options.timeout_seconds))
        deadline = time.monotonic() + timeout_seconds

        pending = _unique_queries(
            [_with_wave_index(query, 0) for query in queries],
            seen_keys=set(),
        )
        seen_keys: set[tuple[Any, ...]] = set()
        gateways: list[dict[str, Any]] = []
        evaluations: list[dict[str, Any]] = []
        wave_summaries: list[dict[str, Any]] = []
        stop_reason = "complete"
        answerability = "complete"
        executed_probe_count = 0

        for wave_index in range(max_waves):
            if not pending:
                stop_reason = (
                    "no_gateway_leg_queries"
                    if wave_index == 0
                    else "no_new_viable_partials"
                )
                break
            if remaining_budget <= 0:
                stop_reason = "global_budget_exhausted"
                answerability = "needs_more_evidence"
                break
            if time.monotonic() >= deadline:
                stop_reason = "timeout"
                answerability = "needs_more_evidence"
                break

            selected, deferred = _select_wave_queries(
                pending,
                wave_index=wave_index,
                probe_limit=min(probes_per_wave, remaining_budget),
                seen_keys=seen_keys,
            )
            if not selected:
                stop_reason = "global_budget_exhausted"
                answerability = "needs_more_evidence"
                pending = deferred
                break

            for query in selected:
                seen_keys.add(_query_key(query))

            result = self.executor.run(selected, plan)
            wave_gateways = list(result.get("gateways") or [])
            gateways.extend(wave_gateways)
            for evaluation in result.get("coverage_evaluations") or []:
                if isinstance(evaluation, dict):
                    evaluations.append({**evaluation, "wave_index": wave_index})

            selected_probe_count = len(selected)
            remaining_budget -= selected_probe_count
            executed_probe_count += selected_probe_count
            if int(result.get("viable_gateways") or 0) > 0:
                generated: list[dict[str, Any]] = []
                pending = []
                stop_reason = "coverage_satisfied"
            else:
                generated = _expansion_queries_from_wave(
                    wave_gateways,
                    plan,
                    wave_index=wave_index + 1,
                    top_k=top_k,
                    seen_keys=seen_keys,
                )
                pending = _unique_queries(
                    [
                        *_with_wave_index_list(deferred, wave_index + 1),
                        *generated,
                    ],
                    seen_keys=seen_keys,
                )
            wave_summaries.append(
                {
                    "wave_index": wave_index,
                    "selected_probe_count": selected_probe_count,
                    "deferred_probe_count": len(deferred),
                    "generated_probe_count": len(generated),
                    "searched_gateways": int(result.get("searched_gateways") or 0),
                    "viable_gateways": int(result.get("viable_gateways") or 0),
                    "failed_gateways": int(result.get("failed_gateways") or 0),
                    "remaining_probe_budget": remaining_budget,
                }
            )
            if stop_reason == "coverage_satisfied":
                break

        else:
            if pending:
                stop_reason = "max_waves_exhausted"
                answerability = "needs_more_evidence"

        if pending and stop_reason in {
            "global_budget_exhausted",
            "max_waves_exhausted",
            "timeout",
        }:
            for gateway, group in _gateway_query_groups(pending).items():
                gateways.append(_not_searched_gateway(gateway, group, stop_reason))

        coverage = _coverage(gateways, evaluations=evaluations)
        coverage["answerability"] = answerability
        coverage["wave_diagnostics"] = {
            "schema_version": "flight_search_wave_diagnostics.v1",
            "max_waves": max_waves,
            "probes_per_wave": probes_per_wave,
            "top_k_partial_paths": top_k,
            "max_segment_searches": int(self.options.max_segment_searches),
            "executed_probe_count": executed_probe_count,
            "remaining_probe_budget": remaining_budget,
            "wave_count": len(wave_summaries),
            "stop_reason": stop_reason,
            "answerability": answerability,
            "waves": wave_summaries,
        }
        return coverage


def _with_wave_index(query: dict[str, Any], wave_index: int) -> dict[str, Any]:
    return {**query, "wave_index": wave_index}


def _with_wave_index_list(
    queries: list[dict[str, Any]], wave_index: int
) -> list[dict[str, Any]]:
    return [_with_wave_index(query, wave_index) for query in queries]


def _select_wave_queries(
    queries: list[dict[str, Any]],
    *,
    wave_index: int,
    probe_limit: int,
    seen_keys: set[tuple[Any, ...]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    selected_slots: set[tuple[str, str]] = set()
    remaining = max(0, probe_limit)
    for group in _selection_query_groups(queries):
        group_queries = [
            _with_wave_index(query, wave_index)
            for query in group
            if _query_key(query) not in seen_keys
        ]
        if not group_queries:
            continue
        group_slots = {_selection_slot(query) for query in group_queries}
        if selected_slots & group_slots:
            deferred.extend(group_queries)
            continue
        if len(group_queries) <= remaining:
            selected.extend(group_queries)
            selected_slots.update(group_slots)
            remaining -= len(group_queries)
            continue
        if remaining > 0 and not selected:
            selected.extend(group_queries[:remaining])
            selected_slots.update(_selection_slot(query) for query in selected)
            deferred.extend(group_queries[remaining:])
            remaining = 0
            continue
        deferred.extend(group_queries)
    return selected, deferred


def _selection_query_groups(queries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rows = [
        query
        for query in queries
        if isinstance(query, dict)
        and str(query.get("role") or "") == "gateway_leg_probe"
        and str(query.get("gateway") or "").strip()
    ]
    rows.sort(
        key=lambda query: (
            int(query.get("gateway_rank") or 0),
            str(query.get("gateway") or "").upper(),
            0 if str(query.get("leg") or "") == "origin_to_gateway" else 1,
            str(query.get("date") or ""),
            str(query.get("date_strategy") or ""),
        )
    )
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    ordered_keys: list[tuple[Any, ...]] = []
    for query in rows:
        gateway = str(query.get("gateway") or "").upper()
        leg = str(query.get("leg") or "")
        if str(query.get("source_type") or "") == "search_wave_expansion":
            group_key = (
                "search_wave_expansion",
                gateway,
                leg,
                str(query.get("origin") or "").upper(),
                str(query.get("destination") or "").upper(),
                str(query.get("provider") or ""),
                str(query.get("date") or ""),
                str(query.get("date_strategy") or ""),
            )
        else:
            group_key = ("gateway_pair", gateway)
        if group_key not in grouped:
            grouped[group_key] = []
            ordered_keys.append(group_key)
        grouped[group_key].append(query)
    return [grouped[key] for key in ordered_keys]


def _selection_slot(query: dict[str, Any]) -> tuple[str, str]:
    return (
        str(query.get("gateway") or "").upper(),
        str(query.get("leg") or ""),
    )


def _unique_queries(
    queries: list[dict[str, Any]], *, seen_keys: set[tuple[Any, ...]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    local_seen: set[tuple[Any, ...]] = set()
    for query in queries:
        key = _query_key(query)
        if key in seen_keys or key in local_seen:
            continue
        local_seen.add(key)
        result.append(query)
    return result


def _query_key(query: dict[str, Any]) -> tuple[Any, ...]:
    carriers = tuple(sorted(str(item).upper() for item in query.get("only_carriers") or []))
    return (
        str(query.get("role") or ""),
        str(query.get("provider") or ""),
        str(query.get("direction") or ""),
        str(query.get("leg") or ""),
        str(query.get("origin") or "").upper(),
        str(query.get("destination") or "").upper(),
        str(query.get("date") or ""),
        bool(query.get("direct_only", True)),
        carriers,
    )


def _expansion_queries_from_wave(
    gateways: list[dict[str, Any]],
    plan: dict[str, Any],
    *,
    wave_index: int,
    top_k: int,
    seen_keys: set[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    partials: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for gateway in gateways:
        if not isinstance(gateway, dict) or not gateway.get("searched"):
            continue
        for leg_key in ("origin_leg", "destination_leg"):
            leg = gateway.get(leg_key)
            if not isinstance(leg, dict):
                continue
            for offer_index, offer in enumerate(leg.get("offers") or []):
                if not isinstance(offer, dict):
                    continue
                queries = _expansion_queries_for_offer(
                    leg,
                    offer,
                    offer_index=offer_index,
                    plan=plan,
                    wave_index=wave_index,
                )
                for query in queries:
                    if _query_key(query) in seen_keys:
                        continue
                    partials.append((_expansion_rank_key(offer), query))
    partials.sort(key=lambda item: item[0])
    return _unique_queries([query for _key, query in partials[:top_k]], seen_keys=seen_keys)


def _expansion_queries_for_offer(
    leg: dict[str, Any],
    offer: dict[str, Any],
    *,
    offer_index: int,
    plan: dict[str, Any],
    wave_index: int,
) -> list[dict[str, Any]]:
    base = _expansion_query_for_offer(
        leg,
        offer,
        offer_index=offer_index,
        plan=plan,
        wave_index=wave_index,
    )
    if base is None:
        return []
    queries = [base]
    arrival_at = _datetime_from_arrival(_segments_from_offer(offer)[-1])
    if arrival_at is None:
        arrival_at = _datetime_from_arrival(offer)
    if (
        arrival_at is not None
        and arrival_at.hour >= LATE_ARRIVAL_NEXT_DAY_THRESHOLD_HOUR
    ):
        next_day = {
            **base,
            "date": (arrival_at.date() + timedelta(days=1)).isoformat(),
            "date_strategy": "arrival_date_plus_one_late_arrival",
        }
        if next_day["date"] != base["date"]:
            queries.append(next_day)
    return queries


def _expansion_query_for_offer(
    leg: dict[str, Any],
    offer: dict[str, Any],
    *,
    offer_index: int,
    plan: dict[str, Any],
    wave_index: int,
) -> dict[str, Any] | None:
    direction = str(leg.get("direction") or "outbound")
    requested_destination = _target_destination_for_direction(plan, direction)
    route_origin = str(plan.get("origin") or "").upper()
    segments = _segments_from_offer(offer)
    if not segments:
        return None
    final_segment = segments[-1]
    final_airport = _airport_value(
        final_segment,
        "destination",
        "arrival_airport",
        "destination_airport",
        "to",
        "to_airport",
    )
    if not final_airport:
        return None
    final_airport = final_airport.upper()
    if final_airport in {requested_destination, route_origin}:
        return None
    arrival_date = _date_from_arrival(final_segment) or _date_from_arrival(offer)
    if not arrival_date:
        return None
    provider = str(leg.get("provider") or "").lower()
    if not provider:
        return None
    return {
        "role": "gateway_leg_probe",
        "source_type": "search_wave_expansion",
        "probe_type": "segment_hub_leg",
        "direction": direction,
        "leg": "gateway_to_destination",
        "origin": final_airport,
        "destination": requested_destination,
        "date": arrival_date,
        "currency": str(plan.get("currency") or "").upper(),
        "direct_only": False,
        "gateway": final_airport,
        "gateway_rank": int(leg.get("gateway_rank") or 0) + 1000 + offer_index,
        "provider": provider,
        "execution_state": "not_executed",
        "wave_index": wave_index,
        "parent_probe_id": leg.get("probe_id"),
        "parent_offer_id": offer.get("id") or offer.get("offer_id"),
        "date_strategy": "arrival_date_from_partial_path",
        "allows_intermediate_hubs": True,
        "connection_layer": "search_wave_expansion",
        "only_carriers": list(leg.get("only_carriers") or []),
        "preferred_carriers": list(leg.get("preferred_carriers") or []),
    }


def _target_destination_for_direction(plan: dict[str, Any], direction: str) -> str:
    if direction == "return":
        return str(plan.get("origin") or "").upper()
    return str(plan.get("destination") or "").upper()


def _segments_from_offer(offer: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("segments", "flights", "legs"):
        value = offer.get(key)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return list(value)
    return [offer]


def _airport_value(segment: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = segment.get(key)
        if value:
            return str(value).strip().upper()
    return ""


def _date_from_arrival(item: dict[str, Any]) -> str | None:
    for key in ("arrival_at", "arrival_time", "arrival_datetime", "arrival"):
        value = item.get(key)
        if not value:
            continue
        text = str(value)
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
    return None


def _datetime_from_arrival(item: dict[str, Any]) -> datetime | None:
    for key in ("arrival_at", "arrival_time", "arrival_datetime", "arrival"):
        value = item.get(key)
        if not value:
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _expansion_rank_key(offer: dict[str, Any]) -> tuple[Any, ...]:
    price = offer.get("price")
    if isinstance(price, dict):
        price = price.get("amount")
    try:
        price_value = float(price)
    except (TypeError, ValueError):
        price_value = float("inf")
    arrival = ""
    for item in reversed(_segments_from_offer(offer)):
        arrival = str(
            item.get("arrival_at")
            or item.get("arrival_time")
            or item.get("arrival_datetime")
            or ""
        )
        if arrival:
            break
    return (price_value, arrival)
