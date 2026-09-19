from __future__ import annotations

import hashlib
import contextlib
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

try:
    import update_airport_timezones  # noqa: E402
except ModuleNotFoundError:  # RED until the maintenance script exists
    update_airport_timezones = None  # type: ignore[assignment]


SOURCE_URLS = (
    "https://api.travelpayouts.com/data/en/airports.json",
    "https://api.travelpayouts.com/data/ru/airports.json",
    "https://api.travelpayouts.com/data/airports.json",
)


def source_payload(records: list[dict[str, object]]) -> bytes:
    return json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class FakeResponse:
    def __init__(self, body: bytes, *, content_type: str = "application/json") -> None:
        self.body = body
        self.status = 200
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class UpdateAirportTimezonesContractTests(unittest.TestCase):
    def run_update(
        self,
        output: Path,
        responses: dict[str, bytes | Exception],
    ) -> tuple[int, dict[str, Any]]:
        if update_airport_timezones is None:
            self.fail("update_airport_timezones.py is not implemented")

        def urlopen(request: object, timeout: int = 0) -> FakeResponse:
            del timeout
            url = request.full_url  # type: ignore[attr-defined]
            response = responses[url]
            if isinstance(response, Exception):
                raise response
            return FakeResponse(response)

        stdout = io.StringIO()
        with (
            mock.patch.object(
                update_airport_timezones.urllib.request,
                "urlopen",
                side_effect=urlopen,
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = update_airport_timezones.main(["--output", str(output)])
        return code, json.loads(stdout.getvalue())

    def valid_responses(self) -> dict[str, bytes | Exception]:
        return {
            SOURCE_URLS[0]: source_payload(
                [
                    {"code": "svo", "time_zone": "Europe/Moscow"},
                    {"code": "SVX", "time_zone": "Asia/Yekaterinburg"},
                ]
            ),
            SOURCE_URLS[1]: source_payload(
                [
                    {"code": "SVO", "time_zone": "Asia/Yekaterinburg"},
                    {"code": "LED", "time_zone": "Europe/Moscow"},
                ]
            ),
            SOURCE_URLS[2]: source_payload(
                [
                    {"code": "SVO", "time_zone": "Europe/London"},
                    {"code": "KUF", "time_zone": "Europe/Samara"},
                ]
            ),
        }

    def test_success_precedence_zoneinfo_and_provenance(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            code, result = self.run_update(output, self.valid_responses())

            self.assertEqual(code, 0)
            self.assertEqual(result["ok"], True)
            self.assertEqual(result["changed"], True)
            self.assertEqual(result["timezone_count"], 4)
            self.assertEqual(result["added"], 4)
            self.assertEqual(result["removed"], 0)
            self.assertEqual(result["timezone_changed"], 0)

            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["timezones"]["SVO"], "Europe/London")
            self.assertEqual(document["timezones"]["SVX"], "Asia/Yekaterinburg")
            self.assertEqual(document["schema_version"], "airport-timezones.v1")
            self.assertEqual(
                [item["url"] for item in document["source_files"]], list(SOURCE_URLS)
            )
            for item, url in zip(document["source_files"], SOURCE_URLS):
                payload = self.valid_responses()[url]
                if not isinstance(payload, bytes):
                    self.fail("test fixture payload must be bytes")
                self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertIn("records", item)
                self.assertIn("timezone_updates", item)

    def test_download_failure_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b'{"existing": "asset"}\n'
            output.write_bytes(original)
            responses = self.valid_responses()
            responses[SOURCE_URLS[1]] = URLError("offline")

            code, result = self.run_update(output, responses)

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertEqual(output.read_bytes(), original)

    def test_invalid_json_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b"not-json\n"
            output.write_bytes(original)
            responses = self.valid_responses()
            responses[SOURCE_URLS[0]] = b"["

            code, result = self.run_update(output, responses)

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertEqual(output.read_bytes(), original)

    def test_non_array_root_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b'{"existing": "asset"}\n'
            output.write_bytes(original)
            responses = self.valid_responses()
            responses[SOURCE_URLS[0]] = b"{}"

            code, result = self.run_update(output, responses)

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertIn("JSON array", result["error"]["message"])
            self.assertEqual(output.read_bytes(), original)

    def test_invalid_timezone_leaves_existing_asset_untouched(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            original = b'{"existing": "asset"}\n'
            output.write_bytes(original)
            responses = self.valid_responses()
            responses[SOURCE_URLS[2]] = source_payload(
                [{"code": "SVO", "time_zone": "Foo/Bar"}]
            )

            code, result = self.run_update(output, responses)

            self.assertNotEqual(code, 0)
            self.assertEqual(result["ok"], False)
            self.assertIn("known IANA timezone", result["error"]["message"])
            self.assertEqual(output.read_bytes(), original)

    def test_identical_input_is_deterministic_and_does_not_rewrite(self) -> None:
        with TemporaryDirectory(prefix="airport-timezones-contract.") as tmp:
            output = Path(tmp) / "airport-timezones.json"
            responses = self.valid_responses()
            first_code, first_result = self.run_update(output, responses)
            first_bytes = output.read_bytes()
            first_mtime = output.stat().st_mtime_ns
            os.utime(output, ns=(first_mtime - 1_000_000_000, first_mtime - 1_000_000_000))
            preserved_mtime = output.stat().st_mtime_ns

            second_code, second_result = self.run_update(output, responses)

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(first_result["source_hashes"], second_result["source_hashes"])
            self.assertEqual(second_result["changed"], False)
            self.assertEqual(output.read_bytes(), first_bytes)
            self.assertEqual(output.stat().st_mtime_ns, preserved_mtime)


if __name__ == "__main__":
    unittest.main()
