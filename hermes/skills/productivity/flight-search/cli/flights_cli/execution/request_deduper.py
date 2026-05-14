from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.normalize import normalize_carrier_code

SegmentProbeKey = tuple[Any, ...]


@dataclass(frozen=True)
class DeduperClaim:
    key: SegmentProbeKey
    probe_id: str
    original_probe_id: str | None = None
    original: Any = None

    @property
    def is_duplicate(self) -> bool:
        return self.original is not None


class RequestDeduper:
    def __init__(self) -> None:
        self._records: dict[SegmentProbeKey, tuple[str, Any]] = {}
        self._counter = 0

    def claim_segment_probe(
        self,
        *,
        spec: dict[str, Any],
        provider: str,
        plan: dict[str, Any],
        only_carriers: list[str],
        limit: int,
        provider_policy: str,
        direct_only: bool = True,
        mcp_url: str | None = None,
    ) -> DeduperClaim:
        key = segment_probe_key(
            spec=spec,
            provider=provider,
            plan=plan,
            only_carriers=only_carriers,
            limit=limit,
            provider_policy=provider_policy,
            direct_only=direct_only,
            mcp_url=mcp_url,
        )
        if key in self._records:
            original_probe_id, original = self._records[key]
            return DeduperClaim(
                key=key,
                probe_id=self._next_probe_id(),
                original_probe_id=original_probe_id,
                original=original,
            )
        return DeduperClaim(key=key, probe_id=self._next_probe_id())

    def record(self, claim: DeduperClaim, outcome: Any) -> None:
        if not claim.is_duplicate:
            self._records[claim.key] = (claim.probe_id, outcome)

    def _next_probe_id(self) -> str:
        self._counter += 1
        return f"segment-probe-{self._counter:03d}"


def segment_probe_key(
    *,
    spec: dict[str, Any],
    provider: str,
    plan: dict[str, Any],
    only_carriers: list[str],
    limit: int,
    provider_policy: str,
    direct_only: bool,
    mcp_url: str | None = None,
) -> SegmentProbeKey:
    effective_carriers = tuple(sorted(normalize_carrier_code(code, "only-carrier") for code in (spec.get("only_carriers") or only_carriers)))
    return (
        "segment",
        str(provider or ""),
        str(provider_policy or ""),
        str(spec.get("direction") or ""),
        str(spec.get("leg") or ""),
        str(spec.get("origin") or "").upper(),
        str(spec.get("destination") or "").upper(),
        str(spec.get("date") or ""),
        str(plan.get("currency") or "").upper(),
        bool(direct_only),
        effective_carriers,
        int(limit),
        str(mcp_url or "") if provider == "fli" else "",
    )
