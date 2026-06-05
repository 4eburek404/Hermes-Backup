from __future__ import annotations

ROOT_COMMANDS = (
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

PRIMARY_ROUTE_COMMAND = "route live-assemble"
TARGETED_PROBE_COMMANDS = ("kb-search", "kb-roundtrip", "fli-search", "fli-dates")
COMPATIBILITY_COMMANDS = ("route kb-assemble",)
LIVE_PROVIDER_COMMANDS = (*TARGETED_PROBE_COMMANDS, *COMPATIBILITY_COMMANDS, PRIMARY_ROUTE_COMMAND)

CATALOG_REFRESH_COMMANDS = (
    "cities search",
    "airports explain",
    "fli-search",
    "route plan",
    "route kb-assemble",
    "route live-assemble",
    "metrics workflow",
)
