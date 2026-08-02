from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from flights_cli.cli import build_parser
from flights_cli.commands import search as search_app
from flights_cli.command_surface import (
    AGENT_COMMANDS,
    CATALOG_AUTO_REFRESH_COMMANDS,
    CATALOG_READ_COMMANDS,
    CATALOG_REFRESH_COMMANDS,
    COMMAND_SPECS,
    DIAGNOSTIC_COMMANDS,
    DIAGNOSTIC_PROBE_COMMANDS,
    PRIMARY_ROUTE_COMMAND,
)
from flights_cli.config import DEFAULT_ROUTE_HUBS
from tests.fixtures.result_fixtures import valid_report

from helpers import PROJECT, TEST_ENV, parser_leaf_defaults


HELP_GOLDENS = {
    ("search",): """usage: flights search [-h] --request REQUEST

options:
  -h, --help         show this help message and exit
  --request REQUEST  flight_search_request.v3 JSON file, or - for stdin.
""",
    ("diagnose", "plan"): """usage: flights diagnose plan [-h] --request REQUEST

options:
  -h, --help         show this help message and exit
  --request REQUEST  flight_search_request.v3 JSON file, or - for stdin.
""",
    (
        "diagnose",
        "probe",
    ): """usage: flights diagnose probe [-h] --provider PROVIDER --request REQUEST

options:
  -h, --help           show this help message and exit
  --provider PROVIDER
  --request REQUEST    Probe JSON file, or - for stdin.
""",
    (
        "diagnose",
        "render",
    ): """usage: flights diagnose render [-h] --input INPUT

options:
  -h, --help     show this help message and exit
  --input INPUT  flight-search result JSON file, output envelope, or - for
                 stdin.
""",
    ("diagnose", "trace"): """usage: flights diagnose trace [-h] --request REQUEST

options:
  -h, --help         show this help message and exit
  --request REQUEST  flight_search_request.v3 JSON file, or - for stdin.
""",
    (
        "maint",
        "check",
    ): """usage: flights maint check [-h] [--runtime-path RUNTIME_PATH]

options:
  -h, --help            show this help message and exit
  --runtime-path RUNTIME_PATH
                        Runtime flight-search skill path to compare against.
                        Defaults to ~/.hermes/skills/productivity/flight-
                        search.
""",
    ("maint", "doctor"): """usage: flights maint doctor [-h]

options:
  -h, --help  show this help message and exit
""",
    ("maint", "catalog", "manifest"): """usage: flights maint catalog manifest [-h]

options:
  -h, --help  show this help message and exit
""",
    (
        "maint",
        "catalog",
        "refresh",
    ): """usage: flights maint catalog refresh [-h] [--only ONLY] [--timeout TIMEOUT]
                                     [--dry-run]

options:
  -h, --help         show this help message and exit
  --only ONLY        Catalog item name. Repeatable; defaults to all static
                     files.
  --timeout TIMEOUT  HTTP timeout seconds per static file.
  --dry-run          Show files that would be downloaded without writing
                     cache.
""",
    ("cities", "search"): """usage: flights cities search [-h] [--limit LIMIT] query

positional arguments:
  query

options:
  -h, --help     show this help message and exit
  --limit LIMIT
""",
    ("airports", "explain"): """usage: flights airports explain [-h] code [code ...]

positional arguments:
  code

options:
  -h, --help  show this help message and exit
""",
}


def live_search_args(**overrides: object) -> argparse.Namespace:
    request = {
        "schema_version": "flight_search_request.v3",
        "origin": overrides.pop("origin", "SVX"),
        "destination": overrides.pop("destination", "DEL"),
        "depart_date": overrides.pop("depart_date", "2026-06-01"),
        "return_date": overrides.pop("return_date", None),
        "currency": overrides.pop("currency", "RUB"),
        "profile": overrides.pop("profile", "business"),
        "provider_policy": overrides.pop("provider_policy", "kupibilet"),
        "route_options": {
            "max_connections": overrides.pop("max_connections", None),
            "tier2_max_connections": overrides.pop("tier2_max_connections", None),
        },
        "output": {},
        "evidence": {},
    }
    adapter = getattr(search_app, "search_request_from_payload", None)
    if not callable(adapter):
        raise AssertionError(
            "search app must expose search_request_from_payload as the canonical search adapter"
        )
    options = adapter(request)
    args = argparse.Namespace(
        command_name="search",
        provider_policy=options.evidence.provider_policy,
        profile=options.profile,
        max_connections=options.route.max_connections,
        tier2_max_connections=options.route.tier2_max_connections,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


class CliContractTests(unittest.TestCase):
    def assert_metadata_only_evidence_scope(self, scope: dict) -> None:
        self.assertEqual(scope["kind"], "static_metadata")
        self.assertFalse(scope["availability_evidence"])
        self.assertFalse(scope["availability_claims_allowed"])
        self.assertTrue(scope["live_provider_evidence_required"])

    def test_default_live_search_cache_ttl_is_30_minutes(self) -> None:
        from flights_cli.config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS

        self.assertEqual(DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, 30 * 60)

    def test_active_command_surface_is_registered_with_leaf_dispatch(self) -> None:
        leaves = parser_leaf_defaults(build_parser())
        specs_by_name = {spec.name: spec for spec in COMMAND_SPECS}
        self.assertEqual(len(COMMAND_SPECS), 11)
        self.assertEqual(set(leaves), set(specs_by_name))
        policy_commands = (
            set(AGENT_COMMANDS)
            | set(DIAGNOSTIC_COMMANDS)
            | set(CATALOG_READ_COMMANDS)
            | set(CATALOG_REFRESH_COMMANDS)
        )
        self.assertTrue(policy_commands.issubset(leaves))
        self.assertIn(PRIMARY_ROUTE_COMMAND, leaves)
        for command_name, defaults in leaves.items():
            with self.subTest(command_name=command_name):
                spec = specs_by_name[command_name]
                self.assertEqual(defaults.get("command_name"), command_name)
                self.assertTrue(callable(defaults.get("func")))
                self.assertEqual(defaults.get("catalog_access"), spec.catalog_access)
                self.assertEqual(
                    defaults.get("requires_catalog", False), spec.requires_catalog
                )

    def test_docs_smoke_commands_parse(self) -> None:
        parser = build_parser()
        docs_argv = {
            "search --request": [
                "--json",
                "search",
                "--request",
                "/tmp/flight-search-request.json",
            ],
            "diagnose plan --request": [
                "--json",
                "diagnose",
                "plan",
                "--request",
                "/tmp/flight-search-request.json",
            ],
            "diagnose probe --provider": [
                "--json",
                "diagnose",
                "probe",
                "--provider",
                "tutu",
                "--request",
                "/tmp/probe.json",
            ],
            "diagnose trace --request": [
                "--json",
                "diagnose",
                "trace",
                "--request",
                "/tmp/flight-search-request.json",
            ],
            "diagnose render --input": [
                "--json",
                "diagnose",
                "render",
                "--input",
                "/tmp/flight-search-result.json",
            ],
            "maint doctor": ["--json", "maint", "doctor"],
            "maint check": ["--json", "maint", "check"],
            "maint catalog manifest": [
                "--json",
                "maint",
                "catalog",
                "manifest",
            ],
            "maint catalog refresh": [
                "--json",
                "maint",
                "catalog",
                "refresh",
                "--dry-run",
            ],
            "cities search": ["--json", "cities", "search", "Yekaterinburg"],
            "airports explain": ["--json", "airports", "explain", "SVX", "MOW"],
        }

        for label, argv in docs_argv.items():
            with self.subTest(label=label):
                self.assertTrue(callable(parser.parse_args(argv).func))

    def test_all_leaf_help_output_matches_goldens(self) -> None:
        self.assertEqual(
            set(HELP_GOLDENS),
            {spec.path for spec in COMMAND_SPECS},
        )
        env = {**TEST_ENV, "COLUMNS": "80"}
        for command_path, expected in HELP_GOLDENS.items():
            with self.subTest(command=" ".join(command_path)):
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "flights_cli",
                        *command_path,
                        "--help",
                    ],
                    cwd=PROJECT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stderr, "")
                self.assertEqual(proc.stdout, expected)

    def test_diagnostic_provider_is_registry_validated_after_parsing(self) -> None:
        args = build_parser().parse_args(
            [
                "diagnose",
                "probe",
                "--provider",
                "future-provider",
                "--request",
                "/tmp/probe.json",
            ]
        )
        self.assertEqual(args.provider, "future-provider")

    def test_catalog_refresh_surface_matches_registered_catalog_commands(self) -> None:
        leaves = parser_leaf_defaults(build_parser())
        self.assertEqual(set(CATALOG_AUTO_REFRESH_COMMANDS), set(CATALOG_READ_COMMANDS))
        for command_name in CATALOG_READ_COMMANDS:
            with self.subTest(command_name=command_name):
                defaults = leaves[command_name]
                self.assertTrue(defaults.get("requires_catalog", False))
                self.assertEqual(defaults.get("catalog_access"), "auto_refresh")
        for command_name in CATALOG_REFRESH_COMMANDS:
            with self.subTest(command_name=command_name):
                self.assertEqual(
                    leaves[command_name].get("catalog_access"), "refresh_explicit"
                )

    def test_metadata_commands_report_metadata_only_evidence_scope(self) -> None:
        commands = {
            "cities search": ["--json", "cities", "search", "Yekaterinburg"],
            "airports explain": ["--json", "airports", "explain", "SVX", "MOW"],
            "maint catalog manifest": ["--json", "maint", "catalog", "manifest"],
            "maint catalog refresh": [
                "--json",
                "maint",
                "catalog",
                "refresh",
                "--dry-run",
            ],
        }

        for command_name, argv in commands.items():
            with self.subTest(command_name=command_name):
                proc = subprocess.run(
                    [sys.executable, "-m", "flights_cli", *argv],
                    cwd=PROJECT,
                    env=TEST_ENV,
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                payload = json.loads(proc.stdout)
                self.assertTrue(payload["ok"])
                self.assert_metadata_only_evidence_scope(
                    payload["data"]["evidence_scope"]
                )
                if "catalog_auto_refresh" in payload["data"]:
                    self.assert_metadata_only_evidence_scope(
                        payload["data"]["catalog_auto_refresh"]["evidence_scope"]
                    )

    def test_search_request_accepts_explicit_kupibilet_provider_policy(self) -> None:
        args = live_search_args(
            destination="LON", depart_date="2099-07-20", provider_policy="kupibilet"
        )

        self.assertEqual(args.command_name, "search")
        self.assertEqual(args.provider_policy, "kupibilet")
        self.assertEqual(args.profile, "business")

    def test_subprocess_test_env_disables_bytecode_writes(self) -> None:
        self.assertEqual(TEST_ENV["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertIn("FLIGHTS_CACHE_DIR", TEST_ENV)

    def test_json_doctor_envelope(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "--json", "maint", "doctor"],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "maint doctor")
        self.assertEqual(payload["issues"], [])
        self.assertEqual(
            payload["data"]["cli"], {"name": "flights-cli", "version": "0.10.0"}
        )
        self.assertEqual(
            payload["data"]["skill"], {"name": "flight-search", "version": "0.13.0"}
        )
        self.assertEqual(
            set(payload["data"]),
            {
                "cache_counts",
                "cache_dir",
                "cache_dir_exists",
                "cache_files",
                "catalog_auto_refresh_policy",
                "catalog_staleness",
                "cli",
                "default_route_hubs",
                "offline_first",
                "python",
                "risk_profiles",
                "runtime_evidence_policy",
                "safety",
                "skill",
                "version",
                "version_manifest",
            },
        )
        self.assertEqual(payload["data"]["version_manifest"]["mismatches"], [])
        self.assertEqual(
            payload["data"]["safety"],
            {
                "booking_or_purchase": False,
                "docker_touched": False,
                "agent_commands": list(AGENT_COMMANDS),
                "primary_route_command": PRIMARY_ROUTE_COMMAND,
                "canonical_path": f"{PRIMARY_ROUTE_COMMAND} --request",
                "diagnostic_probe_commands": list(DIAGNOSTIC_PROBE_COMMANDS),
            },
        )
        self.assertEqual(
            payload["data"]["catalog_auto_refresh_policy"]["applies_to"],
            list(CATALOG_AUTO_REFRESH_COMMANDS),
        )
        self.assertEqual(
            payload["data"]["catalog_auto_refresh_policy"]["max_age"], "2w"
        )
        self.assertEqual(
            payload["data"]["catalog_auto_refresh_policy"]["max_age_seconds"],
            14 * 24 * 60 * 60,
        )
        self.assertEqual(
            [item["code"] for item in payload["data"]["default_route_hubs"]],
            list(DEFAULT_ROUTE_HUBS),
        )
        self.assertEqual(
            set(payload["data"]["cache_counts"]),
            {"airlines", "airports", "alliances", "cities", "countries", "planes"},
        )
        retry_policy = payload["data"]["runtime_evidence_policy"]["retry_policy"]
        self.assertEqual(
            retry_policy["providers"]["tutu"],
            {
                "active_retry": True,
                "max_attempts": 2,
                "scope": "transient_read_only_transport_failures",
            },
        )
        self.assertEqual(
            retry_policy["providers"]["kupibilet"],
            {"active_retry": False, "max_attempts": 1},
        )

        user_text_proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "maint", "doctor"],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(user_text_proc.stderr, "")
        self.assertFalse(user_text_proc.stdout.lstrip().startswith("{"))
        self.assertLessEqual(
            len([line for line in user_text_proc.stdout.splitlines() if line.strip()]),
            12,
        )

    def test_invalid_catalog_refresh_env_is_json_validation_error_for_all_commands(
        self,
    ) -> None:
        env = {**TEST_ENV, "FLIGHTS_CATALOG_REFRESH": "bad"}
        for argv in (
            ["--json", "maint", "doctor"],
            ["--json", "cities", "search", "London"],
        ):
            with self.subTest(argv=argv):
                proc = subprocess.run(
                    [sys.executable, "-m", "flights_cli", *argv],
                    cwd=PROJECT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                payload = json.loads(proc.stdout)
                self.assertEqual(proc.returncode, 1)
                self.assertEqual(proc.stderr, "")
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"]["type"], "validation_error")

    def test_json_diagnose_plan_envelope_and_repeatable_hubs(self) -> None:
        request = {
            "schema_version": "flight_search_request.v3",
            "origin": "SVX",
            "destination": "LON",
            "depart_date": "2099-07-20",
            "route_options": {
                "hubs": ["IST", "DXB"],
                "routing_strategy": "hub-list",
                "destination_airports": ["BBB", "BBA"],
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "flight-search-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "--json",
                    "diagnose",
                    "plan",
                    "--request",
                    str(request_path),
                ],
                cwd=PROJECT,
                env=TEST_ENV,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "diagnose plan")
        self.assertEqual(
            payload["data"]["schema_version"], "flight_search_plan_diagnostic.v2"
        )
        self.assert_metadata_only_evidence_scope(payload["data"]["evidence_scope"])
        data = payload["data"]["plan"]
        provider_queries = data["phases"]["primary"]
        self.assertTrue(provider_queries)
        first_attempt = provider_queries[0]
        first_query = first_attempt["query"]
        self.assertEqual(first_query["role"], "primary_offer_collection")
        self.assertEqual(first_query["source_type"], "provider_full_route")
        self.assertEqual(first_attempt["probe_type"], "full_route_aggregate")
        self.assertEqual(first_query["currency"], "RUB")
        self.assertNotIn("command", first_query)
        route = data["route"]
        self.assertEqual(route["hubs"], ["IST", "DXB"])
        self.assertEqual(route["destination_airports"], ["BBA", "BBB"])
        self.assertEqual(
            route["airport_scope"]["destination"]["scope"], "explicit_airports"
        )
        self.assertEqual(
            route["airport_scope"]["destination"]["excluded_by_default"], []
        )
        self.assertEqual(data["schema_version"], "flight_search_plan.v5")

    def test_diagnose_render_subprocess_success_json_boundary(self) -> None:
        answer = valid_report()["user_answer"]
        result = {
            "schema_version": "flight_search_result.v9",
            "answer": answer,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            result_path = Path(tmp_dir) / "flight-search-result.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "--json",
                    "diagnose",
                    "render",
                    "--input",
                    str(result_path),
                ],
                cwd=PROJECT,
                env=TEST_ENV,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "diagnose render")
        self.assertEqual(payload["issues"], [])
        self.assertEqual(
            payload["data"]["schema_version"],
            "flight_search_render_diagnostic.v1",
        )
        self.assertEqual(
            payload["data"]["search_result_schema_version"],
            "flight_search_result.v9",
        )
        self.assertEqual(payload["data"]["validation"], {"ok": True, "errors": []})
        self.assertEqual(payload["data"]["user_answer"], answer)

    def test_diagnose_probe_subprocess_registry_error_json_boundary(self) -> None:
        request = {
            "origin": "SVX",
            "destination": "DME",
            "date": "2026-08-15",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "probe.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "--json",
                    "diagnose",
                    "probe",
                    "--provider",
                    "future-provider",
                    "--request",
                    str(request_path),
                ],
                cwd=PROJECT,
                env=TEST_ENV,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "validation_error")
        self.assertIn("future-provider", payload["error"]["message"])
        self.assertNotIn("Traceback", proc.stdout)

    def test_diagnose_trace_subprocess_contract_error_json_boundary(self) -> None:
        request = {"schema_version": "flight_search_request.v3"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "invalid-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "--json",
                    "diagnose",
                    "trace",
                    "--request",
                    str(request_path),
                ],
                cwd=PROJECT,
                env=TEST_ENV,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "validation_error")
        self.assertNotIn("Traceback", proc.stdout)

    def test_leaf_json_flag_is_accepted_without_argv_rewrite(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["diagnose", "plan", "--request", "request.json", "--json"]
        )

        self.assertTrue(args.json)
        self.assertEqual(args.command_name, "diagnose plan")


if __name__ == "__main__":
    unittest.main()
