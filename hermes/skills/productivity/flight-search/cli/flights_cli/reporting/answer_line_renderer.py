from __future__ import annotations

from typing import Any

from .formatting import minutes_label, price_label, segment_line


def build_answer_lines(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    options = report.get("recommended_options") or []
    if options:
        best = options[0]
        risk = best.get("risk") or {}
        lines.append(
            "Best CLI-ranked option: "
            f"{best.get('price_text')} risk={risk.get('grade')}/{risk.get('score')} elapsed={best.get('elapsed') or 'n/a'}."
        )
        segment_lines = [segment_line(segment) for segment in best.get("segments") or []]
        if segment_lines:
            lines.append("Segments: " + " | ".join(segment_lines[:8]))
        connection_tradeoffs = []
        for connection in best.get("connections") or []:
            for tradeoff in connection.get("tradeoffs") or []:
                if isinstance(tradeoff, dict):
                    connection_tradeoffs.append((connection, tradeoff))
        if connection_tradeoffs:
            labels = []
            for connection, tradeoff in connection_tradeoffs[:3]:
                code = str(tradeoff.get("code") or "connection_wait").replace("_", " ")
                wait = minutes_label(tradeoff.get("actual_min")) or "n/a"
                airport = connection.get("arrival_airport") or connection.get("departure_airport") or "connection"
                labels.append(f"{code} {wait} at {airport}")
            lines.append("Connection trade-off: " + "; ".join(labels) + "; visible trade-off, not automatic demotion.")
        for category, label in (
            ("cheapest_acceptable", "Cheapest acceptable"),
            ("fastest_acceptable", "Fastest acceptable"),
        ):
            option = next((item for item in options if item.get("category") == category), None)
            if not option or option.get("id") == best.get("id"):
                continue
            option_risk = option.get("risk") or {}
            lines.append(
                f"{label}: rank={option.get('rank')} {option.get('price_text')} "
                f"risk={option_risk.get('grade')}/{option_risk.get('score')} "
                f"elapsed={option.get('elapsed') or 'n/a'}; show as trade-off, not hidden by compact output."
            )
    else:
        lines.append("No CLI-ranked assembled candidate was produced.")

    controls = report.get("aggregate_controls") or []
    usable_controls = []
    for control in controls:
        if control.get("status") != "ok" or int(control.get("offer_count") or 0) <= 0:
            continue
        reportable_offers = [
            offer for offer in control.get("top_offers") or []
            if isinstance(offer, dict) and offer.get("stop_tier") != "T3_THREE_PLUS" and offer.get("reportable_by_stop_policy") is not False
        ]
        if reportable_offers:
            usable = dict(control)
            usable["top_offers"] = reportable_offers
            usable_controls.append(usable)
    if usable_controls:
        control = usable_controls[0]
        offer = (control.get("top_offers") or [{}])[0]
        lines.append(
            "Aggregate control found: "
            f"{price_label(offer.get('price'), offer.get('currency'))} "
            f"{control.get('origin')}->{control.get('destination')} "
            f"{' + '.join(offer.get('flight_numbers') or []) or 'route offer'}."
        )
        lines.append(
            "Provider aggregate candidate: ticketing_protection=unknown; verify single-PNR/protection, baggage, fare rules, and final fare on the booking screen."
        )
        mismatches = offer.get("airport_mismatches") or []
        if mismatches:
            mismatch = mismatches[0]
            lines.append(
                "Aggregate airport-continuity warning: "
                f"{mismatch.get('arrival_airport')}->{mismatch.get('departure_airport')} inside provider offer; verify ground transfer before treating it as protected."
            )

    failures = report.get("provider_failures") or []
    if failures:
        first = failures[0]
        error = first.get("error") or {}
        provider = str(first.get("provider") or "provider").upper()
        route = f"{first.get('origin')}->{first.get('destination')}"
        lines.append(
            f"Provider failure: {provider} failed on {len(failures)} segment search(es); "
            f"first {route} {first.get('date')}: {error.get('message') or 'unknown error'}. "
            "Do not treat this as no-flight evidence or silently replace it with another provider."
        )

    priority_options = report.get("priority_options") or []
    if priority_options:
        moscow = next((item for item in priority_options if item.get("category") == "moscow_gateway_control"), None)
        if moscow:
            lines.append(
                "Moscow gateway control: "
                f"rank={moscow.get('rank')} {moscow.get('price_text')} "
                f"elapsed={moscow.get('elapsed') or 'n/a'}; compare against direct/best, do not hide solely because another option ranks higher."
            )
        priority = next(
            (item for item in priority_options if item.get("category") != "moscow_gateway_control"),
            None,
        )
        if priority:
            lines.append(
                "Priority control: "
                f"{priority.get('category')} rank={priority.get('rank')} "
                f"{priority.get('price_text')} elapsed={priority.get('elapsed') or 'n/a'}."
            )

    checks = report.get("through_fare_checks") or []
    if checks:
        first = checks[0]
        lines.append(
            f"Through-fare check required: verify {first.get('carrier')} {first.get('route')} on airline/GDS before pricing it as separate legs."
        )

    diagnostics = report.get("coverage_diagnostics") or {}
    if diagnostics:
        searched_count = len(diagnostics.get("searched_controls") or [])
        skipped_count = len(diagnostics.get("skipped_controls") or [])
        failed_count = len(diagnostics.get("failed_controls") or [])
        not_executed_count = len(diagnostics.get("not_executed_controls") or [])
        lines.append(
            "Coverage diagnostics: "
            f"mode={diagnostics.get('coverage_mode')}; searched={searched_count}, skipped={skipped_count}, "
            f"failed={failed_count}, not_executed={not_executed_count}; "
            "negative evidence is bounded live controls only."
        )
        if not_executed_count:
            lines.append("Coverage is incomplete: planned controls without terminal live evidence are not_executed, not no-flight evidence.")

    stop_diagnostics = report.get("stop_policy_diagnostics") if isinstance(report.get("stop_policy_diagnostics"), dict) else {}
    if stop_diagnostics:
        max_reported = report.get("stop_policy", {}).get("preferred_max_connections") if isinstance(report.get("stop_policy"), dict) else 1
        if stop_diagnostics.get("used_two_stop_fallback"):
            max_reported = 2
        lines.append(
            "Stop policy: "
            f"reported max connections per journey={max_reported}; "
            f"two_stop_fallback_used={bool(stop_diagnostics.get('used_two_stop_fallback'))}; "
            f"candidate_generation_mode={stop_diagnostics.get('candidate_generation_mode') or 'unknown'}; "
            f"generation_fallback_used={bool(stop_diagnostics.get('fallback_used'))}; "
            f"three_plus_suppressed={int(stop_diagnostics.get('three_plus_suppressed_count') or 0)}."
        )
        if int(stop_diagnostics.get("two_stop_suppressed_because_preferred_exists") or 0) > 0:
            lines.append("Two-stop candidates are hidden because direct/one-stop options exist.")

    lines.append("Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.")
    return lines
