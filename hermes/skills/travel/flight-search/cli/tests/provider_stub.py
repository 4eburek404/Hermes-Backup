"""Офлайн-провайдер для тестов: MCP-стаб Tutu и запуск CLI против него.

Вынесен из test_offline_cli_e2e, чтобы поведенческий контракт мог проверять
поведение на границе CLI, не импортируя ни планировщик, ни Store — то есть
не завися от модулей, которые резка удаляет.
"""

from __future__ import annotations

from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
CATALOG_FIXTURES = PROJECT / "tests" / "fixtures" / "catalog"


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
    def __init__(self, depart: date) -> None:
        self.depart = depart
        self.tool_queries: list[tuple[str, str, str, bool]] = []
        self.method_counts: Counter[str] = Counter()
        self.method_order: list[str] = []
        self.session_method_order: dict[str, list[str]] = {}
        self.protocol_versions: list[str] = []
        self._session_counter = 0
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def send_json(self, status: int, payload: dict | None = None) -> None:
                body = (
                    json.dumps(payload).encode("utf-8") if payload is not None else b""
                )
                self.send_response(status)
                if payload is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                size = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(size) or b"{}")
                method = str(request.get("method") or "")
                with owner._lock:
                    owner.method_counts[method] += 1
                    owner.method_order.append(method)
                    request_session = str(self.headers.get("Mcp-Session-Id") or "")
                    if request_session:
                        owner.session_method_order.setdefault(
                            request_session, []
                        ).append(method)
                if method == "server/discover":
                    self.send_json(
                        400,
                        {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            "error": {"code": -32601, "message": "discover forbidden"},
                        },
                    )
                    return
                response: dict = {"jsonrpc": "2.0", "id": request.get("id")}
                if method == "initialize":
                    with owner._lock:
                        owner._session_counter += 1
                        session_id = f"test-session-{owner._session_counter}"
                        owner.session_method_order[session_id] = ["initialize"]
                    response["result"] = {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "tutu-mcp-server", "version": "1"},
                    }
                    body = json.dumps(response).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Mcp-Session-Id", session_id)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if method == "notifications/initialized":
                    owner.protocol_versions.append(
                        str(self.headers.get("MCP-Protocol-Version") or "")
                    )
                    self.send_json(202)
                    return
                if method == "tools/list":
                    response["result"] = {
                        "tools": [
                            {
                                "name": "get_avia_instructions",
                                "description": "Return the Tutu flight-search playbook.",
                                "inputSchema": {"type": "object"},
                            },
                            {
                                "name": "search_avia",
                                "description": "Search Tutu flight offers.",
                                "inputSchema": {"type": "object"},
                            },
                        ]
                    }
                elif method == "tools/call":
                    tool_name = request["params"]["name"]
                    if tool_name == "get_avia_instructions":
                        response["result"] = {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "# Test Tutu playbook\nUse search_avia.",
                                }
                            ]
                        }
                        self.send_json(200, response)
                        return
                    self.assert_search_tool(tool_name)
                    arguments = request["params"]["arguments"]
                    origin = str(arguments.get("origin") or "").upper()
                    destination = str(arguments.get("destination") or "").upper()
                    date = str(arguments.get("departure_date") or "")
                    owner.tool_queries.append(
                        (origin, destination, date, bool(arguments.get("direct_only")))
                    )
                    payload = owner.search_payload(origin, destination)
                    response["result"] = {
                        "content": [{"type": "text", "text": json.dumps(payload)}]
                    }
                else:
                    response["result"] = {}
                self.send_json(200, response)

            def assert_search_tool(self, tool_name: str) -> None:
                if tool_name != "search_avia":
                    raise AssertionError(f"unexpected MCP tool: {tool_name}")

            def do_DELETE(self) -> None:  # noqa: N802
                self.send_json(200, {})

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

    def search_payload(self, origin: str, destination: str) -> dict:
        depart_text = self.depart.isoformat()
        next_day_text = (self.depart + timedelta(days=1)).isoformat()
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
                                    f"{depart_text}T06:05:00+02:00",
                                    f"{depart_text}T07:45:00+02:00",
                                    100,
                                ),
                                segment(
                                    "AMS",
                                    "IST",
                                    "KL1959",
                                    f"{depart_text}T11:35:00+02:00",
                                    f"{depart_text}T16:05:00+03:00",
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
                                    f"{depart_text}T20:00:00+03:00",
                                    f"{next_day_text}T02:45:00+05:00",
                                    285,
                                )
                            ]
                        }
                    ],
                }
            ]
        return {"offers": offers, "meta": {"has_more": False}}


class ConnectingInventoryStub(TutuStub):
    """Провайдер отдаёт собственный стыковочный оффер NTE→AMS→SVX.

    Стыковка приходит внутри одного провайдерского оффера, а не склеивается
    планировщиком через шлюз, — поэтому сценарий переживает резку хабового слоя.
    """

    def search_payload(self, origin: str, destination: str) -> dict:
        if (origin, destination) != ("NTE", "SVX"):
            return {"offers": [], "meta": {"has_more": False}}
        depart = self.depart.isoformat()
        return {
            "offers": [
                {
                    "offer_id": "nte-ams-svx",
                    "price": {"amount": 24300, "currency": "RUB"},
                    "duration_min": 555,
                    "legs": [
                        {
                            "segments": [
                                segment(
                                    "NTE",
                                    "AMS",
                                    "KL-1424",  # провайдер пишет с дефисом
                                    f"{depart}T06:05:00+02:00",
                                    f"{depart}T07:45:00+02:00",
                                    100,
                                ),
                                segment(
                                    "AMS",
                                    "SVX",
                                    "KL1395",
                                    f"{depart}T11:35:00+02:00",
                                    f"{depart}T18:20:00+05:00",
                                    345,
                                ),
                            ]
                        }
                    ],
                }
            ],
            "meta": {"has_more": False},
        }


def minutes_between(earlier: str, later: str) -> int:
    delta = datetime.fromisoformat(later) - datetime.fromisoformat(earlier)
    return round(delta.total_seconds() / 60)


def run_search_cli(
    request_payload: dict[str, Any],
    *,
    stub_url: str,
    work_dir: Path,
    json_output: bool = True,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    """Прогнать `flights search` в отдельном процессе против стаба.

    Это единственный шов, который переживает резку: тест говорит с CLI, а не с
    планировщиком, поэтому переписывание внутренностей его не ломает.
    """

    policy = str(request_payload.get("provider_policy") or "")
    if policy != "tutu":
        raise AssertionError(
            "подпроцесс CLI не под сетевым замком из conftest: стабится только Tutu, "
            "поэтому в запросе обязан стоять provider_policy=tutu"
        )
    cache = work_dir / "cache"
    if not cache.exists():
        shutil.copytree(CATALOG_FIXTURES, cache)
    request_path = work_dir / "request.json"
    request_path.write_text(json.dumps(request_payload), encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "flights_cli",
        "--catalog-refresh",
        "never",
        "search",
        "--request",
        str(request_path),
    ]
    if json_output:
        command.append("--json")
    return subprocess.run(
        command,
        cwd=PROJECT,
        env={
            **os.environ,
            "FLIGHTS_TUTU_MCP_URL": stub_url,
            "FLIGHTS_CACHE_DIR": str(cache),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
