"""Local HTTPS CONNECT guard: deny live Tutu, tunnel other model endpoints."""
from __future__ import annotations

import json
import select
import socket
import socketserver
import threading
from pathlib import Path
from typing import Any


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], owner: "TutuEgressGuard") -> None:
        self.owner = owner
        super().__init__(address, _ProxyHandler)


class _ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(15)
        header = bytearray()
        while b"\r\n\r\n" not in header and len(header) < 65536:
            block = client.recv(4096)
            if not block:
                return
            header.extend(block)
        first_line = bytes(header).split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        parts = first_line.split()
        if len(parts) < 2:
            self._reply(client, 400, b"Bad proxy request")
            return
        method, authority = parts[0].upper(), parts[1]
        host, port = self._authority(authority, 443 if method == "CONNECT" else 80)
        if host.lower().rstrip(".") == "mcp.tutu.ru":
            self.server.owner.record_blocked(host, method)
            self._reply(client, 403, b"Live Tutu access is disabled; use recorded replay")
            return
        if method != "CONNECT":
            self._reply(client, 405, b"Only CONNECT tunneling is supported")
            return
        try:
            upstream = socket.create_connection((host, port), timeout=20)
        except OSError:
            self._reply(client, 502, b"Upstream connection failed")
            return
        with upstream:
            upstream.setblocking(False)
            client.setblocking(False)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            peers = (client, upstream)
            while True:
                readable, _, exceptional = select.select(peers, (), peers, 60)
                if exceptional or not readable:
                    return
                for source in readable:
                    destination = upstream if source is client else client
                    try:
                        data = source.recv(65536)
                    except OSError:
                        return
                    if not data:
                        return
                    try:
                        destination.sendall(data)
                    except OSError:
                        return

    @staticmethod
    def _authority(value: str, default_port: int) -> tuple[str, int]:
        if value.startswith("[") and "]" in value:
            host, suffix = value[1:].split("]", 1)
            return host, int(suffix[1:]) if suffix.startswith(":") else default_port
        host, separator, raw_port = value.rpartition(":")
        if separator and raw_port.isdigit():
            return host, int(raw_port)
        return value, default_port

    @staticmethod
    def _reply(client: socket.socket, status: int, message: bytes) -> None:
        phrases = {400: "Bad Request", 403: "Forbidden", 405: "Method Not Allowed", 502: "Bad Gateway"}
        try:
            client.sendall(
                f"HTTP/1.1 {status} {phrases[status]}\r\nContent-Length: {len(message)}\r\nConnection: close\r\n\r\n".encode("ascii")
                + message
            )
        except OSError:
            pass


class TutuEgressGuard:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._server: _ProxyServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("egress guard is not started")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self._server is not None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._server = _ProxyServer(("127.0.0.1", 0), self)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def record_blocked(self, host: str, method: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"host": host.lower(), "method": method, "blocked": True}) + "\n")

    def records(self) -> list[dict[str, Any]]:
        if not self.log_path.is_file():
            return []
        records: list[dict[str, Any]] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None
