from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from flights_cli.cli import apply_agent_brief_output, apply_agent_mode_defaults, build_parser, normalize_global_json
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


class CliContractTests(unittest.TestCase):
    def test_default_live_search_cache_ttl_is_30_minutes(self) -> None:
        from flights_cli.config import DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS

        self.assertEqual(DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, 30 * 60)

    def test_route_commands_default_same_airport_minimum_is_120(self) -> None:
        parser = build_parser()
        cases = [
            ["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20"],
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

    def test_su_flights_legacy_command_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["su-flights", "SVX", "SVO", "--depart-date", "2026-07-19"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_u6_prices_standalone_probe_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["u6-prices", "SVX", "IST", "--from-date", "2026-07-19"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_subprocess_test_env_disables_bytecode_writes(self) -> None:
        self.assertEqual(TEST_ENV["PYTHONDONTWRITEBYTECODE"], "1")

    def test_json_doctor_envelope(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "--json", "doctor"],
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
        self.assertEqual(payload["command"], "doctor")
        self.assertEqual(payload["issues"], [])
        self.assertEqual(payload["data"]["cli"], {"name": "flights-cli", "version": "0.10.13"})
        self.assertEqual(payload["data"]["skill"], {"name": "flight-search", "version": "0.10.13"})
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
        })
        self.assertEqual(payload["data"]["safety"], {
            "booking_or_purchase": False,
            "docker_touched": False,
            "live_provider_commands": ["kb-search", "kb-roundtrip", "fli-search", "fli-dates", "route kb-assemble", "route live-assemble"],
        })
        self.assertEqual([item["code"] for item in payload["data"]["default_route_hubs"]], list(DEFAULT_ROUTE_HUBS))
        self.assertNotIn("routes", payload["data"]["cache_counts"])

        human_proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "doctor"],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("flights 0.10.13 (skill flight-search 0.10.13)", human_proc.stdout)
        self.assertIn("main live commands: kb-search, kb-roundtrip, fli-search, fli-dates, route kb-assemble, route live-assemble", human_proc.stdout)
        self.assertIn("default hubs: IST, DXB, DOH", human_proc.stdout)

    def test_auto_hubs_flag_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20", "--auto-hubs"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("unrecognized arguments: --auto-hubs", stderr.getvalue())

    def test_route_plan_direct_only_flag_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20", "--direct-only"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("unrecognized arguments: --direct-only", stderr.getvalue())

    def test_legacy_agent_mode_sets_compact_live_assembly_defaults(self) -> None:
        args = build_parser().parse_args(
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--agent-mode"]
        )

        apply_agent_mode_defaults(args)

        self.assertTrue(args.agent_report)
        self.assertEqual(args.include_candidates, 0)
        self.assertEqual(args.include_ranked_candidates, 5)
        self.assertEqual(args.include_rejected_pairs, 5)
        self.assertEqual(args.include_segment_results, 0)
        self.assertEqual(args.max_candidates, 10)
        self.assertEqual(args.aggregate_control_limit, 10)

    def test_agent_mode_preserves_compact_carrier_aggregate_default(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "DEL",
                "--depart-date",
                "2026-06-01",
                "--agent-mode",
                "--aggregate-control-carrier",
                "SU",
            ]
        )

        apply_agent_mode_defaults(args)

        self.assertEqual(args.aggregate_control_limit, 10)

    def test_agent_report_is_report_attachment_without_output_or_evidence_side_effects(self) -> None:
        args = build_parser().parse_args(
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--agent-report"]
        )

        apply_agent_mode_defaults(args)

        self.assertFalse(args.agent_mode)
        self.assertTrue(args.agent_report)
        self.assertEqual(args.include_candidates, 5)
        self.assertEqual(args.include_ranked_candidates, 5)
        self.assertEqual(args.include_rejected_pairs, 20)
        self.assertEqual(args.include_segment_results, 0)
        self.assertEqual(args.max_candidates, 50)
        self.assertEqual(args.aggregate_control_limit, 0)

    def test_agent_brief_trims_payload_without_agent_mode_or_evidence_side_effects(self) -> None:
        args = build_parser().parse_args(
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--agent-brief"]
        )

        apply_agent_mode_defaults(args)
        trimmed = apply_agent_brief_output(
            args,
            {
                "agent_report": {"answer_lines": ["ok"]},
                "ranked": [{"id": "noisy"}],
                "candidates": [{"id": "raw"}],
            },
        )

        self.assertFalse(args.agent_mode)
        self.assertTrue(args.agent_report)
        self.assertEqual(args.aggregate_control_limit, 0)
        self.assertEqual(args.include_candidates, 5)
        self.assertEqual(args.max_candidates, 50)
        self.assertEqual(trimmed, {"agent_report": {"answer_lines": ["ok"]}})

    def test_agent_brief_preserves_explicit_stop_policy_evidence_scope(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "DEL",
                "--depart-date",
                "2026-06-01",
                "--stop-policy",
                "debug-all",
                "--agent-brief",
            ]
        )

        apply_agent_mode_defaults(args)
        policy = stop_policy_from_args(args)

        self.assertFalse(args.agent_mode)
        self.assertTrue(args.agent_report)
        self.assertEqual(policy.name, "debug_all")
        self.assertFalse(policy.suppress_three_plus)

    def test_cli_does_not_add_public_output_taxonomy_flags(self) -> None:
        parser = build_parser()
        rejected_flag_cases = [
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--format", "agent-json"],
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--evidence", "verified"],
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--report-level", "agent"],
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--output-profile", "human"],
        ]
        for argv in rejected_flag_cases:
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
                    parser.parse_args(argv)
                self.assertEqual(ctx.exception.code, 2)

    def test_json_route_plan_envelope_and_repeatable_hubs(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "plan",
                "SVX",
                "LON",
                "--depart-date",
                "2026-07-20",
                "--hub",
                "IST",
                "--hub",
                "DXB",
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
        self.assertEqual(payload["command"], "route plan")
        data = payload["data"]
        self.assertEqual(data["hubs"], ["IST", "DXB"])
        self.assertEqual(data["destination_airports"], ["LHR", "LGW"])
        self.assertEqual(data["airport_scope"]["destination"]["excluded_by_default"], ["STN", "LTN"])
        self.assertEqual(data["metrics"]["segment_request_count"], 6)
        self.assertNotIn("manual_links", data)
        self.assertNotIn("manual_direct_links", data["metrics"].get("without_cli", {}))
        self.assertIn("warnings", data)
        self.assertNotIn("cache_age_minutes", data)

    def test_normalize_global_json_accepts_trailing_json(self) -> None:
        argv = ["flights", "route", "plan", "SVX", "LON", "--json"]
        self.assertEqual(normalize_global_json(argv), ["flights", "--json", "route", "plan", "SVX", "LON"])


if __name__ == "__main__":
    unittest.main()
