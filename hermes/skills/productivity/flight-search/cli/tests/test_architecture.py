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
from flights_cli.config import MULTI_AIRPORT_GROUPS
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

    def test_provider_names_are_registry_validated_strings(self) -> None:
        self.assertIs(ProviderName, str)
        self.assertEqual(set(PROVIDER_REGISTRY.keys()), {"kupibilet", "tutu"})

    def test_kupibilet_transport_is_separate_from_fetch_orchestration(self) -> None:
        from pathlib import Path

        provider_root = Path("flights_cli/providers")
        provider_sources = [
            (provider_root / name).read_text(encoding="utf-8")
            for name in ("kupibilet.py", "kupibilet_transport.py", "static_catalog.py")
        ]

        for provider_source in provider_sources:
            self.assertNotIn("urllib.request", provider_source)
            self.assertNotIn("urllib.error", provider_source)
            self.assertNotIn("decode_http_body", provider_source)
        self.assertIn("post_kupibilet_search", provider_sources[0])

    def test_moscow_airports_are_not_interchangeable(self) -> None:
        # SVO/DME/VKO are separate airports; not interchangeable for itinerary continuity.
        moscow = MULTI_AIRPORT_GROUPS["moscow"]
        self.assertEqual(sorted(moscow["airports"]), ["DME", "SVO", "VKO"])

    def test_report_contract_primary_fields_exist(self) -> None:
        # Runtime offer_graph stays under diagnose trace; public
        # Result projection exposes one frontier order and one canonical text.
        from flights_cli.reporting.user_answer import build_user_answer
        from flights_cli.pipeline.offer_graph_builder import build_offer_graph

        # Verify these are callable code-level functions, not just prose references.
        self.assertTrue(callable(build_user_answer))
        self.assertTrue(callable(build_offer_graph))

    def test_route_hypotheses_use_the_single_execution_and_decision_pipeline(self) -> None:
        root = PROJECT / "flights_cli"
        executor = (root / "execution" / "search_executor.py").read_text(
            encoding="utf-8"
        )
        planner = (root / "orchestrators" / "search_plan_builder.py").read_text(
            encoding="utf-8"
        )
        discovery = (root / "domain" / "gateway_discovery.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("RouteLegProbeExecutor", executor)
        self.assertNotIn("GatewayLegProbeExecutor", executor)
        self.assertNotIn("_gateway_leg_queries", planner)
        self.assertNotIn("GatewayCandidate", discovery)
        self.assertNotIn("HypothesisAssembler", executor + planner + discovery)

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
            and target.startswith(("flights_cli.providers.kupibilet",))
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

    def test_catalog_semantics_contains_no_human_text_projection(self) -> None:
        semantics = (
            PROJECT / "flights_cli" / "reporting" / "catalog_semantics.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(semantics)
        function_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }

        self.assertTrue(
            {
                "baggage_piece_text",
                "catalog_caveats",
                "compact_price_text",
                "provider_label",
                "source_ticketing_note",
            }.isdisjoint(function_names)
        )
        self.assertIsNone(re.search(r"[А-Яа-яЁё]", semantics))

    def test_catalog_rendering_is_the_only_user_answer_text_owner(self) -> None:
        reporting = PROJECT / "flights_cli" / "reporting"
        user_answer = (reporting / "user_answer.py").read_text(encoding="utf-8")
        rendering = (reporting / "catalog_rendering.py").read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"[А-Яа-яЁё]", user_answer))
        self.assertNotIn("def render_user_answer(", user_answer)
        self.assertIn("def render_user_answer(", rendering)
        self.assertIn("def source_boundaries(", rendering)
        self.assertNotIn(
            "def source_boundaries(",
            (reporting / "coverage.py").read_text(encoding="utf-8"),
        )

    def test_live_assembly_core_has_no_args_like_adapter(self) -> None:
        root = PROJECT / "flights_cli"
        probe_dispatcher = root / "execution" / "probe_dispatcher.py"
        search_executor = root / "execution" / "search_executor.py"

        for path in (probe_dispatcher, search_executor):
            with self.subTest(path=path.name):
                self.assertFalse("argparse" in import_targets(path))

        executor_annotations = function_annotations(
            ast.parse(search_executor.read_text(encoding="utf-8"))
        )
        self.assertEqual(executor_annotations["execute"]["plan"], "SearchPlan")
        executor_tree = ast.parse(search_executor.read_text(encoding="utf-8"))
        execute = next(
            node
            for node in ast.walk(executor_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "execute"
        )
        self.assertIsNotNone(execute.returns)
        self.assertEqual(ast.unparse(execute.returns), "SearchEvidence")
        workflow = root / "orchestrators" / "search_workflow.py"
        workflow_annotations = function_annotations(
            ast.parse(workflow.read_text(encoding="utf-8"))
        )
        self.assertEqual(workflow_annotations["run"]["request"], "SearchRequest")
        workflow_tree = ast.parse(workflow.read_text(encoding="utf-8"))
        run = next(
            node
            for node in ast.walk(workflow_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        self.assertEqual(ast.unparse(run.returns), "FlightSearchResult")
        plan_builder = root / "orchestrators" / "search_plan_builder.py"
        builder_annotations = function_annotations(
            ast.parse(plan_builder.read_text(encoding="utf-8"))
        )
        self.assertEqual(builder_annotations["build"]["request"], "SearchRequest")

    def test_search_workflow_is_the_only_production_executor_composition(self) -> None:
        root = PROJECT / "flights_cli"
        callers = []
        for path in root.rglob("*.py"):
            if "SearchExecutor(" in path.read_text(encoding="utf-8"):
                callers.append(path.relative_to(root).as_posix())
        self.assertEqual(callers, ["orchestrators/search_workflow.py"])

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

    def test_tutu_parser_owns_normalization_without_transport_or_cache(self) -> None:
        provider_root = PROJECT / "flights_cli" / "providers"
        parser_path = provider_root / "tutu_parser.py"
        facade_path = provider_root / "tutu_mcp.py"
        parser_tree = ast.parse(parser_path.read_text(encoding="utf-8"))
        facade_tree = ast.parse(facade_path.read_text(encoding="utf-8"))

        self.assertTrue(
            {
                "re",
                "typing",
                "config",
                "domain.normalize",
                "domain.offer_order",
            }.issubset(import_targets(parser_path))
        )
        self.assertTrue(
            import_targets(parser_path).isdisjoint(
                {
                    "live_cache",
                    "tutu_client",
                    "tutu_transport",
                    "urllib",
                    "urllib.request",
                }
            )
        )

        parser_functions = {
            node.name
            for node in ast.walk(parser_tree)
            if isinstance(node, ast.FunctionDef)
        }
        facade_functions = {
            node.name
            for node in ast.walk(facade_tree)
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("parse_tutu_avia_search", parser_functions)
        self.assertNotIn("parse_tutu_avia_search", facade_functions)

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

    def test_execution_does_not_import_reporting(self) -> None:
        execution_root = PROJECT / "flights_cli" / "execution"
        for path in sorted(execution_root.rglob("*.py")):
            with self.subTest(path=path.relative_to(execution_root)):
                self.assertFalse(
                    any(
                        target.startswith(("reporting", "flights_cli.reporting"))
                        or ".reporting" in target
                        for target in import_targets(path)
                    )
                )

    def test_coverage_snapshot_is_the_only_coverage_semantics_owner(self) -> None:
        root = PROJECT / "flights_cli"
        ledger = (root / "execution" / "probe_ledger.py").read_text(encoding="utf-8")
        coverage = (root / "reporting" / "coverage.py").read_text(encoding="utf-8")

        for forbidden in (
            "coverage_warnings",
            "negative_evidence_type",
            '"completeness"',
            "absence_class",
            "_evidence_classification",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, ledger)
        self.assertIn("def _coverage_diagnostics_from_ledger(", coverage)
        self.assertIn("if bucket not in ledger", coverage)
        self.assertNotIn('ledger.get("completeness")', coverage)
        self.assertNotIn('ledger.get("coverage_warnings")', coverage)

    def test_contract_validation_owns_all_semantic_validators(self) -> None:
        root = PROJECT / "flights_cli"
        validation_path = root / "contracts" / "validation.py"
        validation_tree = ast.parse(validation_path.read_text(encoding="utf-8"))
        validation_functions = {
            node.name
            for node in validation_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(
            {
                "flight_search_result_semantic_errors",
                "user_answer_contract_semantic_errors",
                "validate_flight_search_result",
                "validate_user_answer",
            }.issubset(validation_functions)
        )

        path = root / "pipeline" / "result_contract.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ],
            [],
        )
        self.assertIn("contracts.validation", import_targets(path))

    def test_domain_and_reporting_dependency_direction(self) -> None:
        domain_root = PROJECT / "flights_cli" / "domain"
        for path in sorted(domain_root.rglob("*.py")):
            with self.subTest(layer="domain", path=path.relative_to(domain_root)):
                self.assertFalse(
                    any(
                        target.startswith(("execution", "reporting"))
                        or ".execution" in target
                        or ".reporting" in target
                        for target in import_targets(path)
                    )
                )

        reporting_root = PROJECT / "flights_cli" / "reporting"
        for path in sorted(reporting_root.rglob("*.py")):
            with self.subTest(layer="reporting", path=path.relative_to(reporting_root)):
                self.assertFalse(
                    any(
                        target.startswith(("execution", "orchestrators"))
                        or ".execution" in target
                        or ".orchestrators" in target
                        for target in import_targets(path)
                    )
                )

    def test_stop_policy_is_the_only_owner_of_stop_defaults_and_filtering(self) -> None:
        root = PROJECT / "flights_cli"
        stop_policy = (root / "domain" / "stop_policy.py").read_text(encoding="utf-8")
        kupibilet_adapter = (
            root / "adapters" / "providers" / "kupibilet_adapter.py"
        ).read_text(encoding="utf-8")
        kupibilet_parser = (root / "providers" / "kupibilet_parser.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def filter_provider_offers(", stop_policy)
        self.assertNotIn("connection_policy", stop_policy)
        self.assertNotIn("filter_provider_offers", kupibilet_adapter)
        self.assertIn("airport_mismatch_violations", kupibilet_parser)
        self.assertIn("chronology_violations", kupibilet_parser)
        self.assertIn(
            "chronology_violations",
            (root / "providers" / "tutu_parser.py").read_text(encoding="utf-8"),
        )
        self.assertFalse(
            any(
                "reportable_by_stop_policy" in path.read_text(encoding="utf-8")
                for path in root.rglob("*.py")
            )
        )
        user_answer = (root / "reporting" / "user_answer.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('stop_diagnostics["max_reported_connections"]', user_answer)
        builder = (root / "orchestrators" / "search_plan_builder.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("resolve_stop_policy", builder)
        for relative in (
            "pipeline/candidate_validation.py",
            "pipeline/candidate_scoring.py",
            "pipeline/decision_scorer.py",
            "pipeline/frontier_selection.py",
        ):
            with self.subTest(relative=relative):
                self.assertIn(
                    "BUSINESS_DEFAULT_STOP_POLICY",
                    (root / relative).read_text(encoding="utf-8"),
                )

    def test_stop_math_is_delegated_to_stop_policy(self) -> None:
        root = PROJECT / "flights_cli"
        forbidden_snippets = {
            "providers/kupibilet_parser.py": ("max(0, len(normalized_flights) - 1)",),
            "providers/tutu_parser.py": (
                "def _journey_connection_count",
                "def _journeys_have_airport_change",
            ),
            "providers/segment_normalization.py": ("max(0, len(segments) - 1)",),
            "domain/offer_order.py": ("max(0, len(segments) - 1)",),
            "reporting/frontier_projection.py": ("max(0, len(journey_segments) - 1)",),
            "reporting/catalog_projection.py": ("max_direction_segments",),
            "reporting/user_answer.py": ("max(0, len(segments) - 1)",),
        }
        for relative, snippets in forbidden_snippets.items():
            source = (root / relative).read_text(encoding="utf-8")
            for snippet in snippets:
                with self.subTest(relative=relative, snippet=snippet):
                    self.assertNotIn(snippet, source)

        stop_tier_owners = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if "def stop_tier(" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(stop_tier_owners, ["domain/stop_policy.py"])

    def test_only_preexisting_public_facades_remain(self) -> None:
        root = PROJECT / "flights_cli"
        for relative in (
            "commands/common.py",
            "contracts/schema_errors.py",
            "domain/provider_offer_filter.py",
            "domain/stop_metrics.py",
            "pipeline/candidate_ranker.py",
            "pipeline/offer_graph.py",
            "reporting/user_answer_contracts.py",
        ):
            self.assertFalse((root / relative).exists(), relative)

    def test_direct_candidate_policy_has_one_owner(self) -> None:
        root = PROJECT / "flights_cli" / "pipeline"
        frontier = (root / "frontier_selection.py").read_text(encoding="utf-8")
        builder = (root / "offer_graph_builder.py").read_text(encoding="utf-8")
        self.assertIn("from .direct_gate import candidate_is_direct", frontier)
        self.assertIn("select_best_stop_tier", frontier)
        self.assertIn(
            "domain.stop_policy", import_targets(root / "frontier_selection.py")
        )
        self.assertNotIn("def _is_direct_inventory", frontier)
        self.assertNotIn("direct_mode", builder)
        self.assertNotIn("direct_gate", import_targets(root / "offer_graph_builder.py"))

    def test_candidate_validation_is_authoritative_for_frontier(self) -> None:
        root = PROJECT / "flights_cli" / "pipeline"
        scoring = (root / "candidate_scoring.py").read_text(encoding="utf-8")
        frontier = (root / "frontier_selection.py").read_text(encoding="utf-8")
        self.assertNotIn("chronology_violations", scoring)
        self.assertNotIn("airport_mismatch_violations", scoring)
        self.assertNotIn("cross_ticket_mct_violations", scoring)
        self.assertIn('validation.get("status") == "valid"', frontier)

    def test_cross_airport_minimum_is_reserved_not_an_acceptance_rule(self) -> None:
        path = PROJECT / "flights_cli" / "domain" / "connection_policy.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "cross_ticket_mct_violations"
        )
        referenced_attributes = {
            node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)
        }

        self.assertNotIn("min_cross_airport_min", referenced_attributes)
        self.assertNotIn("required_min(same_airport", source)

    def test_offer_graph_model_only_models_and_serializes(self) -> None:
        path = PROJECT / "flights_cli" / "pipeline" / "offer_graph_model.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top_level_definitions = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        self.assertEqual(top_level_definitions, ["OfferGraph"])

    def test_store_exposes_semantic_catalog_queries_only(self) -> None:
        from flights_cli.store import Store

        self.assertFalse(hasattr(Store, "load_json"))


if __name__ == "__main__":
    unittest.main()
