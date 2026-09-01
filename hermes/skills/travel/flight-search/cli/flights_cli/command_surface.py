from __future__ import annotations

from dataclasses import dataclass

COMMAND_SURFACE_VERSION = "command_surface.v3"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Stable metadata for one dispatchable CLI leaf command."""

    path: tuple[str, ...]
    audience: str
    help: str
    catalog_access: str | None = None

    def __post_init__(self) -> None:
        if not self.path or any(not part or " " in part for part in self.path):
            raise ValueError("command path must contain non-empty CLI path segments")
        if self.audience not in {"agent", "maintenance", "metadata"}:
            raise ValueError(f"unsupported command audience: {self.audience}")
        if self.catalog_access not in {None, "auto_refresh", "refresh_explicit"}:
            raise ValueError(f"unsupported catalog access: {self.catalog_access}")

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
CATALOG_READ_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.requires_catalog
)
CATALOG_AUTO_REFRESH_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.catalog_access == "auto_refresh"
)
CATALOG_REFRESH_COMMANDS = tuple(
    spec.name for spec in COMMAND_SPECS if spec.catalog_access == "refresh_explicit"
)
