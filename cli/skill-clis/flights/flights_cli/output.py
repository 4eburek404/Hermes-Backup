from __future__ import annotations

import json
from typing import Any

from .errors import CliError

def output_envelope(command: str, data: Any) -> dict[str, Any]:
    return {"ok": True, "command": command, "data": data}


def error_envelope(exc: CliError) -> dict[str, Any]:
    error = {"type": exc.error_type, "message": exc.message}
    if exc.details is not None:
        error["details"] = exc.details
    return {"ok": False, "error": error}


def emit_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def render_human(command: str, data: Any) -> str:
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
    if command == "u6-prices":
        if data.get("empty"):
            return (
                f"U6 price calendar: {data['origin']} → {data['destination']}\n"
                f"Status: no data ({data.get('empty_reason', 'unknown')})\n"
                f"Note: {data.get('note', '')}\n"
                "\n"
                "Cross-check:\n  "
                + "\n  ".join(data.get("cross_check_commands", []))
            )
        stats = data.get("stats", {})
        lines = [
            f"U6 price calendar: {data['origin']} → {data['destination']}",
            f"Range: {data.get('from_date', '')} — {data.get('final_date', '?')}  ({data['priced_dates']} priced / {data['unpriced_dates']} no-flight days)",
            f"Prices: min={stats.get('min') or '-'}  max={stats.get('max') or '-'}  avg={stats.get('avg') or '-'} RUB",
            "",
            "Date         Price",
            "-----------  ------",
        ]
        for entry in data.get("results", []):
            lines.append(f"{entry['date']}  {entry['price']:>6} {entry.get('currency', 'RUB')}")
        if not data.get("results"):
            lines.append("(no results matching filters)")
        if len(data.get("results", [])) < data.get("priced_dates", 0):
            lines.append(f"({data['priced_dates'] - len(data.get('results', []))} more matching filter, use --limit to see more)")
        lines.append("")
        lines.append("Cross-check:")
        for cmd in data.get("cross_check_commands", []):
            lines.append(f"  {cmd}")
        return "\n".join(lines)
    if command == "doctor":
        counts = data["cache_counts"]
        token = data["auth"]["travelpayouts_token"]
        return "\n".join(
            [
                f"flights {data['version']}",
                f"plugin: {'ok' if data['hermes_plugin_exists'] else 'missing'} {data['hermes_plugin_path']}",
                f"cache: cities={counts['cities']} airports={counts['airports']} airlines={counts['airlines']} planes={counts['planes']}",
                f"token: {'present' if token['available'] else 'missing'}",
                "live API: disabled unless --live",
            ]
        )
    if command == "cities search":
        lines = [f"cities for {data['query']!r}: {len(data['cities'])}"]
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
            f"hubs: {', '.join(data['hubs'])}",
            f"segment requests: {metrics['segment_request_count']}",
            "first commands:",
        ]
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
    if command == "route kb-assemble":
        assembly = data["assembly"]
        live = data.get("live_search", {})
        plan = live.get("plan", {})
        metrics = plan.get("metrics", {})
        lines = [
            f"Kupibilet direct-segment assembly: {plan.get('origin')} → {plan.get('destination')}",
            f"hubs: {', '.join(plan.get('hubs') or [])}",
            f"segment searches: {len(live.get('segment_searches') or [])}/{metrics.get('segment_search_count', 0)} failures={live.get('failure_count', 0)}",
            f"assembled candidates: {assembly['candidate_count']} from outbound_pairs={assembly['outbound_pair_count']} return_pairs={assembly['return_pair_count']}",
            f"rejected pairs: {assembly.get('rejected_pair_count', 0)}",
            f"note: {live.get('note', '')}",
            "",
        ]
        if not data.get("ranked"):
            lines.append("(no assembled candidates)")
        for item in data.get("ranked", [])[:10]:
            lines.append(
                f"{item['rank']}. {item['id']} risk={item['risk']['score']}:{item['risk']['grade']} price={item['price']} elapsed={item['elapsed_min']}"
            )
        return "\n".join(lines)
    if command == "results parse":
        result = data["segment_result"]
        query = result["query"]
        return "\n".join(
            [
                f"{result['direction']} {result['leg']}: {query.get('origin')}->{query.get('destination')} {query.get('date')}",
                f"offers: {len(result['offers'])}/{result['raw_count']} parse_errors={result['parse_errors']}",
            ]
        )
    if command == "request search":
        req = data["request"]
        lines = [
            f"{req['method']} {req['endpoint']}",
            f"query: {req['query_name']}",
            f"variables: {json.dumps(req['variables'], ensure_ascii=False, sort_keys=True)}",
            f"dry_run: {data['dry_run']}",
            f"manual link: {data['manual_link']}",
        ]
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
