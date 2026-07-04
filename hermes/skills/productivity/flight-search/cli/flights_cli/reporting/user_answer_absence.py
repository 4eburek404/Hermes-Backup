from __future__ import annotations

import re
from typing import Any


def provider_display_name(provider: Any) -> str:
    normalized = str(provider or "").strip().lower()
    if normalized == "kupibilet":
        return "KupiBilet"
    if normalized == "fli":
        return "FLI"
    return str(provider or "").strip()


def ordered_unique_text(values: list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        ordered.append(text)
        seen.add(text)
    return ordered


def gateway_code(value: Any) -> str | None:
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,4}", code):
        return None
    return code


def gateway_codes(gateways: list[Any], *, searched: bool | None = None) -> list[str]:
    codes: list[Any] = []
    for item in gateways:
        if not isinstance(item, dict):
            continue
        if searched is not None and bool(item.get("searched")) is not searched:
            continue
        code = gateway_code(item.get("gateway"))
        if code:
            codes.append(code)
    return ordered_unique_text(codes)


def viable_gateway_codes(gateways: list[Any]) -> list[str]:
    return ordered_unique_text(
        [
            code
            for item in gateways
            if isinstance(item, dict) and item.get("searched") and item.get("viable")
            for code in [gateway_code(item.get("gateway"))]
            if code
        ]
    )


def failed_gateway_codes(gateways: list[Any]) -> list[str]:
    return ordered_unique_text(
        [
            code
            for item in gateways
            if isinstance(item, dict)
            and item.get("searched")
            and item.get("provider_failures")
            for code in [gateway_code(item.get("gateway"))]
            if code
        ]
    )


def comma_list(values: list[str]) -> str:
    return ", ".join(values)


def and_list(values: list[str]) -> str:
    if len(values) <= 1:
        return "".join(values)
    return f"{', '.join(values[:-1])} и {values[-1]}"


def searched_full_route_providers(primary_results: list[Any]) -> list[str]:
    providers: list[Any] = []
    for item in primary_results:
        if not isinstance(item, dict):
            continue
        state = str(item.get("execution_state") or item.get("status") or "").lower()
        status = str(item.get("status") or "").lower()
        if state not in {"searched", "ok", "success"} and status not in {
            "ok",
            "success",
        }:
            continue
        provider = provider_display_name(item.get("provider"))
        if provider:
            providers.append(provider)
    return ordered_unique_text(providers)


def gateway_coverage_summary(agent_report: dict[str, Any]) -> str | None:
    results = (
        agent_report.get("gateway_leg_results")
        if isinstance(agent_report.get("gateway_leg_results"), dict)
        else {}
    )
    gateways = (
        results.get("gateways") if isinstance(results.get("gateways"), list) else []
    )
    searched = gateway_codes(gateways, searched=True)
    viable = viable_gateway_codes(gateways)
    not_searched = gateway_codes(gateways, searched=False)
    failed = failed_gateway_codes(gateways)
    providers = searched_full_route_providers(
        agent_report.get("primary_offer_results")
        if isinstance(agent_report.get("primary_offer_results"), list)
        else []
    )
    if not searched and not not_searched:
        return None

    lines: list[str] = []
    if providers and searched:
        lines.append(
            f"Проверил {and_list(providers)} по всему маршруту и {len(searched)} gateway: {comma_list(searched)}."
        )
    elif searched:
        lines.append(f"Проверил {len(searched)} gateway: {comma_list(searched)}.")

    if viable:
        lines.append(f"Жизнеспособные варианты нашлись через {and_list(viable)}.")
    elif searched:
        lines.append("Жизнеспособных gateway-вариантов среди проверенных не нашлось.")

    if not_searched:
        lines.append(f"Не проверено из-за лимита: {comma_list(not_searched)}.")
    elif int(results.get("not_searched_budget") or 0) > 0:
        lines.append(
            f"Не проверено из-за лимита: {int(results.get('not_searched_budget') or 0)} gateway."
        )

    if failed and not viable:
        lines.append(f"Сбой поставщика затронул gateway: {comma_list(failed)}.")

    return " ".join(lines) if lines else None


def render_no_viable_answer(
    route: dict[str, Any],
    *,
    caveat_context: dict[str, Any],
    gateway_summary: str | None = None,
) -> str:
    origin = route.get("origin") or "???"
    destination = route.get("destination") or "???"
    lines = [f"Не нашёл пригодных вариантов {origin}→{destination}."]
    if gateway_summary:
        lines.append("")
        lines.append(gateway_summary)
    checks = []
    negative_wording = str(caveat_context.get("negative_wording") or "").strip()
    checks.append(
        negative_wording
        or "не нашёл в выполненных live/probe источниках; это не доказательство отсутствия вне границ источника"
    )
    checks.append("финальную цену, тариф, багаж и правила проверить на booking screen.")
    if caveat_context.get("not_executed"):
        checks.append("coverage неполное: не все live-проверки выполнены.")
    if caveat_context.get("provider_failures"):
        checks.append(
            "часть live-проверок упала — если это влияет на выбор, повторить поиск перед покупкой."
        )
    if checks:
        lines.append("")
        lines.append("**Проверить перед покупкой**")
        lines.extend(f"- {line}" for line in checks)
    return "\n".join(lines).strip()


def has_any_signal(text: str, signals: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(signal in lowered for signal in signals)
