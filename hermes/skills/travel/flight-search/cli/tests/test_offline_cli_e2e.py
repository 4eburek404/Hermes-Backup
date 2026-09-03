from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import future_departure_date
from provider_stub import CATALOG_FIXTURES, ConnectingInventoryStub


class OfflineCliE2ETests(unittest.TestCase):
    def test_real_subprocess_uses_each_logical_query_once_and_renders_same_text(
        self,
    ) -> None:
        depart = future_departure_date()
        stub = ConnectingInventoryStub(depart)
        stub.start()
        self.addCleanup(stub.close)
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache = root / "cache"
            shutil.copytree(CATALOG_FIXTURES, cache)
            request_path = root / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "schema_version": "flight_search_request.v1",
                        "origin": "NTE",
                        "destination": "SVX",
                        "depart_date": depart.isoformat(),
                        "return_date": None,
                        "currency": "RUB",
                        "provider_policy": "tutu",
                    }
                ),
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "FLIGHTS_TUTU_MCP_URL": stub.url,
                "FLIGHTS_CACHE_DIR": str(cache),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            base = [
                sys.executable,
                "-m",
                "flights_cli",
                "--catalog-refresh",
                "never",
                "search",
                "--request",
                str(request_path),
                # Бюджеты прогона — ключи, а не поля запроса.
                "--max-searches",
                "20",
                "--timeout",
                "10",
                "--no-live-cache",
            ]
            text_proc = subprocess.run(
                base,
                cwd=Path(__file__).parent.parent,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            text_queries = Counter(stub.tool_queries)
            text_methods = Counter(stub.method_counts)
            text_protocol_versions = list(stub.protocol_versions)
            text_session_orders = list(stub.session_method_order.values())
            stub.tool_queries.clear()
            stub.method_counts.clear()
            stub.method_order.clear()
            stub.protocol_versions.clear()
            stub.session_method_order.clear()
            json_proc = subprocess.run(
                [*base, "--json"],
                cwd=Path(__file__).parent.parent,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            json_queries = Counter(stub.tool_queries)
            json_methods = Counter(stub.method_counts)
            json_protocol_versions = list(stub.protocol_versions)
            json_session_orders = list(stub.session_method_order.values())

        self.assertEqual(text_proc.returncode, 0, text_proc.stderr)
        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        self.assertEqual(text_proc.stderr, "")
        self.assertEqual(json_proc.stderr, "")
        self.assertTrue(text_queries)
        self.assertTrue(all(count == 1 for count in text_queries.values()))
        self.assertEqual(text_queries, json_queries)
        for methods, protocols, queries, session_orders in (
            (text_methods, text_protocol_versions, text_queries, text_session_orders),
            (json_methods, json_protocol_versions, json_queries, json_session_orders),
        ):
            self.assertEqual(methods["server/discover"], 0)
            self.assertEqual(methods["initialize"], len(queries))
            self.assertEqual(methods["notifications/initialized"], len(queries))
            self.assertEqual(methods["tools/call"], len(queries) * 2)
            self.assertEqual(protocols, ["2025-11-25"] * len(queries))
            self.assertEqual(len(session_orders), len(queries))
            for order in session_orders:
                self.assertEqual(
                    order,
                    [
                        "initialize",
                        "notifications/initialized",
                        "tools/call",
                        "tools/list",
                        "tools/call",
                    ],
                )
        envelope = json.loads(json_proc.stdout)
        result = envelope["data"]
        self.assertEqual(result["schema_version"], "flight_search_result.v1")
        self.assertEqual(text_proc.stdout, result["rendered_text"] + "\n")
        self.assertIn("KL1424", text_proc.stdout)
        self.assertIn("KL1395", text_proc.stdout)
        self.assertEqual(
            text_proc.stdout,
            f"""Нашёл варианты NTE→SVX.
1. KL1424 {depart:%d.%m} NTE-(AMS) 0605 0745 в пути 1 ч 40 мин
    пересадка 3 ч 50 мин
   KL1395 {depart:%d.%m} (AMS)-(SVX) 1135 1820 в пути 3 ч 45 мин
    24 300 ₽

Перед оплатой проверьте багаж, финальный тариф и правила обмена/возврата; результат не доказывает варианты вне границ источников.
""",
        )


if __name__ == "__main__":
    unittest.main()
