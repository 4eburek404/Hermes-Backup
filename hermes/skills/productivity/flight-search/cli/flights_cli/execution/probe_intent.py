from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProbeIntent:
    """A provider/search probe the runtime actually intended to execute or skip.

    Diagnostics project these runtime intents instead of rebuilding probes after
    the fact from route-level wishes.
    """

    probe_type: str
    direction: str
    origin: str
    destination: str
    date: str
    provider: str | None = None
    carrier: str | None = None
    leg: str | None = None
    probe_id: str | None = None
    negative_evidence: str | None = None
    filters: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_probe(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "type": self.probe_type,
            "direction": self.direction,
            "origin": self.origin,
            "destination": self.destination,
            "date": self.date,
            "provider": self.provider,
            "carrier": self.carrier,
            "leg": self.leg,
            "probe_id": self.probe_id,
            "negative_evidence": self.negative_evidence,
            "filters": dict(self.filters or {}),
        }
        item.update(dict(self.metadata or {}))
        return {
            key: value for key, value in item.items() if value not in (None, {}, [])
        }


def probe_type_from_segment(spec: Mapping[str, Any]) -> str:
    leg = str(spec.get("leg") or "")
    return "segment_direct" if "direct" in leg else "segment_hub_leg"


def intent_from_segment(
    spec: Mapping[str, Any], *, provider: Any = None, probe_id: Any = None
) -> ProbeIntent:
    only_carriers = [
        str(code).upper() for code in (spec.get("only_carriers") or []) if code
    ]
    carrier = only_carriers[0] if len(only_carriers) == 1 else None
    return ProbeIntent(
        probe_type=probe_type_from_segment(spec),
        direction=str(spec.get("direction") or ""),
        leg=str(spec.get("leg") or "") or None,
        origin=str(spec.get("origin") or "").upper(),
        destination=str(spec.get("destination") or "").upper(),
        date=str(spec.get("date") or ""),
        provider=str(provider or spec.get("provider") or "") or None,
        carrier=carrier,
        probe_id=str(probe_id or spec.get("probe_id") or "") or None,
        negative_evidence=str(spec.get("negative_evidence") or "") or None,
        filters={
            "direct_only": bool(spec.get("direct_only", True)),
            "only_carriers": only_carriers,
        },
        metadata={
            key: value
            for key, value in dict(spec).items()
            if key
            not in {
                "direction",
                "leg",
                "origin",
                "destination",
                "date",
                "provider",
                "probe_id",
                "negative_evidence",
                "only_carriers",
            }
        },
    )


def intent_from_aggregate_query(
    query: Mapping[str, Any], *, provider: Any = None
) -> ProbeIntent:
    carriers = [
        str(code).upper() for code in (query.get("only_carriers") or []) if code
    ]
    carrier = (
        carriers[0]
        if len(carriers) == 1
        else (",".join(carriers) if carriers else None)
    )
    metadata = {
        key: value
        for key, value in dict(query).items()
        if key
        not in {
            "probe_type",
            "direction",
            "origin",
            "destination",
            "date",
            "provider",
            "carrier",
            "probe_id",
            "negative_evidence",
            "only_carriers",
            "direct_only",
        }
    }
    return ProbeIntent(
        probe_type=str(
            query.get("probe_type")
            or ("carrier_aggregate" if carriers else "full_route_aggregate")
        ),
        direction=str(query.get("direction") or ""),
        origin=str(query.get("origin") or "").upper(),
        destination=str(query.get("destination") or "").upper(),
        date=str(query.get("date") or ""),
        provider=str(provider or query.get("provider") or "") or None,
        carrier=carrier,
        probe_id=str(query.get("probe_id") or "") or None,
        filters={
            "direct_only": bool(query.get("direct_only", False)),
            "only_carriers": carriers,
        },
        metadata=metadata,
    )
