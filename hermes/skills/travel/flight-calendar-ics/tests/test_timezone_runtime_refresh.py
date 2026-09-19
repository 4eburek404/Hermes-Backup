from __future__ import annotations

import json
import multiprocessing
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from flight_calendar import timezone_catalog  # noqa: E402


UTC = timezone.utc


def payload(records: list[dict[str, object]]) -> bytes:
    return json.dumps(records, separators=(",", ":")).encode("utf-8")


def airport_payload() -> bytes:
    return payload(
        [
            {"code": "SVO", "time_zone": "Europe/Moscow", "iata_type": "airport", "flightable": True},
            {"code": "KUF", "time_zone": "Europe/Samara", "iata_type": "airport", "flightable": False},
            {"code": "BUS", "time_zone": "Europe/Moscow", "iata_type": "bus", "flightable": True},
            {"code": "RWA", "time_zone": "Europe/Moscow", "iata_type": "railway", "flightable": True},
            {"code": "HEL", "time_zone": "Europe/Moscow", "iata_type": "heliport", "flightable": True},
        ]
    )


def _concurrent_worker(runtime_dir: str, fetch_log: str) -> None:
    def fetch(_url: str) -> bytes:
        with Path(fetch_log).open("a", encoding="utf-8") as handle:
            handle.write("fetch\n")
        time.sleep(0.1)
        return airport_payload()

    timezone_catalog.load_airport_timezones(
        runtime_cache_dir=Path(runtime_dir),
        fetch_source=fetch,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )


class RuntimeTimezoneRefreshContractTests(unittest.TestCase):
    def test_single_canonical_fetch_and_airports_only_filter(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            calls: list[str] = []

            def fetch(url: str) -> bytes:
                calls.append(url)
                return airport_payload()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                fetch_source=fetch,
                now=datetime(2026, 1, 1, tzinfo=UTC),
            )

            self.assertEqual(calls, [timezone_catalog.CANONICAL_SOURCE_URL])
            self.assertEqual(result, {"SVO": "Europe/Moscow", "KUF": "Europe/Samara"})

    def test_fresh_state_suppresses_network_until_ttl(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            calls = 0

            def fetch(url: str) -> bytes:
                nonlocal calls
                calls += 1
                return airport_payload()

            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp), fetch_source=fetch, now=first
            )
            second = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                fetch_source=lambda _url: (_ for _ in ()).throw(AssertionError("network")),
                now=first + timedelta(days=6, hours=23),
            )

            self.assertEqual(calls, 1)
            self.assertEqual(second["KUF"], "Europe/Samara")

    def test_due_state_makes_one_refresh_attempt(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            calls = 0

            def fetch(url: str) -> bytes:
                nonlocal calls
                calls += 1
                return airport_payload()

            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp), fetch_source=fetch, now=first
            )
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp), fetch_source=fetch, now=first + timedelta(days=7)
            )

            self.assertEqual(calls, 2)

    def test_failed_attempt_is_stateful_and_falls_back(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            first = datetime(2026, 1, 1, tzinfo=UTC)

            def fail(_url: str) -> bytes:
                raise OSError("Travelpayouts unavailable")

            first_result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp), fetch_source=fail, now=first
            )
            calls = 0

            def unexpected(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                raise AssertionError("second network attempt inside TTL")

            second_result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp), fetch_source=unexpected, now=first + timedelta(days=1)
            )

            self.assertIn("SVO", first_result)
            self.assertEqual(second_result, first_result)
            self.assertEqual(calls, 0)

    def test_invalid_refresh_preserves_previous_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            calls = 0

            def valid(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                return airport_payload()

            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp), fetch_source=valid, now=first
            )
            cache_path = Path(tmp) / "airport-timezones.json"
            before = cache_path.read_bytes()

            def invalid(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                return b"{"

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp), fetch_source=invalid, now=first + timedelta(days=7)
            )

            self.assertEqual(result["SVO"], "Europe/Moscow")
            self.assertEqual(cache_path.read_bytes(), before)
            self.assertEqual(calls, 2)

    def test_invalid_timezone_preserves_previous_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                fetch_source=lambda _url: airport_payload(),
                now=first,
            )
            cache_path = Path(tmp) / "airport-timezones.json"
            before = cache_path.read_bytes()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                fetch_source=lambda _url: payload(
                    [{"code": "SVO", "time_zone": "Foo/Bar", "iata_type": "airport"}]
                ),
                now=first + timedelta(days=7),
            )

            self.assertEqual(result["SVO"], "Europe/Moscow")
            self.assertEqual(cache_path.read_bytes(), before)

    def test_cache_write_failure_preserves_previous_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                fetch_source=lambda _url: airport_payload(),
                now=first,
            )
            cache_path = Path(tmp) / "airport-timezones.json"
            before = cache_path.read_bytes()
            original_write = timezone_catalog.atomic_write_bytes

            def fail_cache_write(path: Path, content: bytes) -> None:
                if path.name == "airport-timezones.json":
                    raise OSError("disk full")
                original_write(path, content)

            with mock.patch.object(
                timezone_catalog, "atomic_write_bytes", side_effect=fail_cache_write
            ):
                result = timezone_catalog.load_airport_timezones(
                    runtime_cache_dir=Path(tmp),
                    fetch_source=lambda _url: airport_payload(),
                    now=first + timedelta(days=7),
                )

            self.assertEqual(result["SVO"], "Europe/Moscow")
            self.assertEqual(cache_path.read_bytes(), before)

    def test_concurrent_refreshes_share_one_attempt_and_valid_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            fetch_log = Path(tmp) / "fetch.log"
            context = multiprocessing.get_context("fork")
            processes = [
                context.Process(target=_concurrent_worker, args=(str(runtime_dir), str(fetch_log)))
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)

            self.assertEqual(fetch_log.read_text(encoding="utf-8").splitlines(), ["fetch"])
            cached = json.loads((runtime_dir / "airport-timezones.json").read_text())
            self.assertEqual(cached["timezones"]["SVO"], "Europe/Moscow")


if __name__ == "__main__":
    unittest.main()
