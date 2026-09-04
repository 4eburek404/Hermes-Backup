"""Поведенческий контракт CLI.

Страховка для резки: фиксирует то, что обязано пережить переписывание, и
намеренно не фиксирует форматирование, язык и прозу — их чинит отдельный шаг.
Проверки архитектуры сделаны по структурным фактам (реестры, импорты, схемы),
без сканирования исходников текстом.
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from datetime import date, timedelta
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
from flights_cli.version_manifest import load_version_manifest, manifest_mismatches

from provider_stub import (
    ConnectingInventoryStub,
    RoundTripInventoryStub,
    minutes_between,
    run_search_cli,
)

PROJECT = Path(__file__).resolve().parents[1]


def future_departure_date() -> date:
    """Локальная копия: сеть не должна зависеть от helpers, который тянет Store."""

    return date.today() + timedelta(days=3)


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
        """Принимаемый минимум — три поля; версию схемы дописывает нормализация."""
        normalized = normalize_search_request_payload(self._request())
        self.assertEqual(normalized["origin"], "SVX")
        self.assertEqual(normalized["destination"], "SVO")
        self.assertTrue(
            str(normalized["schema_version"]).startswith("flight_search_request.")
        )

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


class AnswerComposition(unittest.TestCase):
    """Что обязано доехать до ответа, когда провайдер вернул стыковочный оффер.

    Один прогон CLI на класс, против локального стаба. Тест говорит с границей
    команды, а не с планировщиком: переписывание внутренностей его не ломает.
    """

    depart: date
    queries: list[tuple[str, str, str, bool]]
    result: dict

    @classmethod
    def setUpClass(cls) -> None:
        depart = future_departure_date()
        stub = ConnectingInventoryStub(depart)
        stub.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                proc = run_search_cli(
                    {
                        "origin": "NTE",
                        "destination": "SVX",
                        "depart_date": depart.isoformat(),
                        "provider_policy": "tutu",
                    },
                    stub_url=stub.url,
                    work_dir=Path(tmp),
                )
            cls.queries = list(stub.tool_queries)
        finally:
            stub.close()
        if proc.returncode != 0:
            raise AssertionError(f"CLI не отработал: {proc.stderr}")
        cls.depart = depart
        cls.result = json.loads(proc.stdout)["data"]

    # Читатели контракта .v1: варианты лежат в result["options"], цена —
    # в option["price"], стыковки — в плече, и только там.

    @classmethod
    def options(cls) -> list[dict]:
        return list(cls.result["options"])

    @staticmethod
    def leg(option: dict, direction: str = "outbound") -> dict:
        return option["directions"].get(direction) or {}

    def test_minimal_request_reaches_provider_queries(self) -> None:
        """Запрос без ритуала доезжает до провайдерских вызовов.

        Обязательный минимум — три поля; provider_policy пришпилен четвёртым
        только потому, что по URL стабится один провайдер, а подпроцесс CLI
        сетевой замок из conftest не покрывает.
        """

        asked = {
            (origin, destination, day) for origin, destination, day, _ in self.queries
        }
        self.assertIn(("NTE", "SVX", self.depart.isoformat()), asked)

    def test_provider_offer_reaches_the_answer_whole(self) -> None:
        """Цена и оба сегмента приезжают от провайдера без потерь."""
        options = self.options()
        self.assertEqual(len(options), 1)
        price = options[0]["price"]
        self.assertEqual(price["amount"], 24300)
        self.assertEqual(price["currency"], "RUB")
        segments = self.leg(options[0])["segments"]
        self.assertEqual([s["flight_number"] for s in segments], ["KL1424", "KL1395"])

    def test_flight_numbers_have_one_spelling(self) -> None:
        """Дефис от провайдера не доезжает до ответа.

        Tutu пишет SU-1400, Kupibilet SU1400, и один рейс приезжал в двух
        написаниях. Канон совпадает с формой, которую ждёт схема .v1.
        """

        numbers = [
            segment["flight_number"]
            for option in self.options()
            for direction in ("outbound", "return")
            for segment in (self.leg(option, direction).get("segments") or [])
        ]
        self.assertTrue(numbers)
        for number in numbers:
            with self.subTest(flight_number=number):
                self.assertRegex(number, r"^[A-Z0-9]{2}[0-9]{1,4}$")

    def test_every_connection_is_measured_and_graded(self) -> None:
        """Стыковка обязана быть посчитана, а не подменена дефолтом.

        Когда производитель оценки уедет вместе с хабовым слоем, поле не
        исчезнет: приедет `comfort: unknown`, схема останется валидной, а
        текст ответа не изменится. Тест ловит именно эту подмену — он сверяет
        запись стыковки с промежутком, выведенным из времён сегментов.

        Записей стало одна вместо двух: `.v1` описывает пересадку один раз,
        и разойтись между собой им больше негде.
        """

        option = self.options()[0]
        leg = self.leg(option)
        segments = leg["segments"]
        expected = [
            (
                first["destination"],
                minutes_between(first["arrival_at"], second["departure_at"]),
            )
            for first, second in zip(segments, segments[1:])
        ]
        self.assertTrue(expected, "сценарий обязан содержать стыковку")

        connections = list(leg.get("connections") or [])
        self.assertEqual([(x["airport"], x["minutes"]) for x in connections], expected)
        for connection in connections:
            self.assertNotIn(connection.get("comfort"), (None, "", "unknown"))
            self.assertIsInstance(connection.get("required_min"), int)


class OfferInvariants(unittest.TestCase):
    """Роли, которые обязаны пережить резку независимо от того, где будут жить."""

    def test_same_physical_flight_from_two_providers_becomes_one_option(self) -> None:
        """Межпровайдерная дедупликация: иначе рейс попадёт в ответ дважды."""
        dep, arr = "2026-10-29T06:00:00+05:00", "2026-10-29T06:40:00+03:00"
        deduped = dedupe_candidates(
            [
                _candidate("tutu", "SU1400", dep, arr),
                _candidate("kupibilet", "SU1400", dep, arr),
            ]
        )
        self.assertEqual(len(deduped), 1)
        self.assertEqual(
            set(deduped[0].get("source_providers") or []), {"tutu", "kupibilet"}
        )

    def test_different_flights_are_not_merged(self) -> None:
        deduped = dedupe_candidates(
            [
                _candidate(
                    "tutu",
                    "SU1400",
                    "2026-10-29T06:00:00+05:00",
                    "2026-10-29T06:40:00+03:00",
                ),
                _candidate(
                    "tutu",
                    "SU1402",
                    "2026-10-29T09:00:00+05:00",
                    "2026-10-29T09:40:00+03:00",
                ),
            ]
        )
        self.assertEqual(len(deduped), 2)

    def test_provider_round_trip_offer_exposes_both_legs(self) -> None:
        """Обратное плечо живёт в journeys, не в плоском segments."""
        offer = {
            "journeys": [
                {
                    "direction": "outbound",
                    "segments": [
                        _segment(
                            "SU1403",
                            "SVX",
                            "SVO",
                            "2026-10-29T19:05:00+05:00",
                            "2026-10-29T19:40:00+03:00",
                        )
                    ],
                },
                {
                    "direction": "return",
                    "segments": [
                        _segment(
                            "SU1414",
                            "SVO",
                            "SVX",
                            "2026-11-05T17:50:00+03:00",
                            "2026-11-05T22:10:00+05:00",
                        )
                    ],
                },
            ],
            "segments": [
                _segment(
                    "SU1403",
                    "SVX",
                    "SVO",
                    "2026-10-29T19:05:00+05:00",
                    "2026-10-29T19:40:00+03:00",
                )
            ],
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
            name = (
                path.relative_to(PROJECT).with_suffix("").as_posix().replace("/", ".")
            )
            if name.endswith(".__init__"):
                name = name[: -len(".__init__")]
            pkg = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
            deps: set[str] = set()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level:
                    base = pkg.split(".")
                    base = (
                        base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    )
                    target = ".".join(base) + (f".{node.module}" if node.module else "")
                    deps.add(target)
            graph[name] = deps
        colour: dict[str, int] = {}
        cycles: list[str] = []

        def visit(node: str, trail: list[str]) -> None:
            if colour.get(node) == 2:
                return
            if colour.get(node) == 1:
                cycles.append(" → ".join(trail[trail.index(node) :] + [node]))
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
            "domain",
            "providers",
            "adapters",
            "ports",
            "pipeline",
            "execution",
            "reporting",
            "orchestrators",
            "contracts",
            "commands",
        )
        rules = {
            "domain": ("execution", "reporting", "orchestrators", "commands"),
            "reporting": ("orchestrators", "execution", "commands"),
            "execution": ("reporting", "commands", "orchestrators"),
            "providers": (
                "pipeline",
                "execution",
                "reporting",
                "orchestrators",
                "commands",
            ),
            "adapters": ("pipeline", "orchestrators", "reporting", "commands"),
            "contracts": ("pipeline", "execution", "orchestrators", "commands"),
        }

        def layer_of(module: str) -> str:
            parts = module.split(".")
            return parts[1] if len(parts) > 1 and parts[1] in layers else "_root"

        edges: dict[str, set[str]] = {}
        root = PROJECT / "flights_cli"
        for path in root.rglob("*.py"):
            name = (
                path.relative_to(PROJECT).with_suffix("").as_posix().replace("/", ".")
            )
            if name.endswith(".__init__"):
                name = name[: -len(".__init__")]
            pkg = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level:
                    base = pkg.split(".")
                    base = (
                        base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    )
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

    def test_text_layer_has_one_legitimate_consumer(self) -> None:
        """У слоя текста ровно один потребитель — сборщик ответа.

        Правило слоёв выше смотрит только межслойные рёбра, а главный разворот
        зависимостей был внутрислойным: проекция каталога клала русский текст в
        структурные поля. Список известного долга был пуст к .v1 и обязан
        таким остаться: текст больше не приезжает в данные.
        """

        renderer = "flights_cli.reporting.answer_text"
        assembler = "flights_cli.pipeline.result_builder"
        known_debt: set[str] = set()

        consumers: set[str] = set()
        root = PROJECT / "flights_cli"
        for path in root.rglob("*.py"):
            name = (
                path.relative_to(PROJECT).with_suffix("").as_posix().replace("/", ".")
            )
            if name.endswith(".__init__"):
                name = name[: -len(".__init__")]
            pkg = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                base = pkg.split(".")
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                target = ".".join(base) + (f".{node.module}" if node.module else "")
                if target == renderer and name != assembler:
                    consumers.add(name)

        self.assertLessEqual(
            consumers,
            known_debt,
            f"новый потребитель рендера: {sorted(consumers - known_debt)}",
        )

    def test_version_manifest_agrees_with_contract_registry(self) -> None:
        manifest = load_version_manifest()
        self.assertTrue(manifest, "манифест версий обязан существовать")
        self.assertEqual(manifest_mismatches(manifest), [])
        for name in ("search_request", "search_result"):
            self.assertIn(name, CURRENT_CONTRACTS)


class RoundTripComposition(unittest.TestCase):
    """Круговой запрос доезжает до ответа одним провайдерским вариантом.

    Это шов, который переживает резку синтеза пар: тест говорит с границей
    CLI и спрашивает, что видит путешественник, а не как собран план.
    """

    depart: date
    return_date: date
    return_dates: list[str | None]
    result: dict

    @classmethod
    def setUpClass(cls) -> None:
        depart = future_departure_date()
        back = depart + timedelta(days=7)
        stub = RoundTripInventoryStub(depart)
        stub.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                proc = run_search_cli(
                    {
                        "origin": "NTE",
                        "destination": "SVX",
                        "depart_date": depart.isoformat(),
                        "return_date": back.isoformat(),
                        "provider_policy": "tutu",
                    },
                    stub_url=stub.url,
                    work_dir=Path(tmp),
                )
            cls.return_dates = list(stub.return_dates)
        finally:
            stub.close()
        if proc.returncode != 0:
            raise AssertionError(f"CLI не отработал: {proc.stderr}")
        cls.depart = depart
        cls.return_date = back
        cls.result = json.loads(proc.stdout)["data"]

    def test_return_date_reaches_the_provider_once(self) -> None:
        """Обе даты уезжают одним запросом, а не двумя односторонними."""
        self.assertEqual(self.return_dates, [self.return_date.isoformat()])

    def test_round_trip_option_carries_both_legs_and_one_price(self) -> None:
        options = list(self.result["options"])
        self.assertEqual(len(options), 1)
        option = options[0]
        directions = option["directions"]
        self.assertEqual(set(directions), {"outbound", "return"})
        self.assertEqual(
            [s["flight_number"] for s in directions["outbound"]["segments"]],
            ["SU2401"],
        )
        self.assertEqual(
            [s["flight_number"] for s in directions["return"]["segments"]],
            ["SU2402"],
        )
        # Цена провайдерская и целая, а не сумма двух односторонних.
        self.assertEqual(option["price"]["amount"], 41200)

    def test_provider_round_trip_is_not_sold_as_separate_tickets(self) -> None:
        """Склейки нет — значит нет и оговорки про отдельные билеты."""
        option = list(self.result["options"])[0]
        self.assertEqual(option["ticketing"]["model"], "provider_order")
        self.assertNotIn("self_transfer", option["ticketing"])
        self.assertNotIn("self_transfer", option["warnings"])
        self.assertNotIn("Отдельные билеты", self.result["rendered_text"])

    def test_non_stop_round_trip_states_no_transfer_protection(self) -> None:
        """Туда и обратно — два рейса, но не стык.

        Плечи летят без пересадок и в разные дни: везти багаж насквозь
        негде и опаздывать не с чего. Раньше счёт рейсов целиком давал
        здесь 1 + 1 = 2 и включал оговорки про единый PNR и сквозной багаж.
        """
        option = list(self.result["options"])[0]
        for direction in ("outbound", "return"):
            self.assertEqual(len(option["directions"][direction]["segments"]), 1)

        self.assertEqual(option["ticketing"], {"model": "provider_order"})
        self.assertEqual(
            option["warnings"], ["baggage_unknown", "verify_on_booking_screen"]
        )


if __name__ == "__main__":
    unittest.main()
