from __future__ import annotations

from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest


CATALOG_FIXTURES = Path(__file__).parent / "fixtures" / "catalog"


def segment(
    origin: str,
    destination: str,
    flight_number: str,
    departure_at: str,
    arrival_at: str,
    duration_min: int,
) -> dict:
    return {
        "from": f"Airport ({origin})",
        "to": f"Airport ({destination})",
        "carrier": "KL" if flight_number.startswith("KL") else "TK",
        "voyage_no": flight_number,
        "departure_at": departure_at,
        "arrival_at": arrival_at,
        "duration_min": duration_min,
    }


class TutuStub:
    def __init__(self) -> None:
        self.tool_queries: list[tuple[str, str, str]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                size = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(size) or b"{}")
                method = request.get("method")
                response: dict = {"jsonrpc": "2.0", "id": request.get("id")}
                if method == "initialize":
                    response["result"] = {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "serverInfo": {"name": "test-tutu", "version": "1"},
                    }
                elif method == "tools/call":
                    arguments = request["params"]["arguments"]
                    origin = str(arguments.get("origin") or "").upper()
                    destination = str(arguments.get("destination") or "").upper()
                    date = str(arguments.get("departure_date") or "")
                    owner.tool_queries.append((origin, destination, date))
                    payload = owner.search_payload(origin, destination)
                    response["result"] = {
                        "content": [{"type": "text", "text": json.dumps(payload)}]
                    }
                else:
                    response["result"] = {}
                body = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/mcp"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    @staticmethod
    def search_payload(origin: str, destination: str) -> dict:
        offers: list[dict] = []
        if (origin, destination) == ("NTE", "IST"):
            offers = [
                {
                    "offer_id": "nte-ams-ist",
                    "price": {"amount": 18500, "currency": "RUB"},
                    "duration_min": 505,
                    "legs": [
                        {
                            "segments": [
                                segment(
                                    "NTE",
                                    "AMS",
                                    "KL1424",
                                    "2026-07-23T06:05:00+02:00",
                                    "2026-07-23T07:45:00+02:00",
                                    100,
                                ),
                                segment(
                                    "AMS",
                                    "IST",
                                    "KL1959",
                                    "2026-07-23T11:35:00+02:00",
                                    "2026-07-23T16:05:00+03:00",
                                    210,
                                ),
                            ]
                        }
                    ],
                }
            ]
        elif (origin, destination) == ("IST", "SVX"):
            offers = [
                {
                    "offer_id": "ist-svx",
                    "price": {"amount": 21500, "currency": "RUB"},
                    "duration_min": 285,
                    "legs": [
                        {
                            "segments": [
                                segment(
                                    "IST",
                                    "SVX",
                                    "TK475",
                                    "2026-07-23T20:00:00+03:00",
                                    "2026-07-24T02:45:00+05:00",
                                    285,
                                )
                            ]
                        }
                    ],
                }
            ]
        return {"offers": offers, "meta": {"has_more": False}}


class OfflineCliE2ETests(unittest.TestCase):
    def test_real_subprocess_uses_each_logical_query_once_and_renders_same_text(
        self,
    ) -> None:
        stub = TutuStub()
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
                        "depart_date": "2026-07-23",
                        "return_date": None,
                        "currency": "RUB",
                        "profile": "business",
                        "ticketing": "separate",
                        "provider_policy": "tutu",
                        "route_options": {
                            "routing_strategy": "hub-list",
                            "hubs": ["IST"],
                            "gateway_discovery_limit": 1,
                            "gateway_probe_batch_size": 1,
                            "gateway_probe_max_batches": 1,
                        },
                        "evidence": {
                            "aggregate_control_limit": 0,
                            "max_segment_searches": 20,
                            "search_wave_max_waves": 1,
                            "search_wave_probe_limit": 10,
                            "no_live_cache": True,
                            "live_cache_ttl_seconds": 0,
                            "timeout": 10,
                        },
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
            stub.tool_queries.clear()
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

        self.assertEqual(text_proc.returncode, 0, text_proc.stderr)
        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        self.assertEqual(text_proc.stderr, "")
        self.assertEqual(json_proc.stderr, "")
        self.assertTrue(text_queries)
        self.assertTrue(all(count == 1 for count in text_queries.values()))
        self.assertEqual(text_queries, json_queries)
        envelope = json.loads(json_proc.stdout)
        result = envelope["data"]
        self.assertEqual(result["schema_version"], "flight_search_result.v7")
        self.assertEqual(text_proc.stdout, result["answer"]["rendered_text"] + "\n")
        self.assertIn("KL1424", text_proc.stdout)
        self.assertIn("KL1959", text_proc.stdout)
        self.assertEqual(
            text_proc.stdout,
            """Нашёл варианты NTE→SVX.
1. KL1424 23.07 NTE-(AMS) 0605 0745 в пути 1:40
    пересадка 3ч 50мин
   KL1959 23.07 (AMS)-(IST) 1135 1605 в пути 3:30
    пересадка 3ч 55мин
   TK475 23.07 (IST)-(SVX) 2000 0245 (24.07) в пути 4:45
    40 000 рублей · Отдельные билеты: при задержке первого рейса следующий сегмент не защищён.

Перед оплатой проверьте багаж, финальный тариф и правила обмена/возврата; результат не доказывает варианты вне границ источников.
""",
        )


if __name__ == "__main__":
    unittest.main()
