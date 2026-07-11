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
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )


def render_search_user_text(result: dict[str, Any]) -> str:
    raw_user_answer = result.get("answer")
    user_answer = raw_user_answer if isinstance(raw_user_answer, dict) else {}
    validate_user_answer(user_answer)
    return str(user_answer["rendered_text"])


def render_user_text(command: str, data: Any) -> str:
    if command == "search" and isinstance(data, dict):
        return render_search_user_text(data)
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
                f"agent path: {data['safety']['canonical_path']}",
                f"diagnostic probe commands: {', '.join(data['safety']['diagnostic_probe_commands'])}",
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
        route = plan["route_context"]
        primary = list(plan.get("primary_offer_queries") or [])
        conditional = list(plan.get("conditional_gateway_queries") or [])
        lines = [
            f"route: {','.join(route['origin_airports'])} -> {','.join(route['destination_airports'])}",
            f"strategy: {route.get('routing_strategy', RoutingStrategy.HUB_LIST)}",
            f"hubs: {', '.join(route['hubs'])}",
            f"primary probes: {len(primary)}",
            f"conditional probes: {len(conditional)}",
            "first probes:",
        ]
        refresh = data.get("catalog_auto_refresh")
        if refresh:
            lines.insert(
                2,
                f"catalog refresh: {'updated' if refresh.get('refreshed') else refresh.get('reason')}",
            )
        probes = [*primary, *conditional]
        for probe in probes[:8]:
            lines.append(
                f"  {probe['origin']} -> {probe['destination']} {probe['date']} [{probe.get('provider') or 'none'}]"
            )
        if len(probes) > 8:
            lines.append(f"  ... {len(probes) - 8} more")
        if plan.get("planning_reasons"):
            lines.append("planning reasons:")
            lines.extend(f"  - {reason}" for reason in plan["planning_reasons"])
        return "\n".join(lines)
    return json.dumps(data, ensure_ascii=False, indent=2)
