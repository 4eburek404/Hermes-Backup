from __future__ import annotations

import json
from typing import Any

from .domain.vocabulary import RoutingStrategy
from .errors import CliError
from .reporting.user_answer import validate_user_answer


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
    raw_user_answer = report.get("user_answer")
    user_answer: dict[str, Any] = (
        raw_user_answer if isinstance(raw_user_answer, dict) else {}
    )
    validate_user_answer(user_answer)
    return str(user_answer["rendered_text"])


def render_human(command: str, data: Any) -> str:
    if isinstance(data, dict) and isinstance(data.get("agent_report"), dict):
        return render_agent_report_human(data["agent_report"])
    if command == "diagnose fli-search":
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
            price_text = (
                f"{price:,.0f} {offer.get('currency', data.get('currency', ''))}"
                if price is not None
                else "price n/a"
            )
            changes = (
                "direct"
                if offer.get("number_of_changes") == 0
                else f"{offer.get('number_of_changes')} stop(s)"
            )
            lines.append(
                f"  {i}. {price_text}  {changes}  {offer.get('duration') or '?'}min"
            )
            leg_bits = []
            for flight in offer.get("segments", []):
                dep = str(flight.get("departure_at") or "")
                arr = str(flight.get("arrival_at") or "")
                leg_bits.append(
                    f"{flight.get('flight_number')} {flight.get('origin')}{dep[11:16]}→{flight.get('destination')}{arr[11:16]}"
                )
            if leg_bits:
                lines.append("     " + " | ".join(leg_bits))
        return "\n".join(lines)
    if command == "diagnose fli-dates":
        lines = [
            f"FLI MCP date search: {data['origin']} → {data['destination']}",
            f"Range: {data.get('from_date')} — {data.get('to_date')}",
            f"Results: {len(data.get('dates') or [])}/{data.get('count', 0)}",
            f"Source: {data['source']}",
            "",
        ]
        for item in data.get("dates", []):
            lines.append(
                f"{item.get('date')}  {item.get('price')} {item.get('currency') or ''}"
            )
        if not data.get("dates"):
            lines.append("(no priced dates found)")
        return "\n".join(lines)
    if command == "diagnose kb-search":
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
            price_text = (
                f"{price:,.0f} {offer.get('currency', data.get('currency', ''))}"
                if price is not None
                else "price n/a"
            )
            changes = (
                "direct"
                if offer.get("number_of_changes") == 0
                else f"{offer.get('number_of_changes')} stop(s)"
            )
            lines.append(
                f"  {i}. {price_text}  {changes}  {offer.get('duration') or '?'}min"
            )
            leg_bits = []
            for flight in offer.get("segments", []):
                operating = flight.get("operating_carrier")
                marketing = flight.get("marketing_carrier")
                op_note = (
                    f" op:{operating}"
                    if operating and marketing and operating != marketing
                    else ""
                )
                dep = str(flight.get("departure_at") or "")
                arr = str(flight.get("arrival_at") or "")
                leg_bits.append(
                    f"{flight.get('flight_number')} {flight.get('origin')}{dep[11:16]}→{flight.get('destination')}{arr[11:16]}{op_note}"
                )
            if leg_bits:
                lines.append("     " + " | ".join(leg_bits))
        return "\n".join(lines)
    if command == "diagnose kb-roundtrip":
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
            price_text = (
                f"{price:,.0f} {offer.get('currency', data.get('currency', ''))}"
                if price is not None
                else "price n/a"
            )
            changes = (
                "direct/direct"
                if all(
                    (journey.get("number_of_changes") or 0) == 0
                    for journey in offer.get("journeys", [])
                )
                else f"{offer.get('number_of_changes')} total stop(s)"
            )
            baggage = (
                offer.get("baggage") if isinstance(offer.get("baggage"), dict) else {}
            )
            baggage_bits = []
            if baggage.get("count") is not None:
                baggage_bits.append(f"{baggage.get('count')}pc")
            if baggage.get("weight") is not None:
                baggage_bits.append(f"{baggage.get('weight')}kg")
            baggage_text = (
                "bag " + "/".join(baggage_bits) if baggage_bits else "bag n/a"
            )
            lines.append(f"  {i}. {price_text}  {changes}  {baggage_text}")
            for journey in offer.get("journeys", []):
                leg_bits = []
                for flight in journey.get("segments", []):
                    operating = flight.get("operating_carrier")
                    marketing = flight.get("marketing_carrier")
                    op_note = (
                        f" op:{operating}"
                        if operating and marketing and operating != marketing
                        else ""
                    )
                    dep = str(flight.get("departure_at") or "")
                    arr = str(flight.get("arrival_at") or "")
                    leg_bits.append(
                        f"{flight.get('flight_number')} {flight.get('origin')}{dep[11:16]}→{flight.get('destination')}{arr[11:16]}{op_note}"
                    )
                if leg_bits:
                    lines.append(
                        f"     {journey.get('direction')}: " + " | ".join(leg_bits)
                    )
        return "\n".join(lines)
    if command == "maint doctor":
        counts = data["cache_counts"]
        policy = data["catalog_auto_refresh_policy"]
        staleness = data["catalog_staleness"]
        skill = data.get("skill") or {}
        return "\n".join(
            [
                f"flights {data['version']} (skill {skill.get('name', 'unknown')} {skill.get('version', 'unknown')})",
                f"cache dir: {data['cache_dir']}",
                (
                    f"cache: countries={counts['countries']} cities={counts['cities']} airports={counts['airports']} "
                    f"airlines={counts['airlines']} alliances={counts['alliances']} planes={counts['planes']}"
                ),
                f"catalog refresh: {policy['mode']} max_age={policy['max_age']} stale={staleness['stale_count']}/{staleness['checked_count']}",
                f"default hubs: {', '.join(item['code'] for item in data.get('default_route_hubs', []))}",
                f"primary route command: {data['safety']['primary_route_command']}",
                f"targeted probe commands: {', '.join(data['safety']['targeted_probe_commands'])}",
            ]
        )
    if command == "maint check":
        source = data["source"]
        runtime = data["runtime"]
        git = source.get("git") or {}
        versions = data["versions"]
        parity = data["source_runtime_parity"]
        workflow = data.get("branch_workflow") or {}
        workflow_parity = (
            workflow.get("parity") if isinstance(workflow.get("parity"), dict) else {}
        )
        version_manifest = data["version_manifest"]
        references = data["references"]
        artifacts = data["generated_artifacts"]
        return "\n".join(
            [
                "flight-search maintenance",
                f"source: {'ok' if source['exists'] else 'missing'} {source['skill_path']}",
                f"runtime: {'ok' if runtime['exists'] else 'missing'} {runtime['skill_path']}",
                f"branch: {git.get('branch') or 'unknown'} dirty={git.get('dirty')}",
                f"HEAD: {git.get('head') or 'unknown'}",
                f"versions: skill={versions.get('skill_md') or 'unknown'} cli={versions.get('cli') or 'unknown'}",
                f"manifest: {'ok' if version_manifest['exists'] and not version_manifest['mismatches'] else 'mismatch'}",
                f"parity: {parity['status']} runtime_claims={'yes' if workflow_parity.get('runtime_claims_allowed') else 'no'}",
                f"doctor: {data['doctor']['status']}",
                f"references: source={references['source_count']} runtime={references['runtime_count']}",
                f"generated artifacts: source={artifacts['source_count']} runtime={artifacts['runtime_count']}",
            ]
        )
    if command == "maint catalog refresh":
        if data.get("dry_run"):
            lines = [
                f"catalog dry-run: {len(data.get('planned') or [])} files",
                f"cache: {data['cache_dir']}",
            ]
            for item in data.get("planned") or []:
                lines.append(f"  {item['name']}: {item['filename']}")
            return "\n".join(lines)
        lines = [
            f"catalog updated: {data.get('updated_count', 0)} files",
            f"cache: {data['cache_dir']}",
        ]
        for item in data.get("updated") or []:
            lines.append(
                f"  {item['name']}: count={item['count']} sha256={str(item['sha256'])[:12]}"
            )
        return "\n".join(lines)
    if command == "maint catalog manifest":
        entries = (data.get("manifest") or {}).get("entries") or {}
        staleness = data.get("catalog_staleness") or {}
        lines = [
            f"catalog manifest: {len(entries)} entries",
            f"cache: {data['cache_dir']}",
            f"stale: {staleness.get('stale_count', 0)}/{staleness.get('checked_count', 0)}",
        ]
        for name in sorted(entries):
            entry = entries[name]
            lines.append(
                f"  {name}: count={entry.get('count')} downloaded_at={entry.get('downloaded_at')}"
            )
        return "\n".join(lines)
    if command == "cities search":
        lines = [f"cities for {data['query']!r}: {len(data['cities'])}"]
        refresh = data.get("catalog_auto_refresh")
        if refresh:
            lines.append(
                f"catalog refresh: {'updated' if refresh.get('refreshed') else refresh.get('reason')}"
            )
        for city in data["cities"]:
            airports = ",".join(city.get("airports") or [])
            lines.append(
                f"{city['code']}\t{city.get('name') or ''}\t{city.get('country_code') or ''}\t{airports}"
            )
        return "\n".join(lines)
    if command == "airports explain":
        lines = []
        for airport in data["airports"]:
            lines.append(
                f"{airport['code']}: {airport.get('city_name') or airport.get('name') or 'unknown'}"
            )
            for note in airport.get("notes") or []:
                lines.append(f"  - {note}")
        return "\n".join(lines)
    if command == "diagnose plan":
        plan = data["plan"] if isinstance(data.get("plan"), dict) else data
        metrics = plan["metrics"]
        lines = [
            f"route: {','.join(plan['origin_airports'])} -> {','.join(plan['destination_airports'])}",
            f"strategy: {plan.get('routing_strategy', RoutingStrategy.HUB_LIST)}",
            f"hubs: {', '.join(plan['hubs'])} ({plan.get('hub_source', 'manual')})",
            f"segment requests: {metrics.get('segment_request_count', metrics.get('segment_search_count', 0))}",
            "first segments:",
        ]
        refresh = data.get("catalog_auto_refresh")
        if refresh:
            lines.insert(
                2,
                f"catalog refresh: {'updated' if refresh.get('refreshed') else refresh.get('reason')}",
            )
        for segment in plan["segments"][:8]:
            command = segment.get("command")
            if command:
                lines.append(f"  {command}")
            else:
                lines.append(
                    f"  {segment['origin']} -> {segment['destination']} {segment['date']}"
                )
        if len(plan["segments"]) > 8:
            lines.append(f"  ... {len(plan['segments']) - 8} more")
        if plan["warnings"]:
            lines.append("warnings:")
            lines.extend(f"  - {warning}" for warning in plan["warnings"])
        return "\n".join(lines)
    return json.dumps(data, ensure_ascii=False, indent=2)
