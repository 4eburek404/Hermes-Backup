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
    "kb-search",
    "kb-roundtrip",
    "fli-search",
    "fli-dates",
    "route",
    "metrics",
)

ROUTE_COMMANDS = (
    "plan",
    "validate",
    "rank",
    "assemble",
    "kb-assemble",
    "live-assemble",
)

PRIMARY_ROUTE_COMMAND = "search"
LEGACY_PRIMARY_ROUTE_COMMAND = "route live-assemble"
TARGETED_PROBE_COMMANDS = ("diagnose probe",)
LEGACY_TARGETED_PROBE_COMMANDS = ("kb-search", "kb-roundtrip", "fli-search", "fli-dates")
COMPATIBILITY_COMMANDS = ("route live-assemble", "route kb-assemble", *LEGACY_TARGETED_PROBE_COMMANDS, "maintenance check", "catalog update", "catalog manifest", "doctor")
LIVE_PROVIDER_COMMANDS = (PRIMARY_ROUTE_COMMAND, *TARGETED_PROBE_COMMANDS, LEGACY_PRIMARY_ROUTE_COMMAND, "route kb-assemble", *LEGACY_TARGETED_PROBE_COMMANDS)

CATALOG_READ_COMMANDS = (
    "cities search",
    "airports explain",
    "fli-search",
    "route plan",
    "route kb-assemble",
    "route live-assemble",
    "metrics workflow",
    "search",
    "diagnose plan",
)
CATALOG_REFRESH_COMMANDS = ("maint catalog refresh",)
