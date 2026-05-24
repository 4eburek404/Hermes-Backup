from __future__ import annotations

import ast
import re
import tomllib
import unittest

from flights_cli import __skill_version__, __version__

from helpers import PROJECT


class ArchitectureTests(unittest.TestCase):
    def test_pyproject_version_matches_runtime_version(self) -> None:
        data = tomllib.loads((PROJECT / "pyproject.toml").read_text())
        self.assertEqual(data["project"]["version"], __version__)

    def test_skill_version_matches_runtime_version(self) -> None:
        skill = PROJECT.parent / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        match = re.search(r"^version: (.+)$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __skill_version__)

    def test_skill_markdown_formatting_is_sane(self) -> None:
        skill = PROJECT.parent / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("\n---\n", text[3:])
        self.assertIn("\n# Flight Search\n", text)
        self.assertGreater(text.count("\n"), 40)

    def test_active_markdown_prompt_surface_is_clean(self) -> None:
        forbidden = [
            "Aviasales",
            "aviasales",
            "price-search",
            "price search",
            "cached price",
            "cached price probes",
            "request search",
            "prices-for-dates",
            "grouped-prices",
            "results parse",
            "aviasales.ru/search",
            "legacy late sanity layer",
            "manual Aviasales links",
            "Travelpayouts cached price data",
        ]
        hits = []
        for path in PROJECT.parent.rglob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                for token in forbidden:
                    if token in line:
                        hits.append((path.relative_to(PROJECT.parent), line_number, token, line.strip()))
        self.assertEqual(hits, [])

    def test_provider_aware_airport_priority_docs_capture_durable_rules(self) -> None:
        reference = PROJECT.parent / "references" / "provider-aware-airport-priority.md"
        self.assertTrue(reference.exists())
        text = reference.read_text(encoding="utf-8")
        for required in [
            "The active provider set is closed to KupiBilet and FLI.",
            "IST means the exact airport code `IST`; do not add `SAW` unless the user explicitly requests `SAW`.",
            "LHR first; `LGW` fallback only if `LHR` has no accepted/viable offers; `STN` and `LTN` excluded by default.",
            "KupiBilet uses `MOW` city-code first.",
            "Exact `SVO`/`DME`/`VKO` fallback is deferred and not executed in parallel when city-code results have accepted offers.",
            "Actual airports must be post-validated against `SVO`/`DME`/`VKO` and displayed as actual airport codes, not only `MOW`.",
            "FLI is exact-airport only and must not receive `LON` city-code queries by default.",
            "successful `SVX→MOW` skips exact fallback calls to `SVX→SVO`, `SVX→DME`, and `SVX→VKO`;",
            "successful `IST→LHR` skips fallback calls to `IST→LGW`;",
            "`SAW`, `STN`, and `LTN` are absent from default generated plans and provider calls.",
            "`direct_destination_control` is a search branch, not a nonstop claim.",
            "Semantic validation must use structured fields, not only `answer_lines`.",
            "Source/runtime sync and validation rules live in `references/cli-maintenance.md`;",
        ]:
            self.assertIn(required, text)

        for doc in [
            PROJECT.parent / "references" / "cli-maintenance.md",
            PROJECT.parent / "references" / "report-contract.md",
            PROJECT / "README.md",
        ]:
            self.assertIn("provider-aware-airport-priority.md", doc.read_text(encoding="utf-8"))

    def test_readme_keeps_supporting_file_distillation_policy(self) -> None:
        readme = PROJECT / "README.md"
        text = readme.read_text(encoding="utf-8")
        self.assertIn(
            "Do not delete supporting Markdown files merely because they contain obsolete provider names, dated route examples, or migration history.",
            text,
        )
        self.assertIn("Move those distilled rules into the appropriate active document or test.", text)

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
