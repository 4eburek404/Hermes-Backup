from __future__ import annotations

import shutil
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
CATALOG_FIXTURE_DIR = PROJECT / "tests" / "fixtures" / "catalog"


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
    try:
        import helpers
    except ImportError:
        return
    monkeypatch.setitem(helpers.TEST_ENV, "FLIGHTS_CACHE_DIR", str(cache_dir))
