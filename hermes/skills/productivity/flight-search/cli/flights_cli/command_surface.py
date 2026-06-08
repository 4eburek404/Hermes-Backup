from __future__ import annotations

ROOT_COMMANDS = (
    "search",
    "diagnose",
    "maint",
    "doctor",
    "maintenance",
    "catalog",
    "cities",
    "airports",
    "route",
    "metrics",
)

ROUTE_COMMANDS = (
    "plan",
    "validate",
    "rank",
    "assemble",
    "live-assemble",
)

PRIMARY_ROUTE_COMMAND = "search"
LEGACY_PRIMARY_ROUTE_COMMAND = "route live-assemble"
TARGETED_PROBE_COMMANDS = (
    "diagnose probe",
    "diagnose kb-search",
    "diagnose kb-roundtrip",
    "diagnose fli-search",
    "diagnose fli-dates",
)
COMPATIBILITY_COMMANDS = ("route live-assemble", "maintenance check", "catalog update", "catalog manifest", "doctor")
LIVE_PROVIDER_COMMANDS = (PRIMARY_ROUTE_COMMAND, *TARGETED_PROBE_COMMANDS, LEGACY_PRIMARY_ROUTE_COMMAND)

CATALOG_READ_COMMANDS = (
    "cities search",
    "airports explain",
    "diagnose fli-search",
    "route plan",
    "route live-assemble",
    "metrics workflow",
    "search",
    "diagnose plan",
)
CATALOG_REFRESH_COMMANDS = ("maint catalog refresh",)
