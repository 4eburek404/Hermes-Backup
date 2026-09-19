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


def write_state(runtime_dir: Path, when: datetime, *, field: str = "last_success") -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / timezone_catalog.REFRESH_STATE_FILENAME).write_text(
        json.dumps({field: when.isoformat()}), encoding="utf-8"
    )


def write_catalog(path: Path, *, timezone_value: str = "Europe/Moscow") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": timezone_catalog.SCHEMA_VERSION,
                "source": "test",
                "timezones": {"SVO": timezone_value},
            }
        ),
        encoding="utf-8",
    )


def _concurrent_worker(runtime_dir: str, bundled_path: str, fetch_log: str) -> None:
    def fetch(_url: str) -> bytes:
        with Path(fetch_log).open("a", encoding="utf-8") as handle:
            handle.write("fetch\n")
        time.sleep(0.1)
        return airport_payload()

    timezone_catalog.load_airport_timezones(
        runtime_cache_dir=Path(runtime_dir),
        bundled_catalog_path=Path(bundled_path),
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
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
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
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=fetch,
                now=first,
            )
            second = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=lambda _url: (_ for _ in ()).throw(AssertionError("network")),
                now=first + timedelta(days=6, hours=23),
            )

            self.assertEqual(calls, 1)
            self.assertEqual(second["KUF"], "Europe/Samara")

    def test_catalog_age_14_days_suppresses_network(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            runtime_dir = Path(tmp)
            cache = runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME
            write_catalog(cache, timezone_value="Asia/Yekaterinburg")
            now = datetime(2026, 1, 15, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=14))

            def unexpected(_url: str) -> bytes:
                raise AssertionError("network must be suppressed for a 14-day catalog")

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=runtime_dir / "missing-bundled.json",
                fetch_source=unexpected,
                now=now,
            )

            self.assertEqual(result, {"SVO": "Asia/Yekaterinburg"})

    def test_catalog_age_15_days_refreshes_synchronously(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            runtime_dir = Path(tmp)
            cache = runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME
            write_catalog(cache, timezone_value="Europe/Moscow")
            now = datetime(2026, 1, 16, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=15))
            calls: list[str] = []

            def fetch(url: str) -> bytes:
                calls.append(url)
                return airport_payload()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=runtime_dir / "missing-bundled.json",
                fetch_source=fetch,
                now=now,
            )

            self.assertEqual(calls, [timezone_catalog.CANONICAL_SOURCE_URL])
            self.assertEqual(result["KUF"], "Europe/Samara")
            self.assertEqual(
                json.loads(cache.read_text(encoding="utf-8"))["timezones"]["SVO"],
                "Europe/Moscow",
            )
            state = json.loads(
                (runtime_dir / timezone_catalog.REFRESH_STATE_FILENAME).read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("last_success", state)
            self.assertNotIn("last_attempt", state)

    def test_stale_refresh_failure_keeps_previous_valid_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            runtime_dir = Path(tmp)
            cache = runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME
            write_catalog(cache, timezone_value="Asia/Yekaterinburg")
            before = cache.read_bytes()
            now = datetime(2026, 1, 16, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=15))

            def fail(_url: str) -> bytes:
                raise OSError("Travelpayouts unavailable")

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=runtime_dir / "missing-bundled.json",
                fetch_source=fail,
                now=now,
            )

            self.assertEqual(result, {"SVO": "Asia/Yekaterinburg"})
            self.assertEqual(cache.read_bytes(), before)

    def test_stale_cache_and_bundled_fallback_survive_failed_refresh(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            runtime_dir = Path(tmp)
            cache = runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME
            bundled = runtime_dir / "bundled.json"
            write_catalog(cache, timezone_value="Asia/Yekaterinburg")
            write_catalog(bundled, timezone_value="Europe/Moscow")
            now = datetime(2026, 1, 16, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=15))

            def fail(_url: str) -> bytes:
                raise OSError("Travelpayouts unavailable")

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=bundled,
                fetch_source=fail,
                now=now,
            )

            self.assertEqual(result, {"SVO": "Asia/Yekaterinburg"})

    def test_due_state_makes_one_refresh_attempt(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            calls = 0

            def fetch(url: str) -> bytes:
                nonlocal calls
                calls += 1
                return airport_payload()

            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=fetch,
                now=first,
            )
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=fetch,
                now=first + timedelta(days=15),
            )

            self.assertEqual(calls, 2)

    def test_failed_refresh_uses_cache_and_next_invocation_may_retry(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            runtime_dir = Path(tmp)
            cache = runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME
            write_catalog(cache, timezone_value="Asia/Yekaterinburg")
            first = datetime(2026, 1, 16, tzinfo=UTC)
            write_state(runtime_dir, first - timedelta(days=15))

            def fail(_url: str) -> bytes:
                raise OSError("Travelpayouts unavailable")

            first_result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=runtime_dir / "missing-bundled.json",
                fetch_source=fail,
                now=first,
            )
            calls = 0

            def retry(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                raise OSError("Travelpayouts unavailable")

            second_result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=runtime_dir / "missing-bundled.json",
                fetch_source=retry,
                now=first + timedelta(days=1),
            )

            self.assertEqual(first_result, {"SVO": "Asia/Yekaterinburg"})
            self.assertEqual(second_result, first_result)
            self.assertEqual(calls, 1)

    def test_invalid_refresh_preserves_previous_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            calls = 0

            def valid(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                return airport_payload()

            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=valid,
                now=first,
            )
            cache_path = Path(tmp) / "airport-timezones.json"
            before = cache_path.read_bytes()

            def invalid(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                return b"{"

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=invalid,
                now=first + timedelta(days=15),
            )

            self.assertEqual(result["SVO"], "Europe/Moscow")
            self.assertEqual(cache_path.read_bytes(), before)
            self.assertEqual(calls, 2)

    def test_invalid_timezone_preserves_previous_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=lambda _url: airport_payload(),
                now=first,
            )
            cache_path = Path(tmp) / "airport-timezones.json"
            before = cache_path.read_bytes()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                fetch_source=lambda _url: payload(
                    [{"code": "SVO", "time_zone": "Foo/Bar", "iata_type": "airport"}]
                ),
                now=first + timedelta(days=15),
            )

            self.assertEqual(result["SVO"], "Europe/Moscow")
            self.assertEqual(cache_path.read_bytes(), before)

    def test_cache_write_failure_preserves_previous_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            first = datetime(2026, 1, 1, tzinfo=UTC)
            timezone_catalog.load_airport_timezones(
                runtime_cache_dir=Path(tmp),
                bundled_catalog_path=Path(tmp) / "missing-bundled.json",
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
                    bundled_catalog_path=Path(tmp) / "missing-bundled.json",
                    fetch_source=lambda _url: airport_payload(),
                    now=first + timedelta(days=15),
                )

            self.assertEqual(result["SVO"], "Europe/Moscow")
            self.assertEqual(cache_path.read_bytes(), before)

    def test_concurrent_refreshes_share_one_attempt_and_valid_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-runtime.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            fetch_log = Path(tmp) / "fetch.log"
            write_state(runtime_dir, datetime(2025, 12, 1, tzinfo=UTC))
            context = multiprocessing.get_context("fork")
            processes = [
                context.Process(target=_concurrent_worker, args=(str(runtime_dir), str(Path(tmp) / "missing-bundled.json"), str(fetch_log)))
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

    def test_recovery_missing_everything_bootstraps_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-recovery.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            bundled = Path(tmp) / "missing-bundled.json"
            calls: list[str] = []

            def fetch(url: str) -> bytes:
                calls.append(url)
                return airport_payload()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=bundled,
                fetch_source=fetch,
                now=datetime(2026, 1, 1, tzinfo=UTC),
            )

            self.assertEqual(calls, [timezone_catalog.CANONICAL_SOURCE_URL])
            self.assertEqual(result["SVO"], "Europe/Moscow")
            self.assertTrue((runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME).exists())

    def test_recovery_ignores_fresh_failed_state_when_everything_is_missing(self) -> None:
        with TemporaryDirectory(prefix="timezone-recovery.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            bundled = Path(tmp) / "missing-bundled.json"
            now = datetime(2026, 1, 2, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=1))
            calls: list[str] = []

            def fetch(url: str) -> bytes:
                calls.append(url)
                return airport_payload()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=bundled,
                fetch_source=fetch,
                now=now,
            )

            self.assertEqual(calls, [timezone_catalog.CANONICAL_SOURCE_URL])
            self.assertEqual(result["SVO"], "Europe/Moscow")

    def test_recovery_ignores_fresh_state_when_both_catalogs_are_corrupt(self) -> None:
        with TemporaryDirectory(prefix="timezone-recovery.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            runtime_dir.mkdir()
            cache = runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME
            bundled = Path(tmp) / "bundled.json"
            cache.write_bytes(b"not-json")
            bundled.write_bytes(b"{}")
            now = datetime(2026, 1, 2, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=1))
            calls = 0

            def fetch(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                return airport_payload()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=bundled,
                fetch_source=fetch,
                now=now,
            )

            self.assertEqual(calls, 1)
            self.assertEqual(result["KUF"], "Europe/Samara")

    def test_failed_recovery_fails_closed_without_partial_cache(self) -> None:
        with TemporaryDirectory(prefix="timezone-recovery.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            bundled = Path(tmp) / "missing-bundled.json"
            now = datetime(2026, 1, 2, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=1))
            calls = 0

            def fail(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                raise OSError("Travelpayouts unavailable")

            with self.assertRaises(ValueError):
                timezone_catalog.load_airport_timezones(
                    runtime_cache_dir=runtime_dir,
                    bundled_catalog_path=bundled,
                    fetch_source=fail,
                    now=now,
                )

            self.assertEqual(calls, 1)
            self.assertFalse((runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME).exists())

    def test_failed_recovery_can_retry_inside_ttl_and_self_heal(self) -> None:
        with TemporaryDirectory(prefix="timezone-recovery.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            bundled = Path(tmp) / "missing-bundled.json"
            first = datetime(2026, 1, 2, tzinfo=UTC)
            write_state(runtime_dir, first - timedelta(days=1))
            calls = 0

            def fail(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                raise OSError("temporary upstream failure")

            with self.assertRaises(ValueError):
                timezone_catalog.load_airport_timezones(
                    runtime_cache_dir=runtime_dir,
                    bundled_catalog_path=bundled,
                    fetch_source=fail,
                    now=first,
                )

            def recover(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                return airport_payload()

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=bundled,
                fetch_source=recover,
                now=first + timedelta(days=1),
            )

            self.assertEqual(calls, 2)
            self.assertEqual(result["SVO"], "Europe/Moscow")

    def test_fresh_state_throttles_when_bundled_fallback_is_valid(self) -> None:
        with TemporaryDirectory(prefix="timezone-recovery.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            bundled = Path(tmp) / "bundled.json"
            now = datetime(2026, 1, 2, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=1))
            write_catalog(bundled)
            calls = 0

            def unexpected(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                raise AssertionError("network must be suppressed")

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=bundled,
                fetch_source=unexpected,
                now=now,
            )

            self.assertEqual(calls, 0)
            self.assertEqual(result, {"SVO": "Europe/Moscow"})

    def test_fresh_state_uses_valid_cache_when_bundled_is_corrupt(self) -> None:
        with TemporaryDirectory(prefix="timezone-recovery.") as tmp:
            runtime_dir = Path(tmp) / "cache"
            cache = runtime_dir / timezone_catalog.RUNTIME_CACHE_FILENAME
            bundled = Path(tmp) / "bundled.json"
            now = datetime(2026, 1, 2, tzinfo=UTC)
            write_state(runtime_dir, now - timedelta(days=1))
            write_catalog(cache, timezone_value="Asia/Yekaterinburg")
            bundled.write_bytes(b"not-json")
            calls = 0

            def unexpected(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                raise AssertionError("network must be suppressed")

            result = timezone_catalog.load_airport_timezones(
                runtime_cache_dir=runtime_dir,
                bundled_catalog_path=bundled,
                fetch_source=unexpected,
                now=now,
            )

            self.assertEqual(calls, 0)
            self.assertEqual(result, {"SVO": "Asia/Yekaterinburg"})


if __name__ == "__main__":
    unittest.main()
