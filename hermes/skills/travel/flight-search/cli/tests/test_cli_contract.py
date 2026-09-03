from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unittest

from flights_cli.cli import build_parser
from flights_cli.commands import search as search_app
from flights_cli.command_surface import (
    AGENT_COMMANDS,
    CATALOG_AUTO_REFRESH_COMMANDS,
    CATALOG_READ_COMMANDS,
    CATALOG_REFRESH_COMMANDS,
    COMMAND_SPECS,
    PRIMARY_ROUTE_COMMAND,
)

from helpers import PROJECT, TEST_ENV, future_departure_date, parser_leaf_defaults


HELP_GOLDENS = {
    ("search",): """usage: flights search [-h] --request REQUEST [--timeout TIMEOUT]
                      [--max-searches MAX_SEARCHES]
                      [--segment-limit SEGMENT_LIMIT]
                      [--live-cache-ttl LIVE_CACHE_TTL] [--no-live-cache]
                      [--fail-fast]

options:
  -h, --help            show this help message and exit
  --request REQUEST     flight_search_request.v1 JSON file, or - for stdin.
  --timeout TIMEOUT     Provider request timeout, seconds.
  --max-searches MAX_SEARCHES
                        Maximum provider attempts for one search.
  --segment-limit SEGMENT_LIMIT
                        Maximum offers pulled from one probe.
  --live-cache-ttl LIVE_CACHE_TTL
                        Live provider cache TTL, seconds. Zero disables reuse.
  --no-live-cache       Bypass the live provider cache.
  --fail-fast           Stop on the first provider failure.
""",
    (
        "maint",
        "check",
    ): """usage: flights maint check [-h] [--runtime-path RUNTIME_PATH]

options:
  -h, --help            show this help message and exit
  --runtime-path RUNTIME_PATH
                        Runtime flight-search skill path to compare against.
                        Defaults to ~/.hermes/skills/travel/flight-search.
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
        "schema_version": "flight_search_request.v1",
        "origin": overrides.pop("origin", "SVX"),
        "destination": overrides.pop("destination", "DEL"),
        "depart_date": overrides.pop("depart_date", "2026-06-01"),
        "return_date": overrides.pop("return_date", None),
        "currency": overrides.pop("currency", "RUB"),
        "provider_policy": overrides.pop("provider_policy", "kupibilet"),
    }
    for name in ("max_connections", "preferred_connections"):
        if name in overrides:
            value = overrides.pop(name)
            if value is not None:
                request[name] = value
    adapter = getattr(search_app, "search_request_from_payload", None)
    if not callable(adapter):
        raise AssertionError(
            "search app must expose search_request_from_payload as the canonical search adapter"
        )
    options = adapter(request)
    args = argparse.Namespace(
        command_name="search",
        provider_policy=options.provider_policy,
        max_connections=options.route.max_connections,
        preferred_connections=options.route.preferred_connections,
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
        self.assertEqual(len(COMMAND_SPECS), 7)
        self.assertEqual(set(leaves), set(specs_by_name))
        policy_commands = (
            set(AGENT_COMMANDS)
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
        depart = future_departure_date()
        args = live_search_args(
            destination="LON",
            depart_date=depart.isoformat(),
            provider_policy="kupibilet",
        )

        self.assertEqual(args.command_name, "search")
        self.assertEqual(args.provider_policy, "kupibilet")

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
            payload["data"]["skill"], {"name": "flight-search", "version": "0.14.0"}
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

    def test_leaf_json_flag_is_accepted_without_argv_rewrite(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["search", "--request", "request.json", "--json"])

        self.assertTrue(args.json)
        self.assertEqual(args.command_name, "search")


if __name__ == "__main__":
    unittest.main()
