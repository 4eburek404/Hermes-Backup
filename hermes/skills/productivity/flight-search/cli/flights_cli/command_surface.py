from __future__ import annotations

COMMAND_SURFACE_VERSION = "command_surface.v1"

ROOT_COMMANDS = (
    "search",
    "diagnose",
    "maint",
    "cities",
    "airports",
    "route",
)

ROUTE_COMMANDS = (
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
DIAGNOSTIC_COMMANDS = (
    "diagnose plan",
    "diagnose render",
    *TARGETED_PROBE_COMMANDS,
    *(f"route {name}" for name in ROUTE_COMMANDS),
)
LIVE_PROVIDER_COMMANDS = (PRIMARY_ROUTE_COMMAND, *TARGETED_PROBE_COMMANDS)

CATALOG_READ_COMMANDS = (
    "cities search",
    "airports explain",
    "diagnose fli-search",
    "search",
    "diagnose plan",
)
CATALOG_AUTO_REFRESH_COMMANDS = CATALOG_READ_COMMANDS
CATALOG_REFRESH_COMMANDS = ("maint catalog refresh",)
