from __future__ import annotations

import json
from typing import Any

from .errors import CliError

def output_envelope(command: str, data: Any) -> dict[str, Any]:
    return {"ok": True, "command": command, "data": data, "issues": []}


def error_envelope(exc: CliError) -> dict[str, Any]:
    error = {"type": exc.error_type, "message": exc.message}
    if exc.details is not None:
        error["details"] = exc.details
    return {"ok": False, "error": error}


def emit_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def render_agent_report_human(report: dict[str, Any]) -> str:
    human_answer = report.get("human_answer") if isinstance(report.get("human_answer"), dict) else {}
    if human_answer.get("text"):
        return str(human_answer["text"])

    lines = ["agent report:"]
    display = report.get("display") if isinstance(report.get("display"), dict) else {}
    if display.get("text"):
        lines.append(str(display["text"]))
    for line in report.get("answer_lines") or []:
        lines.append(f"  {line}")
    route = report.get("route") or {}
    status = report.get("status") or {}
    lines.extend(
        [
            "",
            f"route: {route.get('origin')} -> {route.get('destination')} dates={route.get('dates')}",
            f"ranked: {status.get('ranked_output_count')} output / {status.get('ranked_total_count')} total; candidates={status.get('candidate_count')}",
        ]
    )
    controls = report.get("aggregate_controls") or []
    if controls:
        lines.append("aggregate controls:")
        for control in controls[:6]:
            filters = control.get("filters") or {}
            carriers = ",".join(filters.get("only_carriers") or []) or "any"
            lines.append(
                f"  {control.get('direction')} {control.get('origin')}->{control.get('destination')} "
                f"carrier={carriers} status={control.get('status')} offers={control.get('offer_count')}"
            )
    return "\n".join(lines)


def render_human(command: str, data: Any) -> str:
    if isinstance(data, dict) and isinstance(data.get("agent_report"), dict):
        return render_agent_report_human(data["agent_report"])
    if command == "fli-search":
        lines = [
            f"FLI MCP live search: {data['origin']} → {data['destination']}",
            f"Date: {data['depart_date']}",
            f"Results: {data['offer_count']} unique offers from {data['raw_count']} raw results",
            f"Source: {data['source']}",
            f"Note: {data.get('note', '')}",
            "",
        ]
        if not data.get("offers"):
            lines.append("(no matching offers found)")
        for i, offer in enumerate(data.get("offers", []), 1):
            price = offer.get("price")
            price_text = f"{price:,.0f} {offer.get('currency', data.get('currency', ''))}" if price is not None else "price n/a"
            changes = "direct" if offer.get("number_of_changes") == 0 else f"{offer.get('number_of_changes')} stop(s)"
            lines.append(f"  {i}. {price_text}  {changes}  {offer.get('duration') or '?'}min")
            leg_bits = []
            for flight in offer.get("flights", []):
                dep = str(flight.get("departure_at") or "")
                arr = str(flight.get("arrival_at") or "")
                leg_bits.append(
                    f"{flight.get('flight_number')} {flight.get('origin')}{dep[11:16]}→{flight.get('destination')}{arr[11:16]}"
                )
            if leg_bits:
                lines.append("     " + " | ".join(leg_bits))
        return "\n".join(lines)
    if command == "fli-dates":
        lines = [
            f"FLI MCP date search: {data['origin']} → {data['destination']}",
            f"Range: {data.get('from_date')} — {data.get('to_date')}",
            f"Results: {len(data.get('dates') or [])}/{data.get('count', 0)}",
            f"Source: {data['source']}",
            "",
        ]
        for item in data.get("dates", []):
            lines.append(f"{item.get('date')}  {item.get('price')} {item.get('currency') or ''}")
        if not data.get("dates"):
            lines.append("(no priced dates found)")
        return "\n".join(lines)
    if command == "kb-search":
        lines = [
            f"Kupibilet live search: {data['origin']} → {data['destination']}",
            f"Date: {data['depart_date']}",
            f"Results: {data['offer_count']} unique offers from {data['raw_variant_count']} raw variants",
            f"Source: {data['source']}",
            f"Note: {data.get('note', '')}",
            "",
        ]
        if not data.get("offers"):
            lines.append("(no matching offers found)")
        for i, offer in enumerate(data.get("offers", []), 1):
            price = offer.get("price")
            price_text = f"{price:,.0f} {offer.get('currency', data.get('currency', ''))}" if price is not None else "price n/a"
            changes = "direct" if offer.get("number_of_changes") == 0 else f"{offer.get('number_of_changes')} stop(s)"
            lines.append(f"  {i}. {price_text}  {changes}  {offer.get('duration') or '?'}min")
            leg_bits = []
            for flight in offer.get("flights", []):
                operating = flight.get("operating_carrier")
                marketing = flight.get("marketing_carrier")
                op_note = f" op:{operating}" if operating and marketing and operating != marketing else ""
                dep = str(flight.get("departure_at") or "")
                arr = str(flight.get("arrival_at") or "")
                leg_bits.append(
                    f"{flight.get('flight_number')} {flight.get('origin')}{dep[11:16]}→{flight.get('destination')}{arr[11:16]}{op_note}"
                )
            if leg_bits:
                lines.append("     " + " | ".join(leg_bits))
        return "\n".join(lines)
    if command == "kb-roundtrip":
        lines = [
            f"Kupibilet live round-trip search: {data['origin']} ↔ {data['destination']}",
            f"Dates: {data['depart_date']} → {data['return_date']}",
            f"Results: {data['offer_count']} fare packages from {data['raw_variant_count']} raw variants",
            f"Source: {data['source']}",
            f"Note: {data.get('note', '')}",
            "",
        ]
        if not data.get("offers"):
            lines.append("(no matching round-trip offers found)")
        for i, offer in enumerate(data.get("offers", []), 1):
            price = offer.get("price")
            price_text = f"{price:,.0f} {offer.get('currency', data.get('currency', ''))}" if price is not None else "price n/a"
            changes = "direct/direct" if all((journey.get("number_of_changes") or 0) == 0 for journey in offer.get("journeys", [])) else f"{offer.get('number_of_changes')} total stop(s)"
            baggage = offer.get("baggage") if isinstance(offer.get("baggage"), dict) else {}
            baggage_bits = []
            if baggage.get("count") is not None:
                baggage_bits.append(f"{baggage.get('count')}pc")
            if baggage.get("weight") is not None:
                baggage_bits.append(f"{baggage.get('weight')}kg")
            baggage_text = "bag " + "/".join(baggage_bits) if baggage_bits else "bag n/a"
            lines.append(f"  {i}. {price_text}  {changes}  {baggage_text}")
            for journey in offer.get("journeys", []):
                leg_bits = []
                for flight in journey.get("flights", []):
                    operating = flight.get("operating_carrier")
                    marketing = flight.get("marketing_carrier")
                    op_note = f" op:{operating}" if operating and marketing and operating != marketing else ""
                    dep = str(flight.get("departure_at") or "")
                    arr = str(flight.get("arrival_at") or "")
                    leg_bits.append(
                        f"{flight.get('flight_number')} {flight.get('origin')}{dep[11:16]}→{flight.get('destination')}{arr[11:16]}{op_note}"
                    )
                if leg_bits:
                    lines.append(f"     {journey.get('direction')}: " + " | ".join(leg_bits))
        return "\n".join(lines)
    if command == "doctor":
        counts = data["cache_counts"]
        tp_auth = data["auth"]["travelpayouts_token"]
        policy = data["catalog_auto_refresh_policy"]
        staleness = data["catalog_staleness"]
        skill = data.get("skill") or {}
        return "\n".join(
            [
                f"flights {data['version']} (skill {skill.get('name', 'unknown')} {skill.get('version', 'unknown')})",
                f"plugin: {'ok' if data['hermes_plugin_exists'] else 'missing'} {data['hermes_plugin_path']}",
                (
                    f"cache: countries={counts['countries']} cities={counts['cities']} airports={counts['airports']} "
                    f"airlines={counts['airlines']} alliances={counts['alliances']} planes={counts['planes']}"
                ),
                f"catalog refresh: {policy['mode']} max_age={policy['max_age']} stale={staleness['stale_count']}/{staleness['checked_count']}",
                f"default hubs: {', '.join(item['code'] for item in data.get('default_route_hubs', []))}",
                f"Travelpayouts auth: {'present' if tp_auth['available'] else 'missing'}",
                "Travelpayouts usage: static catalogs only",
                f"main live commands: {', '.join(data['safety']['live_provider_commands'])}",
            ]
        )
    if command == "catalog update":
        if data.get("dry_run"):
            lines = [f"catalog dry-run: {len(data.get('planned') or [])} files", f"cache: {data['cache_dir']}"]
            for item in data.get("planned") or []:
                lines.append(f"  {item['name']}: {item['filename']}")
            return "\n".join(lines)
        lines = [f"catalog updated: {data.get('updated_count', 0)} files", f"cache: {data['cache_dir']}"]
        for item in data.get("updated") or []:
            lines.append(f"  {item['name']}: count={item['count']} sha256={str(item['sha256'])[:12]}")
        return "\n".join(lines)
    if command == "catalog manifest":
        entries = (data.get("manifest") or {}).get("entries") or {}
        staleness = data.get("catalog_staleness") or {}
        lines = [
            f"catalog manifest: {len(entries)} entries",
            f"cache: {data['cache_dir']}",
            f"stale: {staleness.get('stale_count', 0)}/{staleness.get('checked_count', 0)}",
        ]
        for name in sorted(entries):
            entry = entries[name]
            lines.append(f"  {name}: count={entry.get('count')} downloaded_at={entry.get('downloaded_at')}")
        return "\n".join(lines)
    if command == "cities search":
        lines = [f"cities for {data['query']!r}: {len(data['cities'])}"]
        refresh = data.get("catalog_auto_refresh")
        if refresh:
            lines.append(f"catalog refresh: {'updated' if refresh.get('refreshed') else refresh.get('reason')}")
        for city in data["cities"]:
            airports = ",".join(city.get("airports") or [])
            lines.append(f"{city['code']}\t{city.get('name') or ''}\t{city.get('country_code') or ''}\t{airports}")
        return "\n".join(lines)
    if command == "airports explain":
        lines = []
        for airport in data["airports"]:
            lines.append(f"{airport['code']}: {airport.get('city_name') or airport.get('name') or 'unknown'}")
            for note in airport.get("notes") or []:
                lines.append(f"  - {note}")
        return "\n".join(lines)
    if command == "route plan":
        metrics = data["metrics"]
        lines = [
            f"route: {','.join(data['origin_airports'])} -> {','.join(data['destination_airports'])}",
            f"strategy: {data.get('routing_strategy', 'hub-list')}",
            f"hubs: {', '.join(data['hubs'])} ({data.get('hub_source', 'manual')})",
            f"segment requests: {metrics['segment_request_count']}",
            "first commands:",
        ]
        refresh = data.get("catalog_auto_refresh")
        if refresh:
            lines.insert(2, f"catalog refresh: {'updated' if refresh.get('refreshed') else refresh.get('reason')}")
        for segment in data["segments"][:8]:
            lines.append(f"  {segment['command']}")
        if len(data["segments"]) > 8:
            lines.append(f"  ... {len(data['segments']) - 8} more")
        if data["warnings"]:
            lines.append("warnings:")
            lines.extend(f"  - {warning}" for warning in data["warnings"])
        return "\n".join(lines)
    if command == "route validate":
        lines = [
            f"ok: {data['ok']}",
            f"risk: {data['risk']['score']} ({data['risk']['grade']}) profile={data['risk']['profile']}",
            f"segments: {data['summary']['segment_count']}, connections: {data['summary']['connection_count']}, violations: {data['summary']['violation_count']}",
        ]
        for violation in data["violations"]:
            lines.append(f"violation: {violation['arrival_airport']} -> {violation['departure_airport']}: {violation['status']}")
            for note in violation.get("notes") or []:
                lines.append(f"  - {note}")
        return "\n".join(lines)
    if command == "route rank":
        lines = [f"profile: {data['profile']} ({data['rank_order']})"]
        for item in data["ranked"]:
            lines.append(
                f"{item['rank']}. {item['id']} risk={item['risk']['score']}:{item['risk']['grade']} price={item['price']} elapsed={item['elapsed_min']}"
            )
            for reason in item["risk"]["top_reasons"][:3]:
                lines.append(f"  - +{reason['points']} {reason['code']}: {reason['message']}")
        return "\n".join(lines)
    if command == "route assemble":
        assembly = data["assembly"]
        lines = [
            f"profile: {data['profile']} ({data['rank_order']})",
            f"assembled candidates: {assembly['candidate_count']} from outbound_pairs={assembly['outbound_pair_count']} return_pairs={assembly['return_pair_count']}",
            f"rejected pairs: {assembly.get('rejected_pair_count', 0)}",
        ]
        for item in data["ranked"]:
            lines.append(
                f"{item['rank']}. {item['id']} risk={item['risk']['score']}:{item['risk']['grade']} price={item['price']} elapsed={item['elapsed_min']}"
            )
        return "\n".join(lines)
    if command in {"route kb-assemble", "route live-assemble"}:
        assembly = data["assembly"]
        live = data.get("live_search", {})
        plan = live.get("plan", {})
        metrics = plan.get("metrics", {})
        label = "Kupibilet direct-segment assembly" if command == "route kb-assemble" else "Provider-policy live assembly"
        lines = [
            f"{label}: {plan.get('origin')} → {plan.get('destination')}",
            f"strategy: {plan.get('routing_strategy', 'hub-list')}",
            f"provider policy: {live.get('provider_policy', 'kupibilet')}",
            f"hubs: {', '.join(plan.get('hubs') or [])}",
            f"segment searches: {len(live.get('segment_searches') or [])}/{metrics.get('segment_search_count', 0)} failures={live.get('failure_count', 0)}",
            f"assembled candidates: {assembly['candidate_count']} from outbound_pairs={assembly['outbound_pair_count']} return_pairs={assembly['return_pair_count']}",
            f"rejected pairs: {assembly.get('rejected_pair_count', 0)}",
            f"note: {live.get('note', '')}",
        ]
        viability = live.get("hub_viability") or []
        if viability:
            viable_hubs = [item["hub"] for item in viability if item.get("viable")]
            missing = [f"{item['hub']} missing={','.join(item.get('missing_legs') or [])}" for item in viability if not item.get("viable")]
            lines.append(f"viable hubs: {', '.join(viable_hubs) if viable_hubs else 'none'}")
            if missing:
                lines.append(f"incomplete hubs: {'; '.join(missing[:6])}")
        direct_intel = live.get("direct_route_intelligence") or {}
        if direct_intel.get("enabled"):
            if direct_intel.get("available"):
                cache = direct_intel.get("cache") or {}
                lines.append(
                    f"direct route index: available cache={'hit' if cache.get('hit') else 'refreshed'}"
                )
            else:
                lines.append(f"direct route index: unavailable ({direct_intel.get('reason')})")
        lines.append("")
        if not data.get("ranked"):
            lines.append("(no assembled candidates)")
        for item in data.get("ranked", [])[:10]:
            lines.append(
                f"{item['rank']}. {item['id']} risk={item['risk']['score']}:{item['risk']['grade']} price={item['price']} elapsed={item['elapsed_min']}"
            )
        return "\n".join(lines)
    if command == "metrics workflow":
        metrics = data["metrics"]
        return "\n".join(
            [
                f"without cli: {json.dumps(metrics['without_cli'], ensure_ascii=False, sort_keys=True)}",
                f"with cli: {json.dumps(metrics['with_cli'], ensure_ascii=False, sort_keys=True)}",
                f"segment requests: {metrics['segment_request_count']}",
            ]
        )
    return json.dumps(data, ensure_ascii=False, indent=2)
