from __future__ import annotations

COMMAND_SURFACE_VERSION = "command_surface.v1"

PRIMARY_ROUTE_COMMAND = "search"
AGENT_COMMANDS = (PRIMARY_ROUTE_COMMAND,)
DIAGNOSTIC_PROBE_COMMANDS = ("diagnose probe",)
DIAGNOSTIC_COMMANDS = (
    "diagnose plan",
    "diagnose render",
    *DIAGNOSTIC_PROBE_COMMANDS,
)

CATALOG_READ_COMMANDS = (
    "cities search",
    "airports explain",
    "search",
    "diagnose plan",
)
CATALOG_AUTO_REFRESH_COMMANDS = CATALOG_READ_COMMANDS
CATALOG_REFRESH_COMMANDS = ("maint catalog refresh",)
