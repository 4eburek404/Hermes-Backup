"""Поведенческий контракт CLI.

Страховка для резки: фиксирует то, что обязано пережить переписывание, и
намеренно не фиксирует форматирование, язык и прозу — их чинит отдельный шаг.
Проверки архитектуры сделаны по структурным фактам (реестры, импорты, схемы),
без сканирования исходников текстом.
"""

from __future__ import annotations

import ast
import unittest
from datetime import timedelta
from pathlib import Path

from flights_cli.adapters.providers.registry import PROVIDER_REGISTRY
from flights_cli.contracts.registry import CURRENT_CONTRACTS
from flights_cli.domain.offer_paths import offer_segment_paths
from flights_cli.errors import CliError
from flights_cli.execution.failure_classifier import classify_failure
from flights_cli.pipeline.offer_graph_merge import dedupe_candidates
from flights_cli.pipeline.search_request import (
    normalize_search_request_payload,
    search_request_from_payload,
)
from flights_cli.store import Store
from flights_cli.version_manifest import load_version_manifest, manifest_mismatches

from helpers import build_search_plan, future_departure_date

PROJECT = Path(__file__).resolve().parents[1]


def _segment(flight: str, origin: str, destination: str, dep: str, arr: str) -> dict:
    return {
        "flight_number": flight,
        "carrier": flight[:2],
        "origin": origin,
        "destination": destination,
        "departure_at": dep,
        "arrival_at": arr,
    }


def _candidate(provider: str, flight: str, dep: str, arr: str) -> dict:
    return {
        "id": f"candidate:{provider}:{flight}",
        "source_providers": [provider],
        "journeys": [
            {
                "direction": "outbound",
                "segments": [_segment(flight, "SVX", "SVO", dep, arr)],
            }
        ],
    }


class RequestBoundary(unittest.TestCase):
    """Что CLI обязан принимать и что обязан отвергать."""

    def _request(self, **overrides) -> dict:
        depart = future_departure_date()
        payload = {
            "origin": "SVX",
            "destination": "SVO",
            "depart_date": depart.isoformat(),
        }
        payload.update(overrides)
        return payload

    def test_request_of_three_fields_is_accepted(self) -> None:
        """SKILL.md требует больше полей, чем код. Принимаемый минимум — три."""
        normalized = normalize_search_request_payload(self._request())
        self.assertEqual(normalized["origin"], "SVX")
        self.assertEqual(normalized["destination"], "SVO")
        self.assertTrue(str(normalized["schema_version"]).startswith("flight_search_request."))

    def test_three_field_request_produces_provider_queries(self) -> None:
        """Минимальный запрос доходит до плана и порождает вызовы провайдеров."""
        request = search_request_from_payload(self._request())
        plan = build_search_plan(request, Store())
        attempts = plan["phases"]["primary"]
        self.assertTrue(attempts, "план обязан содержать хотя бы одну пробу")
        providers = {str(a["provider"]) for a in attempts}
        self.assertTrue(providers <= set(PROVIDER_REGISTRY))

    def test_past_departure_is_rejected(self) -> None:
        past = future_departure_date() - timedelta(days=30)
        with self.assertRaises(CliError):
            search_request_from_payload(self._request(depart_date=past.isoformat()))

    def test_return_before_departure_is_rejected(self) -> None:
        depart = future_departure_date()
        with self.assertRaises(CliError):
            search_request_from_payload(
                self._request(return_date=(depart - timedelta(days=1)).isoformat())
            )


class OfferInvariants(unittest.TestCase):
    """Роли, которые обязаны пережить резку независимо от того, где будут жить."""

    def test_same_physical_flight_from_two_providers_becomes_one_option(self) -> None:
        """Межпровайдерная дедупликация: иначе рейс попадёт в ответ дважды."""
        dep, arr = "2026-10-29T06:00:00+05:00", "2026-10-29T06:40:00+03:00"
        deduped, count = dedupe_candidates(
            [_candidate("tutu", "SU1400", dep, arr), _candidate("kupibilet", "SU1400", dep, arr)]
        )
        self.assertEqual(len(deduped), 1)
        self.assertEqual(count, 1)
        self.assertEqual(
            set(deduped[0].get("source_providers") or []), {"tutu", "kupibilet"}
        )

    def test_different_flights_are_not_merged(self) -> None:
        deduped, count = dedupe_candidates(
            [
                _candidate("tutu", "SU1400", "2026-10-29T06:00:00+05:00", "2026-10-29T06:40:00+03:00"),
                _candidate("tutu", "SU1402", "2026-10-29T09:00:00+05:00", "2026-10-29T09:40:00+03:00"),
            ]
        )
        self.assertEqual(len(deduped), 2)
        self.assertEqual(count, 0)

    def test_provider_round_trip_offer_exposes_both_legs(self) -> None:
        """Обратное плечо живёт в journeys, не в плоском segments."""
        offer = {
            "journeys": [
                {"direction": "outbound", "segments": [_segment("SU1403", "SVX", "SVO", "2026-10-29T19:05:00+05:00", "2026-10-29T19:40:00+03:00")]},
                {"direction": "return", "segments": [_segment("SU1414", "SVO", "SVX", "2026-11-05T17:50:00+03:00", "2026-11-05T22:10:00+05:00")]},
            ],
            "segments": [_segment("SU1403", "SVX", "SVO", "2026-10-29T19:05:00+05:00", "2026-10-29T19:40:00+03:00")],
        }
        paths = offer_segment_paths(offer, fallback_direction=None)
        self.assertEqual([p["direction"] for p in paths], ["outbound", "return"])
        self.assertEqual(paths[1]["segments"][0]["destination"], "SVX")

    def test_provider_failure_is_classified_not_swallowed(self) -> None:
        """Отказ провайдера обязан остаться отказом, а не стать «рейсов нет»."""
        for message, expected in (
            ("HTTP 429 Too Many Requests", "rate_limited"),
            ("connection refused", "provider_unavailable"),
            ("read timeout", "timeout"),
        ):
            with self.subTest(message=message):
                result = classify_failure("error", message)
                self.assertEqual(result["classification"], expected)
                self.assertIn("retryable", result)


class StructuralFacts(unittest.TestCase):
    """Перенесено из храповика: те же гарантии, но по фактам, а не по тексту."""

    def test_provider_registry_is_exactly_two_providers(self) -> None:
        self.assertEqual(set(PROVIDER_REGISTRY), {"tutu", "kupibilet"})

    def test_package_has_no_import_cycles(self) -> None:
        root = PROJECT / "flights_cli"
        graph: dict[str, set[str]] = {}
        for path in root.rglob("*.py"):
            name = path.relative_to(PROJECT).with_suffix("").as_posix().replace("/", ".")
            if name.endswith(".__init__"):
                name = name[: -len(".__init__")]
            pkg = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
            deps: set[str] = set()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level:
                    base = pkg.split(".")
                    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    target = ".".join(base) + (f".{node.module}" if node.module else "")
                    deps.add(target)
            graph[name] = deps
        colour: dict[str, int] = {}
        cycles: list[str] = []

        def visit(node: str, trail: list[str]) -> None:
            if colour.get(node) == 2:
                return
            if colour.get(node) == 1:
                cycles.append(" → ".join(trail[trail.index(node):] + [node]))
                return
            colour[node] = 1
            for dep in sorted(graph.get(node, ())):
                if dep in graph:
                    visit(dep, trail + [dep])
            colour[node] = 2

        for node in sorted(graph):
            visit(node, [node])
        self.assertEqual(cycles, [], f"обнаружены циклы импорта: {cycles}")

    def test_layer_dependencies_point_one_way(self) -> None:
        """Слои не разворачиваются: перенесено из храповика, но по графу импортов."""
        layers = (
            "domain", "providers", "adapters", "ports", "pipeline",
            "execution", "reporting", "orchestrators", "contracts", "commands",
        )
        rules = {
            "domain": ("execution", "reporting", "orchestrators", "commands"),
            "reporting": ("orchestrators", "execution", "commands"),
            "execution": ("reporting", "commands", "orchestrators"),
            "providers": ("pipeline", "execution", "reporting", "orchestrators", "commands"),
            "adapters": ("pipeline", "orchestrators", "reporting", "commands"),
            "contracts": ("pipeline", "execution", "orchestrators", "commands"),
        }

        def layer_of(module: str) -> str:
            parts = module.split(".")
            return parts[1] if len(parts) > 1 and parts[1] in layers else "_root"

        edges: dict[str, set[str]] = {}
        root = PROJECT / "flights_cli"
        for path in root.rglob("*.py"):
            name = path.relative_to(PROJECT).with_suffix("").as_posix().replace("/", ".")
            if name.endswith(".__init__"):
                name = name[: -len(".__init__")]
            pkg = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level:
                    base = pkg.split(".")
                    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    target = ".".join(base) + (f".{node.module}" if node.module else "")
                    source, sink = layer_of(name), layer_of(target)
                    if source != sink:
                        edges.setdefault(source, set()).add(sink)

        for source, forbidden in rules.items():
            with self.subTest(layer=source):
                self.assertEqual(
                    sorted(edges.get(source, set()) & set(forbidden)),
                    [],
                    f"слой {source} не должен импортировать {forbidden}",
                )

    def test_version_manifest_agrees_with_contract_registry(self) -> None:
        manifest = load_version_manifest()
        self.assertTrue(manifest, "манифест версий обязан существовать")
        self.assertEqual(manifest_mismatches(manifest), [])
        for name in ("search_request", "search_result", "user_answer"):
            self.assertIn(name, CURRENT_CONTRACTS)


if __name__ == "__main__":
    unittest.main()
