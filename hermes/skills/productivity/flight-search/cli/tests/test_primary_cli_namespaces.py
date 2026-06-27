from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from flights_cli.cli import auto_refresh_catalog, build_parser
from flights_cli.command_surface import CATALOG_AUTO_REFRESH_COMMANDS, CATALOG_READ_COMMANDS, CATALOG_REFRESH_COMMANDS
from flights_cli.contracts.registry import current_contract
from flights_cli.pipeline.options import LiveAssemblyOptions
from flights_cli.store import Store

from helpers import parser_leaf_defaults


MINIMAL_SEARCH_REQUEST = {
    "schema_version": "flight_search_request.v1",
    "origin": "SVX",
    "destination": "LON",
    "depart_date": "2026-07-20",
    "return_date": "2026-07-25",
    "currency": "RUB",
    "profile": "business",
    "ticketing": "separate",
    "provider_policy": "auto",
}


class PrimaryCliNamespaceTests(unittest.TestCase):
    def test_catalog_dependent_commands_auto_refresh_when_needed_and_refresh_is_explicit(self) -> None:
        parser = build_parser()
        leaves = parser_leaf_defaults(parser)
        self.assertEqual(set(CATALOG_AUTO_REFRESH_COMMANDS), set(CATALOG_READ_COMMANDS))
        self.assertEqual(CATALOG_REFRESH_COMMANDS, ("maint catalog refresh",))
        for command_name in CATALOG_READ_COMMANDS:
            with self.subTest(command_name=command_name):
                defaults = leaves[command_name]
                self.assertEqual(defaults.get("catalog_access"), "auto_refresh")
                self.assertTrue(defaults.get("requires_catalog", False))
        args = parser.parse_args(["search", "--request", "request.json"])
        with patch("flights_cli.cli.refresh_static_catalog_if_needed") as refresh:
            refresh.return_value = {"enabled": True, "refreshed": False, "reason": "fresh"}
            self.assertEqual(auto_refresh_catalog(args, Store()), refresh.return_value)
            refresh.assert_called_once_with(
                Store().cache_dir,
                max_age_seconds=14 * 24 * 60 * 60,
                timeout=30,
                force=False,
            )

    def test_catalog_refresh_can_be_disabled_for_catalog_dependent_commands(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--catalog-refresh", "never", "search", "--request", "request.json"])
        self.assertEqual(getattr(args, "catalog_access", None), "auto_refresh")
        with patch("flights_cli.cli.refresh_static_catalog_if_needed") as refresh:
            result = auto_refresh_catalog(args, Store())
            self.assertEqual(result["enabled"], False)
            self.assertEqual(result["reason"], "disabled")
            self.assertEqual(result["evidence_scope"]["kind"], "static_metadata")
            self.assertFalse(result["evidence_scope"]["availability_evidence"])
            refresh.assert_not_called()

    def test_search_request_and_result_contract_resources_validate_minimal_payloads(self) -> None:
        from importlib import resources

        request_contract = current_contract("search_request")
        result_contract = current_contract("search_result")
        request_schema = json.loads(resources.files("flights_cli.contracts").joinpath(request_contract["schema_resource"]).read_text(encoding="utf-8"))
        result_schema = json.loads(resources.files("flights_cli.contracts").joinpath(result_contract["schema_resource"]).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(request_schema)
        Draft202012Validator.check_schema(result_schema)

        Draft202012Validator(request_schema).validate(MINIMAL_SEARCH_REQUEST)
        Draft202012Validator(result_schema).validate(
            {
                "schema_version": "flight_search_result.v1",
                "wire_version": "flight_search_result.v1",
                "request": MINIMAL_SEARCH_REQUEST,
                "agent_report": {"schema_version": "agent_report.v2"},
                "route_result": {"agent_report": {"schema_version": "agent_report.v2"}},
            }
        )

    def test_search_app_adapts_request_to_live_assembly_and_wraps_result(self) -> None:
        from flights_cli.apps.search import command_search

        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "request.json"
            request_path.write_text(json.dumps(MINIMAL_SEARCH_REQUEST), encoding="utf-8")
            args = argparse.Namespace(request=str(request_path), command_name="search")
            captured: dict[str, object] = {}

            def fake_run(live_assembly_options: LiveAssemblyOptions, store: Store) -> dict[str, object]:
                captured["origin"] = live_assembly_options.route.origin
                captured["destination"] = live_assembly_options.route.destination
                captured["command_name"] = live_assembly_options.command_name
                captured["agent_brief"] = live_assembly_options.output.agent_brief
                return {"agent_report": {"schema_version": "agent_report.v2"}, "assembly": True}

            with patch("flights_cli.apps.search.run_live_route_assembly", side_effect=fake_run):
                result = command_search(args, Store())

        self.assertEqual(captured, {"origin": "SVX", "destination": "LON", "command_name": "search", "agent_brief": True})
        self.assertEqual(result["schema_version"], "flight_search_result.v1")
        self.assertEqual(result["wire_version"], "flight_search_result.v1")
        self.assertEqual(result["request"], MINIMAL_SEARCH_REQUEST)
        self.assertEqual(result["agent_report"], {"schema_version": "agent_report.v2"})
        self.assertTrue(result["route_result"]["assembly"])

    def test_search_json_errors_are_machine_parseable_on_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "invalid-request.json"
            request_path.write_text(json.dumps({"schema_version": "flight_search_request.v1"}), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "flights_cli", "--json", "search", "--request", str(request_path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "validation_error")
        self.assertEqual(proc.stderr, "")


if __name__ == "__main__":
    unittest.main()
