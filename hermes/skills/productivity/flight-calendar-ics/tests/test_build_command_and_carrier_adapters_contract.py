#!/usr/bin/env python3
"""Build command and carrier adapter contracts for flight-calendar-ics."""
from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def base_build_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "route": "auto",
        "output_dir": None,
        "input": None,
        "url": None,
        "url_file": None,
        "pnr_locator": None,
        "pnr_key": None,
        "pnr": None,
        "rloc": None,
        "last_name": None,
        "first_name": None,
        "access_code": None,
        "tz": [],
        "no_alarms": True,
        "frontend_base": None,
        "graphql_endpoint": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class BuildCommandAndCarrierAdaptersContractTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._old_path = list(sys.path)
        script_dir = str(SCRIPTS.resolve())
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

    def tearDown(self) -> None:
        sys.path[:] = self._old_path

    def test_run_build_command_dispatches_auto_route_with_injected_carrier_handlers(self) -> None:
        from flight_calendar.build_command import run_build_command

        calls: list[dict[str, Any]] = []

        def infer_route(_args: argparse.Namespace) -> dict[str, Any]:
            return {"mode": "auto", "route": "redwings", "confidence": 1.0, "evidence": ["host:flyredwings.com"]}

        def redwings_handler(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
            calls.append({"args": args, "process_len": len(process)})
            return 0, {"segments_count": 1, "json_path": str(args.output_json), "ics_path": str(args.output_ics), "write_performed": True}

        def verifier(paths: dict[str, Path], segments_count: int, process: list[dict[str, Any]]) -> dict[str, Any]:
            calls.append({"verify_paths": paths, "segments_count": segments_count})
            return {"ok": True, "event_count": segments_count, "private_modes": {"json": "600", "ics": "600"}}

        with tempfile.TemporaryDirectory(prefix="flight-build-command.") as tmp:
            output_dir = Path(tmp) / "bundle"
            args = base_build_args(
                output_dir=output_dir,
                url="https://booking.flyredwings.com/#/find/ABC123/KEY123/Submit",
            )
            process: list[dict[str, Any]] = []

            rc, data = run_build_command(
                args,
                process,
                make_bundle=lambda _args, _paths, _process: (_ for _ in ()).throw(AssertionError("make route not expected")),
                carrier_handlers={"redwings": redwings_handler},
                infer_route=infer_route,
                verifier=verifier,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(data["route"], "redwings")
        self.assertEqual(data["route_detection"]["evidence"], ["host:flyredwings.com"])
        self.assertEqual(data["verification"]["ok"], True)
        self.assertEqual(data["envelope_path"], str(output_dir / "envelope.json"))
        self.assertEqual(
            data["agent_handoff"],
            {
                "ready": True,
                "media": f"MEDIA:{output_dir / 'flights.ics'}",
                "artifact_inspection_required": False,
                "verification_source": "flight_calendar.bundle.verify_bundle_artifacts",
                "safe_summary": {
                    "route": "redwings",
                    "route_detection_mode": "auto",
                    "segments_count": 1,
                    "verification_ok": True,
                    "vevent_count": 1,
                    "ics_mode": "600",
                },
            },
        )
        self.assertEqual(calls[0]["args"].output_json, output_dir / "itinerary.json")
        self.assertEqual(calls[0]["args"].output_ics, output_dir / "flights.ics")
        self.assertEqual([step["step"] for step in process], ["infer_route", "create_output_bundle"])

    def test_carrier_adapter_builds_redwings_args_from_private_url_file(self) -> None:
        from flight_calendar.carrier_adapters import build_route_args

        with tempfile.TemporaryDirectory(prefix="flight-carrier-adapter.") as tmp:
            url_file = Path(tmp) / "url.txt"
            url_file.write_text("https://booking.flyredwings.com/#/find/ABC123/KEY123/Submit\n", encoding="utf-8")
            paths = {"json": Path(tmp) / "itinerary.json", "ics": Path(tmp) / "flights.ics"}
            args = base_build_args(route="redwings", url_file=url_file, graphql_endpoint="https://example.invalid/graphql")

            route_args = build_route_args(args, paths)

        self.assertEqual(route_args.url, "https://booking.flyredwings.com/#/find/ABC123/KEY123/Submit")
        self.assertEqual(route_args.output_json, paths["json"])
        self.assertEqual(route_args.output_ics, paths["ics"])
        self.assertEqual(route_args.graphql_endpoint, "https://example.invalid/graphql")

    def test_carrier_adapter_rejects_unknown_route_as_usage_error(self) -> None:
        from flight_calendar.carrier_adapters import build_route_args
        from flight_calendar.envelope import CliFailure

        with self.assertRaises(CliFailure) as caught:
            build_route_args(base_build_args(route="unknown"), {"json": Path("itinerary.json"), "ics": Path("flights.ics")})

        self.assertEqual(caught.exception.code, "usage_error")
        self.assertIn("unknown build route", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
