from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import update_airport_timezones  # noqa: E402


SOURCE_URL = "https://api.travelpayouts.com/data/en/airports.json"


def source_payload(records: list[dict[str, object]]) -> bytes:
    return json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class UpdateAirportTimezonesContractTests(unittest.TestCase):
    def run_update(
        self,
        output: Path,
        response: bytes | Exception,
    ) -> tuple[int, dict[str, Any]]:
        def fetch(url: str) -> bytes:
            self.assertEqual(url, SOURCE_URL)
            if isinstance(response, Exception):
                raise response
            return response

        stdout = io.StringIO()
        with (
            mock.patch.object(update_airport_timezones, "fetch_source", side_effect=fetch),
            contextlib.redirect_stdout(stdout),
        ):
            code = update_airport_timezones.main(["--output", str(output)])
        return code, json.loads(stdout.getvalue())

    def valid_response(self) -> bytes:
        return source_payload(
            [
                {"code": "svo", "time_zone": "Europe/Moscow", "iata_type": "airport", "flightable": True},
                {"code": "KUF", "time_zone": "Europe/Samara", "iata_type": "airport", "flightable": False},
                {"code": "BUS", "time_zone": "Europe/Moscow", "iata_type": "bus", "flightable": True},
                {"code": "RWA", "time_zone": "Europe/Moscow", "iata_type": "railway", "flightable": True},
                {"code": "HEL", "time_zone": "Europe/Moscow", "iata_type": "heliport", "flightable": True},
            ]
        )

    def test_success_airports_only_zoneinfo_and_provenance(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            code, result = self.run_update(output, self.valid_response())

            self.assertEqual(code, 0)
            self.assertEqual(result["ok"], True)
            self.assertEqual(result["changed"], True)
            self.assertEqual(result["timezone_count"], 2)
            self.assertEqual(result["added"], 2)
            self.assertEqual(result["removed"], 0)
            self.assertEqual(result["timezone_changed"], 0)

            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["timezones"], {"KUF": "Europe/Samara", "SVO": "Europe/Moscow"})
            self.assertEqual(document["schema_version"], "airport-timezones.v1")
            self.assertEqual(document["source_files"][0]["url"], SOURCE_URL)
            self.assertEqual(document["source_files"][0]["records"], 5)
            self.assertEqual(document["source_files"][0]["airports_retained"], 2)
            self.assertNotIn("timezone_updates", document["source_files"][0])
            self.assertEqual(
                document["source_files"][0]["sha256"],
                hashlib.sha256(self.valid_response()).hexdigest(),
            )

    def test_download_failure_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b'{"existing": "asset"}\n'
            output.write_bytes(original)

            code, result = self.run_update(output, URLError("offline"))

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertEqual(output.read_bytes(), original)

    def test_invalid_json_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b"not-json\n"
            output.write_bytes(original)

            code, result = self.run_update(output, b"[")

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertEqual(output.read_bytes(), original)

    def test_non_array_root_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b'{"existing": "asset"}\n'
            output.write_bytes(original)

            code, result = self.run_update(output, b"{}")

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertIn("JSON array", result["error"]["message"])
            self.assertEqual(output.read_bytes(), original)

    def test_invalid_timezone_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b'{"existing": "asset"}\n'
            output.write_bytes(original)
            response = source_payload(
                [{"code": "SVO", "time_zone": "Foo/Bar", "iata_type": "airport"}]
            )

            code, result = self.run_update(output, response)

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertIn("known IANA timezone", result["error"]["message"])
            self.assertEqual(output.read_bytes(), original)

    def test_identical_input_is_deterministic_and_does_not_rewrite(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            response = self.valid_response()
            first_code, first_result = self.run_update(output, response)
            first_bytes = output.read_bytes()
            first_mtime = output.stat().st_mtime_ns
            os.utime(output, ns=(first_mtime - 1_000_000_000, first_mtime - 1_000_000_000))
            preserved_mtime = output.stat().st_mtime_ns

            second_code, second_result = self.run_update(output, response)

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(first_result["source_hashes"], second_result["source_hashes"])
            self.assertEqual(second_result["changed"], False)
            self.assertEqual(output.read_bytes(), first_bytes)
            self.assertEqual(output.stat().st_mtime_ns, preserved_mtime)


if __name__ == "__main__":
    unittest.main()
