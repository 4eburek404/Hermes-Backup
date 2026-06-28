from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .options import FilterOptions, LiveAssemblyOptions


@dataclass(frozen=True, slots=True)
class SegmentSpec:
    direction: str
    leg: str
    origin: str
    destination: str
    date: str
    route_family: str
    priority: int
    only_carriers: tuple[str, ...] = ()
    preferred_carriers: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "leg": self.leg,
            "origin": self.origin,
            "destination": self.destination,
            "date": self.date,
            "route_family": self.route_family,
            "priority": self.priority,
            "only_carriers": list(self.only_carriers),
            "preferred_carriers": list(self.preferred_carriers),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProbeSpec:
    probe_type: str
    provider_policy: str
    origin: str
    destination: str
    date: str
    direction: str
    leg: str
    currency: str
    filters: FilterOptions
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_type": self.probe_type,
            "provider_policy": self.provider_policy,
            "origin": self.origin,
            "destination": self.destination,
            "date": self.date,
            "direction": self.direction,
            "leg": self.leg,
            "currency": self.currency,
            "filters": {
                "only_carriers": list(self.filters.only_carriers),
                "exclude_carriers": list(self.filters.exclude_carriers),
                "prefer_carriers": list(self.filters.prefer_carriers),
                "avoid_carriers": list(self.filters.avoid_carriers),
            },
            "metadata": dict(self.metadata),
        }


_SEGMENT_CORE_KEYS = {
    "direction",
    "leg",
    "origin",
    "destination",
    "date",
    "route_family",
    "priority",
    "only_carriers",
    "preferred_carriers",
}


def _str_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),)


def _unique(*groups: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for group in groups:
        for value in group:
            normalized = str(value).strip().upper()
            if normalized and normalized not in values:
                values.append(normalized)
    return tuple(values)


def segment_specs_from_plan(plan: dict[str, Any]) -> list[SegmentSpec]:
    specs: list[SegmentSpec] = []
    for segment in plan.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        metadata = {
            key: value
            for key, value in segment.items()
            if key not in _SEGMENT_CORE_KEYS and key != "command"
        }
        specs.append(
            SegmentSpec(
                direction=str(segment.get("direction") or ""),
                leg=str(segment.get("leg") or ""),
                origin=str(segment.get("origin") or "").upper(),
                destination=str(segment.get("destination") or "").upper(),
                date=str(segment.get("date") or ""),
                route_family=str(segment.get("route_family") or ""),
                priority=int(segment.get("priority") or 0),
                only_carriers=_str_tuple(segment.get("only_carriers")),
                preferred_carriers=_str_tuple(segment.get("preferred_carriers")),
                metadata=metadata,
            )
        )
    return specs


def probe_specs_from_segments(
    segments: list[SegmentSpec], options: LiveAssemblyOptions
) -> list[ProbeSpec]:
    specs: list[ProbeSpec] = []
    for segment in segments:
        filters = FilterOptions(
            only_carriers=_unique(options.filters.only_carriers, segment.only_carriers),
            exclude_carriers=options.filters.exclude_carriers,
            prefer_carriers=_unique(
                options.filters.prefer_carriers, segment.preferred_carriers
            ),
            avoid_carriers=options.filters.avoid_carriers,
        )
        specs.append(
            ProbeSpec(
                probe_type="segment_direct",
                provider_policy=options.evidence.provider_policy,
                origin=segment.origin,
                destination=segment.destination,
                date=segment.date,
                direction=segment.direction,
                leg=segment.leg,
                currency=options.currency,
                filters=filters,
                metadata={
                    "route_family": segment.route_family,
                    "priority": segment.priority,
                    **dict(segment.metadata),
                },
            )
        )
    return specs
