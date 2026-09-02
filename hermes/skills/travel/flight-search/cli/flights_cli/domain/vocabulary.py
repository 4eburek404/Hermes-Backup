"""Central vocabulary — single source of truth for all string constants used as
semantic identifiers across the flights CLI.

Every member is a StrEnum: ``Leg.DIRECT_OUTBOUND == "direct_outbound"``, serialises
to the same JSON string, works as a dict key and in sets.  This makes migration
incremental and safe: existing JSON output is byte-identical, and test fixtures
comparing against plain strings continue to pass without changes.

Existing Literal types in ``ports/providers.py`` (ProviderName, ProbeType,
ExecutionState, CacheStatus, EvidenceType) are *not* duplicated here — they
remain the canonical definitions for their layer.  When other layers need to
reference those values, import from ``ports/providers``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


# ---------------------------------------------------------------------------
# Leg identifiers (hub-segment legs + direct legs)
# ---------------------------------------------------------------------------


class Leg(StrEnum):
    DIRECT_OUTBOUND = "direct_outbound"
    DIRECT_RETURN = "direct_return"


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------


class Direction(StrEnum):
    OUTBOUND = "outbound"
    RETURN = "return"


def normalize_direction(value: Any) -> str:
    """Привести что угодно к направлению; всё неузнанное — outbound."""
    return (
        Direction.RETURN
        if str(value or Direction.OUTBOUND).strip().lower() == Direction.RETURN
        else Direction.OUTBOUND
    )


# ---------------------------------------------------------------------------
# Route family
# ---------------------------------------------------------------------------


class RouteFamily(StrEnum):
    """Осталось одно семейство: три остальных зеркалили `route_mode`.

    `route_mode` был ярлыком классификации рынка и удалён вместе с ней
    2 сентября. Имя `RouteFamily` при одном члене уже неточно — переезжает
    вместе со словарём в .v1.
    """

    DIRECT_INVENTORY = "direct_inventory"


# ---------------------------------------------------------------------------
# Probe execution state  (extends ExecutionState from ports/providers.py
# with ledger-specific states like "searched", "not_executed", "planned")
# ---------------------------------------------------------------------------


class ProbeStatus(StrEnum):
    SEARCHED = "searched"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_SUPPORTED = "not_supported"
    NOT_EXECUTED = "not_executed"
    DEDUPED = "deduped"
    PLANNED = "planned"
