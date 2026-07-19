from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flights_cli.cli import auto_refresh_catalog, build_parser
from flights_cli.command_surface import (
    CATALOG_AUTO_REFRESH_COMMANDS,
    CATALOG_READ_COMMANDS,
    CATALOG_REFRESH_COMMANDS,
)
from flights_cli.contracts.validation import validate_contract_payload
from flights_cli.pipeline.search_request import SearchRequest
from flights_cli.store import Store
from helpers import parser_leaf_defaults
from test_result_contract import valid_result


MINIMAL_SEARCH_REQUEST = {
    "schema_version": "flight_search_request.v3",
    "origin": "SVX",
    "destination": "LON",
    "depart_date": "2026-07-20",
    "return_date": "2026-07-25",
    "currency": "RUB",
    "profile": "business",
    "provider_policy": "auto",
}


class PrimaryCliNamespaceTests(unittest.TestCase):
    def test_catalog_dependent_commands_auto_refresh_when_needed_and_refresh_is_explicit(
        self,
    ) -> None:
        parser = build_parser()
        leaves = parser_leaf_defaults(parser)
        self.assertEqual(set(CATALOG_AUTO_REFRESH_COMMANDS), set(CATALOG_READ_COMMANDS))
        self.assertEqual(CATALOG_REFRESH_COMMANDS, ("maint catalog refresh",))
        for command_name in CATALOG_READ_COMMANDS:
            self.assertEqual(leaves[command_name].get("catalog_access"), "auto_refresh")
        args = parser.parse_args(["search", "--request", "request.json"])
        with patch("flights_cli.cli.refresh_static_catalog_if_needed") as refresh:
            refresh.return_value = {
                "enabled": True,
                "refreshed": False,
                "reason": "fresh",
            }
            self.assertEqual(auto_refresh_catalog(args, Store()), refresh.return_value)

    def test_catalog_refresh_can_be_disabled(self) -> None:
        args = build_parser().parse_args(
            ["--catalog-refresh", "never", "search", "--request", "request.json"]
        )
        result = auto_refresh_catalog(args, Store())
        self.assertFalse(result["enabled"])
        self.assertFalse(result["evidence_scope"]["availability_evidence"])

    def test_request_and_result_contract_resources_validate(self) -> None:
        validate_contract_payload("search_request", valid_result()["request"])
        validate_contract_payload("search_result", valid_result())

    def test_search_command_adapts_to_typed_request(self) -> None:
        from flights_cli.commands.search import command_search

        captured: dict[str, object] = {}

        def fake_run(request: SearchRequest) -> dict[str, str]:
            captured["origin"] = request.origin
            captured["destination"] = request.destination
            return {"schema_version": "flight_search_result.v9"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "request.json"
            request_path.write_text(
                json.dumps(MINIMAL_SEARCH_REQUEST), encoding="utf-8"
            )
            args = argparse.Namespace(request=str(request_path), command_name="search")
            with patch("flights_cli.commands.search.SearchWorkflow") as workflow:
                workflow.return_value.run.side_effect = fake_run
                result = command_search(args, Store())

        self.assertEqual(captured, {"origin": "SVX", "destination": "LON"})
        self.assertEqual(result["schema_version"], "flight_search_result.v9")

    def test_diagnose_trace_serializes_existing_artifacts_once(self) -> None:
        from flights_cli.commands.diagnose import command_diagnose_trace

        evidence = SimpleNamespace(to_trace_dict=lambda: {"provider_policy": "auto"})
        decision = SimpleNamespace(
            offer_graph={},
            offer_candidates={},
            scored_decisions={"scorer": {}},
            decision_frontier={},
        )
        artifacts = SimpleNamespace(
            request=MINIMAL_SEARCH_REQUEST,
            execution=SimpleNamespace(
                plan={},
                evidence=evidence,
                decision=decision,
                projection_input={},
            ),
            projection={"answer": {}},
        )
        args = argparse.Namespace(request="unused.json", command_name="diagnose trace")
        with (
            patch("flights_cli.commands.diagnose.prepare_search_request"),
            patch(
                "flights_cli.commands.diagnose.build_search_artifacts",
                return_value=artifacts,
            ),
            patch(
                "flights_cli.commands.diagnose.validate_contract_payload"
            ) as validate,
        ):
            result = command_diagnose_trace(args, Store())

        self.assertEqual(result["schema_version"], "flight_route_trace_diagnostic.v4")
        self.assertEqual(
            set(result),
            {"schema_version", "request", "plan", "evidence", "decision", "answer"},
        )
        validate.assert_called_once_with("route_trace", result)

    def test_search_json_errors_are_machine_parseable_on_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "invalid-request.json"
            request_path.write_text(
                json.dumps({"schema_version": "flight_search_request.v3"}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "--json",
                    "search",
                    "--request",
                    str(request_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)["ok"])
        self.assertEqual(proc.stderr, "")

    def test_search_json_success_has_no_stderr_or_traceback(self) -> None:
        from flights_cli.cli import main

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch("flights_cli.cli.command_search", return_value=valid_result()),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = main(
                [
                    "flights",
                    "--json",
                    "--catalog-refresh",
                    "never",
                    "search",
                    "--request",
                    "unused.json",
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout.getvalue())["ok"])
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("Traceback", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
