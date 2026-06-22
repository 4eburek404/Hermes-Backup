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

from jsonschema import Draft202012Validator

from flights_cli.apps import search as search_app
from flights_cli.cli import apply_agent_brief_output, apply_agent_output_defaults, build_parser, normalize_global_json
from flights_cli.command_surface import (
    CATALOG_AUTO_REFRESH_COMMANDS,
    CATALOG_READ_COMMANDS,
    CATALOG_REFRESH_COMMANDS,
    LIVE_PROVIDER_COMMANDS,
    PRIMARY_ROUTE_COMMAND,
    ROOT_COMMANDS,
    ROUTE_COMMANDS,
    TARGETED_PROBE_COMMANDS,
)
from flights_cli.config import DEFAULT_ROUTE_HUBS
from flights_cli.domain.stop_policy import stop_policy_from_args

from helpers import PROJECT, TEST_ENV


def load_doctor_envelope_schema() -> dict:
    schema_suffix = (
        Path("software-development")
        / "skill-audit-and-improvement"
        / "schemas"
        / "cli-doctor-envelope.v1.schema.json"
    )
    skill_roots = (Path("hermes") / "skills", Path("skills"))
    checked_candidates = []
    checked_bases = []

    for start in (PROJECT, Path.cwd().resolve()):
        for base in (start, *start.parents):
            if base not in checked_bases:
                checked_bases.append(base)

    for base in checked_bases:
        for skill_root in skill_roots:
            candidate = base / skill_root / schema_suffix
            checked_candidates.append(candidate)
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))

    checked = "\n".join(f"  - {candidate}" for candidate in checked_candidates)
    raise AssertionError(f"doctor envelope schema not found from {PROJECT}; checked:\n{checked}")


def subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


COMMAND_ARGV = {
    "cities search": ["cities", "search", "Yekaterinburg"],
    "airports explain": ["airports", "explain", "SVX"],
    "diagnose fli-search": ["diagnose", "fli-search", "IST", "LHR", "--depart-date", "2026-07-20"],
    "search": ["search", "--request", "request.json"],
    "diagnose plan": ["diagnose", "plan", "--request", "request.json"],
}

TARGETED_PROBE_ARGV = {
    "diagnose probe": ["diagnose", "probe", "--provider", "kupibilet", "--request", "probe.json"],
    "diagnose render": ["diagnose", "render", "--input", "agent_report.json"],
    "diagnose kb-search": ["diagnose", "kb-search", "SVX", "MOW", "--depart-date", "2026-07-19"],
    "diagnose kb-roundtrip": ["diagnose", "kb-roundtrip", "SVX", "BJS", "--depart-date", "2026-08-01", "--return-date", "2026-08-08"],
    "diagnose fli-dates": ["diagnose", "fli-dates", "IST", "LHR", "--from-date", "2026-07-20", "--to-date", "2026-07-22"],
}

DEV_ROUTE_ARGV = {
    "route assemble": ["route", "assemble", "--input", "segment-results.json"],
    "route rank": ["route", "rank", "--input", "candidates.json"],
    "route validate": ["route", "validate", "--input", "itinerary.json"],
}

CATALOG_REFRESH_ARGV = {
    "maint catalog refresh": ["maint", "catalog", "refresh", "--dry-run"],
}

def _dash(*parts: str) -> str:
    return "-".join(parts)


def _command_label(*parts: str) -> str:
    return " ".join(parts)


REMOVED_COMMAND_ARGV = {
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
        parser = build_parser()
        root = subparser_choices(parser)
        self.assertEqual(tuple(root), ROOT_COMMANDS)
        route = subparser_choices(root["route"])
        self.assertEqual(tuple(route), ROUTE_COMMANDS)

        for command_name, argv in COMMAND_ARGV.items():
            with self.subTest(command_name=command_name):
                args = parser.parse_args(argv)
                self.assertEqual(args.command_name, command_name)
                self.assertTrue(callable(args.func))
        for command_name, argv in TARGETED_PROBE_ARGV.items():
            with self.subTest(command_name=command_name):
                args = parser.parse_args(argv)
                self.assertEqual(args.command_name, command_name)
                self.assertTrue(callable(args.func))
        for command_name, argv in DEV_ROUTE_ARGV.items():
            with self.subTest(command_name=command_name):
                args = parser.parse_args(argv)
                self.assertEqual(args.command_name, command_name)
                self.assertTrue(callable(args.func))

    def test_removed_legacy_commands_are_not_registered(self) -> None:
        parser = build_parser()

        for command_name, argv in REMOVED_COMMAND_ARGV.items():
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

    def test_docs_name_current_golden_path_and_diagnostic_plan(self) -> None:
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
        parser = build_parser()
        self.assertEqual(set(CATALOG_READ_COMMANDS), set(COMMAND_ARGV))
        self.assertEqual(set(CATALOG_AUTO_REFRESH_COMMANDS), set(COMMAND_ARGV))
        self.assertEqual(set(CATALOG_REFRESH_COMMANDS), set(CATALOG_REFRESH_ARGV))
        for command_name in CATALOG_READ_COMMANDS:
            with self.subTest(command_name=command_name):
                args = parser.parse_args(COMMAND_ARGV[command_name])
                self.assertTrue(getattr(args, "requires_catalog", False))
                self.assertEqual(getattr(args, "catalog_access", None), "auto_refresh")
        for command_name in CATALOG_REFRESH_COMMANDS:
            with self.subTest(command_name=command_name):
                args = parser.parse_args(CATALOG_REFRESH_ARGV[command_name])
                self.assertEqual(getattr(args, "catalog_access", None), "refresh_explicit")

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
        doctor_schema = load_doctor_envelope_schema()
        Draft202012Validator.check_schema(doctor_schema)
        Draft202012Validator(doctor_schema).validate(payload)
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
        self.assertIn("flights 0.5.8 (skill flight-search 0.8.8)", human_proc.stdout)
        self.assertIn("primary route command: search", human_proc.stdout)
        self.assertIn("targeted probe commands: diagnose probe, diagnose kb-search, diagnose kb-roundtrip, diagnose fli-search, diagnose fli-dates", human_proc.stdout)
        self.assertIn("default hubs: IST, DXB, DOH", human_proc.stdout)

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
