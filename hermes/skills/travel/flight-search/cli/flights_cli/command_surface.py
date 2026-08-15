from __future__ import annotations

from dataclasses import dataclass

COMMAND_SURFACE_VERSION = "command_surface.v2"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Stable metadata for one dispatchable CLI leaf command."""

    path: tuple[str, ...]
    audience: str
    help: str
    catalog_access: str | None = None
    diagnostic_probe: bool = False

    def __post_init__(self) -> None:
        if not self.path or any(not part or " " in part for part in self.path):
            raise ValueError("command path must contain non-empty CLI path segments")
        if self.audience not in {"agent", "diagnostic", "maintenance", "metadata"}:
            raise ValueError(f"unsupported command audience: {self.audience}")
        if self.catalog_access not in {None, "auto_refresh", "refresh_explicit"}:
            raise ValueError(f"unsupported catalog access: {self.catalog_access}")
        if self.diagnostic_probe and self.audience != "diagnostic":
            raise ValueError("diagnostic probes must have diagnostic audience")

    @property
    def name(self) -> str:
        return " ".join(self.path)

    @property
    def leaf(self) -> str:
        return self.path[-1]

    @property
    def requires_catalog(self) -> bool:
        return self.catalog_access == "auto_refresh"


SEARCH_COMMAND = CommandSpec(
    path=("search",),
    audience="agent",
    help=(
        "Primary request-file route search; JSON output keeps compact "
        "flight_search_result envelope."
    ),
    catalog_access="auto_refresh",
)
DIAGNOSE_PLAN_COMMAND = CommandSpec(
    path=("diagnose", "plan"),
    audience="diagnostic",
    help=(
        "Render the route segment plan from a flight_search_request.v4 file "
        "without provider calls."
    ),
    catalog_access="auto_refresh",
)
DIAGNOSE_PROBE_COMMAND = CommandSpec(
    path=("diagnose", "probe"),
    audience="diagnostic",
    help="Run a single provider probe from a probe JSON file.",
    diagnostic_probe=True,
)
DIAGNOSE_RENDER_COMMAND = CommandSpec(
    path=("diagnose", "render"),
    audience="diagnostic",
    help="Validate and render answer from a flight-search result JSON file.",
)
DIAGNOSE_TRACE_COMMAND = CommandSpec(
    path=("diagnose", "trace"),
    audience="diagnostic",
    help="Run search and return the full route/live diagnostic trace.",
    catalog_access="auto_refresh",
)
MAINT_CHECK_COMMAND = CommandSpec(
    path=("maint", "check"),
    audience="maintenance",
    help=(
        "Report source/runtime provenance and local maintenance status without "
        "network calls."
    ),
)
MAINT_DOCTOR_COMMAND = CommandSpec(
    path=("maint", "doctor"),
    audience="maintenance",
    help="Check local caches and static catalog status without provider calls.",
)
MAINT_CATALOG_MANIFEST_COMMAND = CommandSpec(
    path=("maint", "catalog", "manifest"),
    audience="maintenance",
    help="Show the local static catalog manifest.",
)
MAINT_CATALOG_REFRESH_COMMAND = CommandSpec(
    path=("maint", "catalog", "refresh"),
    audience="maintenance",
    help="Download public static catalog JSON files explicitly.",
    catalog_access="refresh_explicit",
)
CITIES_SEARCH_COMMAND = CommandSpec(
    path=("cities", "search"),
    audience="metadata",
    help="Search city name or IATA code in local cache.",
    catalog_access="auto_refresh",
)
AIRPORTS_EXPLAIN_COMMAND = CommandSpec(
    path=("airports", "explain"),
    audience="metadata",
    help="Explain airport and multi-airport risk rules.",
    catalog_access="auto_refresh",
)

COMMAND_SPECS = (
    CITIES_SEARCH_COMMAND,
    AIRPORTS_EXPLAIN_COMMAND,
    SEARCH_COMMAND,
    DIAGNOSE_PLAN_COMMAND,
    DIAGNOSE_RENDER_COMMAND,
    DIAGNOSE_TRACE_COMMAND,
    DIAGNOSE_PROBE_COMMAND,
    MAINT_CHECK_COMMAND,
    MAINT_DOCTOR_COMMAND,
    MAINT_CATALOG_MANIFEST_COMMAND,
    MAINT_CATALOG_REFRESH_COMMAND,
)

_specs_by_name = {spec.name: spec for spec in COMMAND_SPECS}
if len(_specs_by_name) != len(COMMAND_SPECS):
    raise RuntimeError("command surface contains duplicate leaf paths")
PRIMARY_ROUTE_COMMAND = SEARCH_COMMAND.name
AGENT_COMMANDS = tuple(spec.name for spec in COMMAND_SPECS if spec.audience == "agent")
DIAGNOSTIC_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.audience == "diagnostic"
)
DIAGNOSTIC_PROBE_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.diagnostic_probe
)
CATALOG_READ_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.requires_catalog
)
CATALOG_AUTO_REFRESH_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.catalog_access == "auto_refresh"
)
CATALOG_REFRESH_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.catalog_access == "refresh_explicit"
)
