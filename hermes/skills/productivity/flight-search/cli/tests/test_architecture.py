from __future__ import annotations

import ast
import json
import re
import tomllib
import unittest

from flights_cli import __skill_version__, __version__
from flights_cli.command_surface import (
    COMMAND_SURFACE_VERSION,
    DIAGNOSTIC_COMMANDS,
    PRIMARY_ROUTE_COMMAND,
)
from flights_cli.config import (
    CITY_AIRPORTS_EXCLUDED_BY_DEFAULT,
    KUPIBILET_CITY_CODE_FIRST_AIRPORTS,
    MULTI_AIRPORT_GROUPS,
    PREFERRED_AIRPORT_TIERS,
)
from flights_cli.ports.providers import ProviderName
from flights_cli.adapters.providers.registry import PROVIDER_REGISTRY
from flights_cli.contracts.registry import current_contract

from helpers import PROJECT


def import_targets(path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.add(node.module)
    return targets


def function_annotations(tree: ast.AST) -> dict[str, dict[str, str]]:
    annotations: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        annotations[node.name] = {
            arg.arg: ast.unparse(arg.annotation)
            for arg in node.args.args + node.args.kwonlyargs
            if arg.annotation is not None
        }
    return annotations


class ArchitectureTests(unittest.TestCase):
    def version_manifest(self) -> dict:
        return json.loads(
            (PROJECT.parent / "version_manifest.json").read_text(encoding="utf-8")
        )

    def test_pyproject_version_matches_runtime_version(self) -> None:
        data = tomllib.loads((PROJECT / "pyproject.toml").read_text())
        self.assertEqual(data["project"]["version"], __version__)
        manifest = self.version_manifest()
        self.assertEqual(data["project"]["name"], manifest["cli"]["package"])
        self.assertEqual(data["project"]["version"], manifest["cli"]["version"])

    def test_skill_version_matches_runtime_version(self) -> None:
        skill = PROJECT.parent / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        match = re.search(r"^version: (.+)$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __skill_version__)
        manifest = self.version_manifest()
        self.assertEqual(
            manifest["skill"], {"name": "flight-search", "version": __skill_version__}
        )

    def test_version_manifest_matches_contract_registry_and_command_surface(
        self,
    ) -> None:
        manifest = self.version_manifest()
        self.assertEqual(
            manifest["contracts"]["user_answer"],
            current_contract("user_answer")["schema_version"],
        )
        self.assertEqual(
            manifest["contracts"]["flight_search_request"],
            current_contract("search_request")["schema_version"],
        )
        self.assertEqual(
            manifest["contracts"]["flight_search_result"],
            current_contract("search_result")["schema_version"],
        )
        self.assertEqual(
            manifest["command_surface"]["version"], COMMAND_SURFACE_VERSION
        )
        self.assertEqual(
            manifest["command_surface"]["canonical_path"],
            f"{PRIMARY_ROUTE_COMMAND} --request",
        )
        self.assertEqual(
            sorted(manifest["command_surface"]["diagnostic_commands"]),
            sorted(DIAGNOSTIC_COMMANDS),
        )

    def test_active_provider_set_includes_opt_in_tutu_provider(self) -> None:
        # Tutu is opt-in only, but it is part of the typed provider registry.
        self.assertEqual(set(ProviderName.__args__), {"kupibilet", "fli", "tutu"})
        self.assertEqual(set(PROVIDER_REGISTRY.keys()), {"kupibilet", "fli", "tutu"})

    def test_ist_resolves_to_exact_code_only(self) -> None:
        # IST default scope is IST only; SAW requires explicit request.
        self.assertIn("IST", CITY_AIRPORTS_EXCLUDED_BY_DEFAULT)
        self.assertEqual(CITY_AIRPORTS_EXCLUDED_BY_DEFAULT["IST"], ["SAW"])

    def test_lon_preferred_tier_lhr_then_lgw_excludes_stn_ltn(self) -> None:
        # LHR tier 1 preferred, LGW tier 2 deferred; STN/LTN excluded by default.
        lon_tiers = PREFERRED_AIRPORT_TIERS["LON"]
        self.assertEqual(lon_tiers[0]["tier"], 1)
        self.assertEqual(lon_tiers[0]["airports"], ["LHR"])
        self.assertEqual(lon_tiers[0]["role"], "preferred")
        self.assertEqual(lon_tiers[1]["tier"], 2)
        self.assertEqual(lon_tiers[1]["airports"], ["LGW"])
        self.assertEqual(lon_tiers[1]["role"], "deferred")
        self.assertEqual(
            sorted(CITY_AIRPORTS_EXCLUDED_BY_DEFAULT["LON"]), ["LTN", "STN"]
        )

    def test_kupibilet_mow_city_code_first_and_exact_deferred(self) -> None:
        # KupiBilet uses MOW city-code first; SVO/DME/VKO are deferred probes.
        self.assertIn("MOW", KUPIBILET_CITY_CODE_FIRST_AIRPORTS)
        self.assertEqual(
            sorted(KUPIBILET_CITY_CODE_FIRST_AIRPORTS["MOW"]), ["DME", "SVO", "VKO"]
        )

    def test_moscow_airports_are_not_interchangeable(self) -> None:
        # SVO/DME/VKO are separate airports; not interchangeable for itinerary continuity.
        moscow = MULTI_AIRPORT_GROUPS["moscow"]
        self.assertEqual(sorted(moscow["airports"]), ["DME", "SVO", "VKO"])

    def test_report_contract_primary_fields_exist(self) -> None:
        # Runtime offer_graph stays under diagnose trace; public
        # Result projection exposes one frontier order and one canonical text.
        from flights_cli.reporting.user_answer import build_user_answer
        from flights_cli.pipeline.offer_graph import build_offer_graph

        # Verify these are callable code-level functions, not just prose references.
        self.assertTrue(callable(build_user_answer))
        self.assertTrue(callable(build_offer_graph))

    def test_active_contract_schema_resources_match_registry_versions(self) -> None:
        contracts = PROJECT / "flights_cli" / "contracts"
        for contract_name in (
            "user_answer",
            "search_request",
            "search_result",
            "route_trace",
            "search_plan",
            "offer_graph",
        ):
            contract = current_contract(contract_name)
            resource = contract.get("schema_resource")
            if not resource:
                continue
            with self.subTest(contract_name=contract_name):
                schema_path = contracts / resource
                self.assertTrue(schema_path.is_file())
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    schema["properties"]["schema_version"]["const"],
                    contract["schema_version"],
                )

    def test_module_dependency_boundaries(self) -> None:
        root = PROJECT / "flights_cli"
        modules = {
            ".".join(path.relative_to(PROJECT).with_suffix("").parts): path
            for path in root.rglob("*.py")
        }
        edges: dict[str, set[str]] = {module: set() for module in modules}

        def resolve_target(target: str) -> str | None:
            parts = target.split(".")
            for end in range(len(parts), 0, -1):
                candidate = ".".join(parts[:end])
                if candidate in modules:
                    return candidate
            return None

        for module, path in modules.items():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                target_name = None
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.level:
                        base = module.split(".")[: -node.level]
                        target_name = ".".join(base + [node.module])
                    else:
                        target_name = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        target = resolve_target(alias.name)
                        if target and target != module:
                            edges[module].add(target)
                    continue

                if target_name and target_name.startswith("flights_cli"):
                    target = resolve_target(target_name)
                    if target and target != module:
                        edges[module].add(target)

        visiting: list[str] = []
        visited: set[str] = set()
        cycles: list[list[str]] = []

        def visit(module: str) -> None:
            visited.add(module)
            visiting.append(module)
            for target in edges[module]:
                if target not in visited:
                    visit(target)
                elif target in visiting:
                    cycles.append(visiting[visiting.index(target) :] + [target])
            visiting.pop()

        for module in modules:
            if module not in visited:
                visit(module)

        forbidden_provider_edges = [
            (source, target)
            for source, targets in edges.items()
            for target in targets
            if source.startswith("flights_cli.providers.")
            and target.startswith(("flights_cli.cli", "flights_cli.commands."))
        ]
        forbidden_orchestrator_provider_edges = [
            (source, target)
            for source, targets in edges.items()
            for target in targets
            if source.startswith("flights_cli.orchestrators.")
            and target.startswith(
                ("flights_cli.providers.kupibilet", "flights_cli.providers.fli_mcp")
            )
        ]
        forbidden_output_edges = [
            (source, target)
            for source, targets in edges.items()
            for target in targets
            if source == "flights_cli.output"
            and target.startswith(
                (
                    "flights_cli.providers.",
                    "flights_cli.orchestrators.",
                    "flights_cli.commands.",
                )
            )
        ]

        self.assertEqual(cycles, [])
        self.assertEqual(forbidden_provider_edges, [])
        self.assertEqual(forbidden_orchestrator_provider_edges, [])
        self.assertEqual(forbidden_output_edges, [])

    def test_live_assembly_core_has_no_args_like_adapter(self) -> None:
        root = PROJECT / "flights_cli"
        probe_dispatcher = root / "execution" / "probe_dispatcher.py"
        aggregate_runner = root / "execution" / "aggregate_control_runner.py"
        search_executor = root / "execution" / "search_executor.py"

        for path in (probe_dispatcher, aggregate_runner, search_executor):
            with self.subTest(path=path.name):
                self.assertFalse("argparse" in import_targets(path))

        tree = ast.parse(search_executor.read_text(encoding="utf-8"))
        annotations = function_annotations(tree)
        self.assertEqual(annotations["execute_search"]["request"], "SearchRequest")

    def test_provider_runtime_does_not_accept_argparse_namespace(self) -> None:
        provider_root = PROJECT / "flights_cli" / "providers"
        for path in sorted(provider_root.glob("*.py")):
            with self.subTest(path=path.name):
                self.assertFalse("argparse" in import_targets(path))
                annotations = function_annotations(
                    ast.parse(path.read_text(encoding="utf-8"))
                )
                flattened = {
                    annotation
                    for function in annotations.values()
                    for annotation in function.values()
                }
                self.assertTrue(
                    flattened.isdisjoint({"argparse.Namespace", "Namespace"})
                )

    def test_reporting_does_not_import_orchestrators(self) -> None:
        reporting_root = PROJECT / "flights_cli" / "reporting"
        for path in sorted(reporting_root.rglob("*.py")):
            with self.subTest(path=path.relative_to(reporting_root)):
                self.assertFalse(
                    any(
                        target.startswith("flights_cli.orchestrators")
                        or target == "orchestrators"
                        for target in import_targets(path)
                    )
                )


if __name__ == "__main__":
    unittest.main()
