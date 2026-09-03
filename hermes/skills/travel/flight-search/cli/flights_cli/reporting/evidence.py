"""Свидетельство прогона в том объёме, в каком оно доезжает до ответа.

Двенадцать полей покрытия — счётчики по семи корзинам, две метки полноты,
три постоянных предупреждения и два списка причин — сведены к одному
`complete`. Всё, что они добавляли сверх него, было диагностикой прогона, а
не ответом путешественнику, и читалось только тестами.

Осталось два факта, которых в двенадцати полях как раз не было: **кого
спросили** и **кто упал**. Первый важен потому, что провайдер, не умеющий
такой запрос, до пробы не доходит: без списка спрошенных ответ выглядел
полным, опросив одного провайдера из двух.
"""

from __future__ import annotations

from typing import Any

PROBE_BUCKETS = (
    "planned_probes",
    "searched_probes",
    "skipped_probes",
    "failed_probes",
    "unsupported_probes",
    "not_executed_probes",
    "deduped_probes",
)
TERMINAL_PROBE_BUCKETS = PROBE_BUCKETS[1:]


def _validated_ledger(ledger: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(ledger, dict):
        raise ValueError("live search output requires a production probe_ledger")
    missing = [bucket for bucket in PROBE_BUCKETS if bucket not in ledger]
    invalid = [
        bucket
        for bucket in PROBE_BUCKETS
        if bucket in ledger and not isinstance(ledger[bucket], list)
    ]
    if missing or invalid:
        details = []
        if missing:
            details.append(f"missing buckets: {', '.join(missing)}")
        if invalid:
            details.append(f"non-list buckets: {', '.join(invalid)}")
        raise ValueError(
            f"invalid production probe ledger shape ({'; '.join(details)})"
        )
    return {
        bucket: [item for item in ledger[bucket] if isinstance(item, dict)]
        for bucket in PROBE_BUCKETS
    }


def _provider_failure(probe: dict[str, Any]) -> dict[str, Any]:
    error = probe.get("error") if isinstance(probe.get("error"), dict) else {}
    retryable = error.get("retryable")
    return {
        "provider": str(probe.get("provider") or "unknown"),
        "classification": str(
            error.get("classification") or error.get("type") or "upstream_error"
        ),
        "retryable": retryable if isinstance(retryable, bool) else None,
    }


def all_planned_probes_are_terminal(probe_ledger: Any) -> bool:
    """Каждая запланированная проба дошла до какого-нибудь конца.

    Это инвариант журнала, а не оценка ответа: проба могла упасть или быть
    пропущена — важно, что она не потерялась.
    """

    buckets = _validated_ledger(probe_ledger)
    return len(buckets["planned_probes"]) == sum(
        len(buckets[bucket]) for bucket in TERMINAL_PROBE_BUCKETS
    )


def build_evidence(
    probe_ledger: Any, *, date_window: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Свести журнал проб к трём фактам ответа (и покрытию окна, если оно было)."""

    buckets = _validated_ledger(probe_ledger)
    planned_count = len(buckets["planned_probes"])
    terminal_count = sum(len(buckets[bucket]) for bucket in TERMINAL_PROBE_BUCKETS)
    blocked = bool(buckets["not_executed_probes"] or buckets["failed_probes"])
    evidence: dict[str, Any] = {
        "providers_searched": sorted(
            {
                str(probe.get("provider"))
                for probe in buckets["searched_probes"]
                if probe.get("provider")
            }
        ),
        "provider_failures": [
            _provider_failure(probe) for probe in buckets["failed_probes"]
        ],
        "complete": planned_count == terminal_count and not blocked,
    }
    if date_window is not None:
        evidence["date_window"] = date_window
    return evidence


__all__ = [
    "PROBE_BUCKETS",
    "TERMINAL_PROBE_BUCKETS",
    "all_planned_probes_are_terminal",
    "build_evidence",
]
