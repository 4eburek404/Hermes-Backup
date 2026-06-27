from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from flights_cli.apps import search as search_app
from flights_cli.cli import apply_agent_brief_output, apply_agent_output_defaults, build_parser, normalize_global_json
from flights_cli.command_surface import (
    CATALOG_AUTO_REFRESH_COMMANDS,
    CATALOG_READ_COMMANDS,
    CATALOG_REFRESH_COMMANDS,
    DIAGNOSTIC_COMMANDS,
    LIVE_PROVIDER_COMMANDS,
    PRIMARY_ROUTE_COMMAND,
    TARGETED_PROBE_COMMANDS,
)
from flights_cli.config import DEFAULT_ROUTE_HUBS
from flights_cli.domain.stop_policy import stop_policy_from_args

from helpers import PROJECT, TEST_ENV, parser_leaf_defaults

def _dash(*parts: str) -> str:
    return "-".join(parts)


def _command_label(*parts: str) -> str:
    return " ".join(parts)


REMOVED_COMMAND_CASES = {
    _command_label("route", _dash("live", "assemble")): ["route", _dash("live", "assemble"), "SVX", "LON", "--depart-date", "2026-07-20"],
    _command_label("route", _dash("kb", "assemble")): ["route", _dash("kb", "assemble"), "SVX", "LON", "--depart-date", "2026-07-20"],
    _command_label("route", "plan"): ["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20"],
    "kb-search": ["kb-search", "SVX", "MOW", "--depart-date", "2026-07-19"],
    "kb-roundtrip": ["kb-roundtrip", "SVX", "BJS", "--depart-date", "2026-08-01", "--return-date", "2026-08-08"],
    "fli-search": ["fli-search", "IST", "LHR", "--depart-date", "2026-07-20"],
    "fli-dates": ["fli-dates", "IST", "LHR", "--from-date", "2026-07-20", "--to-date", "2026-07-22"],
}


def live_search_args(**overrides: object) -> argparse.Namespace:
    agent_report = bool(overrides.pop("agent_report", True))
    request = {
        "schema_version": "flight_search_request.v1",
        "origin": overrides.pop("origin", "SVX"),
        "destination": overrides.pop("destination", "DEL"),
        "depart_date": overrides.pop("depart_date", "2026-06-01"),
        "return_date": overrides.pop("return_date", None),
        "currency": overrides.pop("currency", "RUB"),
        "profile": overrides.pop("profile", "business"),
        "ticketing": overrides.pop("ticketing", "separate"),
        "provider_policy": overrides.pop("provider_policy", "kupibilet"),
        "route_options": {
            "stop_policy": overrides.pop("stop_policy", "business-default"),
            "max_connections": overrides.pop("max_connections", None),
            "tier2_max_connections": overrides.pop("tier2_max_connections", None),
        },
        "output": {
            "agent_brief": overrides.pop("agent_brief", False),
            "include_candidates": overrides.pop("include_candidates", 5),
            "include_ranked_candidates": overrides.pop("include_ranked_candidates", 5),
            "include_rejected_pairs": overrides.pop("include_rejected_pairs", 20),
            "include_segment_results": overrides.pop("include_segment_results", 0),
            "max_candidates": overrides.pop("max_candidates", 50),
        },
        "evidence": {
            "aggregate_control_limit": overrides.pop("aggregate_control_limit", 0),
        },
    }
    adapter = getattr(search_app, "live_assembly_options_from_search_request", None)
    if not callable(adapter):
        raise AssertionError("search app must expose live_assembly_options_from_search_request as the canonical search adapter")
    options = adapter(request)
    args = argparse.Namespace(
        command_name=options.command_name,
        provider_policy=options.evidence.provider_policy,
        aggregate_control_limit=options.evidence.aggregate_control_limit,
        ticketing=options.ticketing,
        profile=options.profile,
        stop_policy=options.route.stop_policy,
        max_connections=options.route.max_connections,
        tier2_max_connections=options.route.tier2_max_connections,
        limit_per_pair=options.output.limit_per_pair,
        max_candidates=options.output.max_candidates,
        include_candidates=options.output.include_candidates,
        include_ranked_candidates=options.output.include_ranked_candidates,
        include_rejected_pairs=options.output.include_rejected_pairs,
        include_segment_results=options.output.include_segment_results,
        agent_brief=options.output.agent_brief,
        agent_report=agent_report,
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

    def test_route_commands_default_same_airport_minimum_is_120(self) -> None:
        parser = build_parser()
        cases = [
            ["route", "validate"],
            ["route", "rank"],
            ["route", "assemble"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(args.min_same_airport_min, 120)
                self.assertEqual(args.min_cross_airport_min, 300)
        assemble_args = parser.parse_args(["route", "assemble"])
        self.assertEqual(assemble_args.limit_per_pair, 10)

    def test_active_command_surface_is_registered_with_leaf_dispatch(self) -> None:
        leaves = parser_leaf_defaults(build_parser())
        policy_commands = (
            set(DIAGNOSTIC_COMMANDS)
            | set(LIVE_PROVIDER_COMMANDS)
            | set(CATALOG_READ_COMMANDS)
            | set(CATALOG_REFRESH_COMMANDS)
        )
        self.assertTrue(policy_commands.issubset(leaves))
        self.assertIn(PRIMARY_ROUTE_COMMAND, leaves)
        for command_name, defaults in leaves.items():
            with self.subTest(command_name=command_name):
                self.assertEqual(defaults.get("command_name"), command_name)
                self.assertTrue(callable(defaults.get("func")))

    def test_removed_legacy_commands_are_not_registered(self) -> None:
        parser = build_parser()

        for command_name, argv in REMOVED_COMMAND_CASES.items():
            with self.subTest(command_name=command_name):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parser.parse_args(argv)

    def test_docs_smoke_commands_parse(self) -> None:
        parser = build_parser()
        docs_argv = {
            "search --request": ["--json", "search", "--request", "/tmp/flight-search-request.json"],
            "diagnose plan --request": ["--json", "diagnose", "plan", "--request", "/tmp/flight-search-request.json"],
            "maint doctor": ["--json", "maint", "doctor"],
            "maint check": ["--json", "maint", "check"],
            "cities search": ["--json", "cities", "search", "Yekaterinburg"],
            "airports explain": ["--json", "airports", "explain", "SVX", "MOW"],
            "route assemble": ["--json", "route", "assemble", "--input", "segment-results.json"],
            "route rank": ["--json", "route", "rank", "--input", "candidates.json"],
            "route validate": ["--json", "route", "validate", "--input", "itinerary.json"],
        }

        for label, argv in docs_argv.items():
            with self.subTest(label=label):
                self.assertTrue(callable(parser.parse_args(argv).func))

    def test_docs_name_current_canonical_path_and_diagnostic_plan(self) -> None:
        skill_text = (PROJECT.parent / "SKILL.md").read_text(encoding="utf-8")
        readme_text = (PROJECT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 -m flights_cli --json search --request", skill_text)
        self.assertIn("python3 -m flights_cli --json search --request", readme_text)
        self.assertIn("python3 -m flights_cli --json diagnose plan --request", readme_text)
        removed_live = _command_label("route", _dash("live", "assemble"))
        removed_plan = _command_label("route", "plan")
        self.assertNotIn(removed_live, skill_text)
        self.assertNotIn(removed_live, readme_text)
        self.assertNotIn(removed_plan, skill_text)
        self.assertNotIn(removed_plan, readme_text)

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
                self.assertEqual(leaves[command_name].get("catalog_access"), "refresh_explicit")

    def test_metadata_commands_report_metadata_only_evidence_scope(self) -> None:
        commands = {
            "cities search": ["--json", "cities", "search", "Yekaterinburg"],
            "airports explain": ["--json", "airports", "explain", "SVX", "MOW"],
            "maint catalog manifest": ["--json", "maint", "catalog", "manifest"],
            "maint catalog refresh": ["--json", "maint", "catalog", "refresh", "--dry-run"],
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
                self.assert_metadata_only_evidence_scope(payload["data"]["evidence_scope"])
                if "catalog_auto_refresh" in payload["data"]:
                    self.assert_metadata_only_evidence_scope(payload["data"]["catalog_auto_refresh"]["evidence_scope"])

    def test_search_request_accepts_explicit_kupibilet_provider_policy(self) -> None:
        args = live_search_args(destination="LON", depart_date="2026-07-20", provider_policy="kupibilet")

        self.assertEqual(args.command_name, "search")
        self.assertEqual(args.provider_policy, "kupibilet")
        self.assertEqual(args.limit_per_pair, 10)
        self.assertEqual(args.stop_policy, "business-default")
        self.assertEqual(args.profile, "business")

    def test_subprocess_test_env_disables_bytecode_writes(self) -> None:
        self.assertEqual(TEST_ENV["PYTHONDONTWRITEBYTECODE"], "1")

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
        self.assertEqual(payload["data"]["cli"], {"name": "flights-cli", "version": "0.5.8"})
        self.assertEqual(payload["data"]["skill"], {"name": "flight-search", "version": "0.8.8"})
        self.assertEqual(set(payload["data"]), {
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
            "route_intel_cache",
            "runtime_evidence_policy",
            "safety",
            "skill",
            "version",
            "version_manifest",
        })
        self.assertEqual(payload["data"]["version_manifest"]["mismatches"], [])
        self.assertEqual(payload["data"]["safety"], {
            "booking_or_purchase": False,
            "docker_touched": False,
            "primary_route_command": PRIMARY_ROUTE_COMMAND,
            "targeted_probe_commands": list(TARGETED_PROBE_COMMANDS),
            "live_provider_commands": list(LIVE_PROVIDER_COMMANDS),
        })
        self.assertEqual(payload["data"]["catalog_auto_refresh_policy"]["applies_to"], list(CATALOG_AUTO_REFRESH_COMMANDS))
        self.assertEqual(payload["data"]["catalog_auto_refresh_policy"]["max_age"], "2w")
        self.assertEqual(payload["data"]["catalog_auto_refresh_policy"]["max_age_seconds"], 14 * 24 * 60 * 60)
        self.assertEqual([item["code"] for item in payload["data"]["default_route_hubs"]], list(DEFAULT_ROUTE_HUBS))
        self.assertEqual(set(payload["data"]["cache_counts"]), {"airlines", "airports", "alliances", "cities", "countries", "planes"})

        human_proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "maint", "doctor"],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(human_proc.stderr, "")
        self.assertFalse(human_proc.stdout.lstrip().startswith("{"))
        self.assertLessEqual(len([line for line in human_proc.stdout.splitlines() if line.strip()]), 12)

    def test_invalid_catalog_refresh_env_is_json_validation_error_for_all_commands(self) -> None:
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

    def test_agent_report_is_report_attachment_without_output_or_evidence_side_effects(self) -> None:
        args = live_search_args(agent_report=True)

        apply_agent_output_defaults(args)

        self.assertTrue(args.agent_report)
        self.assertEqual(args.include_candidates, 5)
        self.assertEqual(args.include_ranked_candidates, 5)
        self.assertEqual(args.include_rejected_pairs, 20)
        self.assertEqual(args.include_segment_results, 0)
        self.assertEqual(args.max_candidates, 50)
        self.assertEqual(args.aggregate_control_limit, 0)

    def test_agent_brief_trims_payload_without_preset_side_effects(self) -> None:
        args = live_search_args(agent_brief=True)

        apply_agent_output_defaults(args)
        trimmed = apply_agent_brief_output(
            args,
            {
                "agent_report": {"answer_lines": ["ok"]},
                "ranked": [{"id": "noisy"}],
                "candidates": [{"id": "raw"}],
            },
        )

        self.assertTrue(args.agent_report)
        self.assertEqual(args.aggregate_control_limit, 0)
        self.assertEqual(args.include_candidates, 5)
        self.assertEqual(args.max_candidates, 50)
        self.assertEqual(trimmed, {"agent_report": {"answer_lines": ["ok"]}})

    def test_agent_brief_preserves_explicit_stop_policy_evidence_scope(self) -> None:
        args = live_search_args(stop_policy="debug-all", agent_brief=True)

        apply_agent_output_defaults(args)
        policy = stop_policy_from_args(args)

        self.assertTrue(args.agent_report)
        self.assertEqual(policy.name, "debug_all")
        self.assertFalse(policy.suppress_three_plus)

    def test_json_diagnose_plan_envelope_and_repeatable_hubs(self) -> None:
        request = {
            "schema_version": "flight_search_request.v1",
            "origin": "SVX",
            "destination": "LON",
            "depart_date": "2026-07-20",
            "route_options": {"hubs": ["IST", "DXB"], "routing_strategy": "hub-list"},
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
        self.assertEqual(payload["data"]["schema_version"], "flight_search_plan_diagnostic.v1")
        self.assert_metadata_only_evidence_scope(payload["data"]["evidence_scope"])
        data = payload["data"]["plan"]
        self.assertEqual(len(payload["data"]["segments"]), len(data["segments"]))
        self.assertEqual(len(payload["data"]["probe_specs"]), len(data["segments"]))
        first_probe = payload["data"]["probe_specs"][0]
        self.assertEqual(first_probe["probe_type"], "segment_direct")
        self.assertEqual(first_probe["provider_policy"], "auto")
        self.assertEqual(first_probe["currency"], "RUB")
        self.assertEqual(first_probe["filters"], {"only_carriers": [], "exclude_carriers": [], "prefer_carriers": [], "avoid_carriers": []})
        self.assertNotIn("command", first_probe)
        self.assertEqual(data["hubs"], ["IST", "DXB"])
        self.assertEqual(data["destination_airports"], ["LHR", "LGW"])
        self.assertEqual(data["airport_scope"]["destination"]["excluded_by_default"], ["STN", "LTN"])
        self.assertEqual(data["metrics"]["segment_search_count"], 10)
        self.assertEqual(data["segments"][0]["route_family"], "hub_list")
        self.assertEqual(data["segments"][0]["origin"], "SVX")
        self.assertEqual(data["segments"][0]["destination"], "IST")
        self.assertIn("warnings", data)

    def test_normalize_global_json_accepts_trailing_json(self) -> None:
        argv = ["flights", "diagnose", "plan", "--request", "request.json", "--json"]
        self.assertEqual(normalize_global_json(argv), ["flights", "--json", "diagnose", "plan", "--request", "request.json"])


if __name__ == "__main__":
    unittest.main()
