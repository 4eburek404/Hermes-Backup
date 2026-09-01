from __future__ import annotations

import shutil
import socket
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
CATALOG_FIXTURE_DIR = PROJECT / "tests" / "fixtures" / "catalog"
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live-providers",
        action="store_true",
        default=False,
        help="run opt-in tests that call live provider services or MCP servers",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_provider: opt-in tests that call live provider services or MCP servers",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-live-providers"):
        return
    skip_live = pytest.mark.skip(
        reason="live provider smoke test; pass --run-live-providers to run"
    )
    for item in items:
        if "live_provider" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def isolate_flights_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_dir = tmp_path / "flight-search-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for fixture in CATALOG_FIXTURE_DIR.glob("*.json"):
        shutil.copy2(fixture, cache_dir / fixture.name)

    monkeypatch.setenv("FLIGHTS_CACHE_DIR", str(cache_dir))
    # Подпроцессы CLI наследуют окружение, а сетевой замок ниже на них не
    # распространяется. Без этого обновление каталога уходит в живую сеть.
    monkeypatch.setenv("FLIGHTS_CATALOG_REFRESH", "never")
    try:
        import helpers
    except ImportError:
        return
    monkeypatch.setitem(helpers.TEST_ENV, "FLIGHTS_CACHE_DIR", str(cache_dir))


@pytest.fixture(autouse=True)
def block_outbound_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Офлайн по умолчанию: наружу ходит только тест, помеченный live_provider.

    Без этого замка тест может незаметно уехать в живого провайдера мимо своего
    фейка, и базовая линия «все зелёные» перестаёт быть воспроизводимой без сети.
    Локальные стабы (127.0.0.1) разрешены — на них построены офлайн-прогоны CLI.
    """

    if "live_provider" in request.keywords:
        return

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def allowed(address: object) -> bool:
        if not isinstance(address, tuple) or not address:
            return True  # unix-сокеты и прочее не про выход наружу
        return str(address[0]) in LOOPBACK_HOSTS

    def refuse(address: object) -> None:
        raise RuntimeError(
            f"тест пытается выйти в сеть: {address!r}. "
            "Подставьте фейк провайдера или пометьте тест @pytest.mark.live_provider"
        )

    def guarded_connect(self: socket.socket, address: object) -> object:
        if not allowed(address):
            refuse(address)
        return original_connect(self, address)

    def guarded_create_connection(address: object, *args: object, **kwargs: object):
        if not allowed(address):
            refuse(address)
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
