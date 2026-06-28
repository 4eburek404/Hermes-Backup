"""Central vocabulary — single source of truth for all string constants used as
semantic identifiers across the flights CLI.

Every member is a StrEnum: ``Leg.ORIGIN_TO_HUB == "origin_to_hub"``, serialises
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


# ---------------------------------------------------------------------------
# Leg identifiers (hub-segment legs + direct legs)
# ---------------------------------------------------------------------------


class Leg(StrEnum):
    ORIGIN_TO_HUB = "origin_to_hub"
    HUB_TO_DESTINATION = "hub_to_destination"
    DESTINATION_TO_HUB = "destination_to_hub"
    HUB_TO_ORIGIN = "hub_to_origin"
    DIRECT_OUTBOUND = "direct_outbound"
    DIRECT_RETURN = "direct_return"


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------


class Direction(StrEnum):
    OUTBOUND = "outbound"
    RETURN = "return"


# ---------------------------------------------------------------------------
# Stop-policy buckets
# ---------------------------------------------------------------------------


class StopBucket(StrEnum):
    PREFERRED = "preferred"
    TIER2 = "tier2"
    SUPPRESSED = "suppressed"


# ---------------------------------------------------------------------------
# Market / Intent / Evidence classification
# ---------------------------------------------------------------------------


class MarketClass(StrEnum):
    RU_DOMESTIC = "ru_domestic"
    RU_TOUCHING_INTERNATIONAL = "ru_touching_international"
    GLOBAL_NON_RU = "global_non_ru"
    STRUCTURALLY_CONSTRAINED = "structurally_constrained"


class IntentClass(StrEnum):
    MAINTENANCE = "maintenance"
    DIRECT_INVENTORY = "direct_inventory"
    TICKETING_PROOF = "ticketing_proof"
    CARRIER_OR_AIRPORT_SCOPE = "carrier_or_airport_scope"
    ROUTE_RECOMMENDATION = "route_recommendation"


class EvidenceClass(StrEnum):
    DIAGNOSTIC_ONLY = "diagnostic_only"
    TICKETING_REQUIRED = "ticketing_required"
    ABSENCE_CLAIM = "absence_claim"
    SHOPPING_ADVISORY = "shopping_advisory"


# ---------------------------------------------------------------------------
# Routing strategy
# ---------------------------------------------------------------------------


class RoutingStrategy(StrEnum):
    DOMESTIC_RU = "domestic-ru"
    RU_PRIORITY = "ru-priority"
    HUB_LIST = "hub-list"


# ---------------------------------------------------------------------------
# Route family (mirrors route_mode values, underscore form)
# ---------------------------------------------------------------------------


class RouteFamily(StrEnum):
    DIRECT_INVENTORY = "direct_inventory"
    DOMESTIC_RU = "domestic_ru"
    RU_PRIORITY = "ru_priority"
    HUB_LIST = "hub_list"


# ---------------------------------------------------------------------------
# Required controls (probe control types, not probe_type from ports)
# ---------------------------------------------------------------------------


class RequiredControl(StrEnum):
    EXACT_AIRPORT_DIRECT = "exact_airport_direct"
    DATE_WINDOW_DIRECT = "date_window_direct"
    MOSCOW_GATEWAY_DIRECT = "moscow_gateway_direct"
    CARRIER_AGGREGATE = "carrier_aggregate"
    FULL_ROUTE_AGGREGATE = "full_route_aggregate"


# ---------------------------------------------------------------------------
# Absence taxonomy
# ---------------------------------------------------------------------------


class AbsenceReason(StrEnum):
    PROVIDER_EMPTY = "provider_empty"
    PROVIDER_HORIZON_UNCERTAINTY = "provider_horizon_uncertainty"
    PROVIDER_COVERAGE_GAP = "provider_coverage_gap"
    CONSTRAINT_MISMATCH = "constraint_mismatch"
    RUNTIME_PROVIDER_FAILURE = "runtime_provider_failure"
    STRUCTURAL_UNAVAILABILITY = "structural_unavailability"
    TICKETING_PROTECTION_UNCERTAINTY = "ticketing_protection_uncertainty"


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
    CACHE_HIT = "cache_hit"
    STALE_CACHE_USED = "stale_cache_used"
