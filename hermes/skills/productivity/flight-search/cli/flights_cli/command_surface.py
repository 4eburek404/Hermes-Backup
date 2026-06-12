from __future__ import annotations

ROOT_COMMANDS = (
    "search",
    "diagnose",
    "maint",
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
)

PRIMARY_ROUTE_COMMAND = "search"
TARGETED_PROBE_COMMANDS = (
    "diagnose probe",
    "diagnose kb-search",
    "diagnose kb-roundtrip",
    "diagnose fli-search",
    "diagnose fli-dates",
)
LIVE_PROVIDER_COMMANDS = (PRIMARY_ROUTE_COMMAND, *TARGETED_PROBE_COMMANDS)

CATALOG_READ_COMMANDS = (
    "cities search",
    "airports explain",
    "diagnose fli-search",
    "route plan",
    "metrics workflow",
    "search",
    "diagnose plan",
)
CATALOG_AUTO_REFRESH_COMMANDS = CATALOG_READ_COMMANDS
CATALOG_REFRESH_COMMANDS = ("maint catalog refresh",)
