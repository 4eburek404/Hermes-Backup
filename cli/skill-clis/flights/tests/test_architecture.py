from __future__ import annotations

import ast
import tomllib
import unittest

from flights_cli import __version__

from helpers import PROJECT


class ArchitectureTests(unittest.TestCase):
    def test_pyproject_version_matches_runtime_version(self) -> None:
        data = tomllib.loads((PROJECT / "pyproject.toml").read_text())
        self.assertEqual(data["project"]["version"], __version__)

    def test_module_dependency_boundaries(self) -> None:
        root = PROJECT / "flights_cli"
        modules = {".".join(path.relative_to(PROJECT).with_suffix("").parts): path for path in root.rglob("*.py")}
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
                        base = module.split(".")[:-node.level]
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
                    cycles.append(visiting[visiting.index(target):] + [target])
            visiting.pop()

        for module in modules:
            if module not in visited:
                visit(module)

        forbidden_provider_edges = [
            (source, target)
            for source, targets in edges.items()
            for target in targets
            if source.startswith("flights_cli.providers.") and target.startswith(("flights_cli.cli", "flights_cli.commands."))
        ]
        forbidden_output_edges = [
            (source, target)
            for source, targets in edges.items()
            for target in targets
            if source == "flights_cli.output" and target.startswith(("flights_cli.providers.", "flights_cli.orchestrators.", "flights_cli.commands."))
        ]

        self.assertEqual(cycles, [])
        self.assertEqual(forbidden_provider_edges, [])
        self.assertEqual(forbidden_output_edges, [])


if __name__ == "__main__":
    unittest.main()
