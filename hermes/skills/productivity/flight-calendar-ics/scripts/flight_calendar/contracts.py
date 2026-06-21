"""Central registry for flight-calendar-ics CLI wire contracts.

This module is deliberately data-only: importing it must not touch network,
runtime skill state, or private booking values.  The single CLI entrypoint uses
these constants to keep its doctor output, parser choices, and JSON envelope
contract in sync.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "flight-calendar-ics-cli.v1"

BUNDLE_ROUTES = ["make", "aeroflot", "ural", "utair", "redwings"]
BUILD_ROUTE_CHOICES = ["auto", *BUNDLE_ROUTES]

COMMANDS = ["doctor", "build", "diagnose", "maint"]

COMMAND_SURFACES: dict[str, list[str]] = {
    "production": [
        "build auto",
    ],
    "diagnostic": [
        "diagnose doctor",
        "diagnose validate",
        "diagnose route-detect",
        "diagnose bundle-check",
        "diagnose privacy-check",
        "diagnose carrier-probe",
        "diagnose timezone inspect",
        "build make",
        "build aeroflot",
        "build ural",
        "build utair",
        "build redwings",
    ],
    "maintenance": [
        "maint doctor",
        "maint contracts",
        "maint source-runtime diff",
        "maint source-runtime-sync",
        "maint refs registry-check",
        "maint clean --dry-run",
        "maint audit",
        "maint timezone-catalog inspect",
    ],
}

CONTRACT_REGISTRY: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "wire_commands": COMMANDS,
    "build_routes": BUILD_ROUTE_CHOICES,
    "command_registry": COMMAND_SURFACES,
    "cli_envelope": {
        "schema_version": SCHEMA_VERSION,
        "schema_path": "schemas/cli-envelope.v1.schema.json",
    },
    "agent_contract": {
        "schema_version": SCHEMA_VERSION,
        "entrypoint": "scripts/flight_calendar_ics.py",
    },
}

_AGENT_CONTRACT_TEMPLATE: dict[str, Any] = {
    "normal_steps": [
        {
            "id": "collect_source",
            "instruction": "Use explicit evidence or already-supplied attachments/cache; do not ask again for retrievable ticket data.",
        },
        {
            "id": "run_one_command",
            "instruction": "Run exactly one --json build auto command for ordinary carrier URLs/canonical JSON. Use explicit build <route> only for diagnostics, tests, or when the user has already selected a route. The CLI owns route inference, the private output bundle, canonical artifact names, envelope persistence, and structural verification.",
        },
        {
            "id": "verify",
            "instruction": "Parse stdout handoff: ok=true, data.agent_handoff.no_further_action_needed=true, data.agent_handoff.media, data.agent_handoff.safe_summary (route, segments, segments_count, vevent_count, ics_mode). Use safe_summary.segments for flight details — no guessing. No terminal commands, file reads, or diagnostics are needed after build auto succeeds.",
        },
        {
            "id": "deliver",
            "instruction": "Send data.agent_handoff.media with data.agent_handoff.safe_summary only.",
        },
    ],
    "dispatch_matrix": [
        {
            "source": "carrier_url_or_canonical_itinerary_json",
            "command": "build",
            "route": "auto",
            "argv_template": ["--json", "build", "auto", "--url-file", "<PRIVATE_FILE_WITH_SOURCE_URL>"],
            "alternate_argv_template": ["--json", "build", "auto", "--input", "<PATH_TO_ITINERARY_JSON>"],
            "notes": ["Preferred happy path: let the CLI infer the route from a safe source fingerprint and return route_detection in the envelope."],
        },
        {
            "source": "canonical_itinerary_json_or_manual_normalization",
            "command": "build",
            "route": "make",
            "argv_template": ["--json", "build", "make", "--input", "<PATH_TO_ITINERARY_JSON>"],
        },
        {
            "source": "aeroflot_url_or_pnr_plus_surname",
            "command": "build",
            "route": "aeroflot",
            "argv_template": ["--json", "build", "aeroflot", "--url-file", "<PRIVATE_FILE_WITH_AEROFLOT_URL>"],
            "alternate_argv_template": ["--json", "build", "aeroflot", "--pnr-locator", "<PNR>", "--last-name", "<SURNAME>"],
            "notes": ["Prefer --url-file for private links; add --first-name only for ambiguous surname lookup."],
        },
        {
            "source": "ural_manage_booking_url_or_tracker_redirect",
            "command": "build",
            "route": "ural",
            "argv_template": ["--json", "build", "ural", "--url-file", "<PRIVATE_FILE_WITH_URAL_URL>"],
        },
        {
            "source": "utair_order_manage_url",
            "command": "build",
            "route": "utair",
            "argv_template": ["--json", "build", "utair", "--url-file", "<PRIVATE_FILE_WITH_UTAIR_URL>"],
        },
        {
            "source": "redwings_direct_find_url",
            "command": "build",
            "route": "redwings",
            "argv_template": ["--json", "build", "redwings", "--url-file", "<PRIVATE_FILE_WITH_RED_WINGS_FIND_URL>"],
            "anti_path": "Do not infer access keys from PNR/surname or already-opened order pages.",
        },
    ],
    "verification": {
        "envelope": [
            "schema_version=flight-calendar-ics-cli.v1",
            "ok=true",
            "command=build",
            "data.agent_handoff.ready=true",
            "data.agent_handoff.no_further_action_needed=true",
            "data.agent_handoff.artifact_inspection_required=false",
            "data.agent_handoff.safe_summary.verification_ok=true",
            "data.agent_handoff.safe_summary.ics_mode",
            "data.envelope_path points to the full diagnostic envelope",
        ],
        "reporting_fields": [
            "data.agent_handoff.media",
            "data.agent_handoff.safe_summary.route",
            "data.agent_handoff.safe_summary.route_detection_mode",
            "data.agent_handoff.safe_summary.segments",
            "data.agent_handoff.safe_summary.segments_count",
            "data.agent_handoff.safe_summary.vevent_count",
            "data.agent_handoff.safe_summary.ics_mode",
            "data.agent_handoff.safe_summary.verification_ok",
        ],
        "bundle": ["readable output directory", "itinerary.json readable", "flights.ics readable", "envelope.json readable", "VEVENT count equals segments_count", "VEVENT DTSTART/DTEND are absolute UTC Z timestamps", "no VTIMEZONE components required for flight events", "no TBD/UNKNOWN/None"],
    },
    "failure_path": {
        "steps": [
            "read_json_error_code",
            "keep_private_source_private",
            "do_not_switch_route_without_new_evidence",
            "run_diagnose_only_after_failure_or_explicit_request",
        ],
        "diagnostics_trigger": "build_auto_failed_or_user_requested_diagnostics",
        "route_switch_rule": "do_not_switch_route_without_new_evidence",
    },
    "diagnostics": {
        "commands": [
            "diagnose doctor",
            "diagnose route-detect",
            "diagnose validate",
            "diagnose bundle-check",
            "diagnose privacy-check",
            "diagnose timezone inspect",
        ],
        "write_performed": False,
    },
    "maintenance": {
        "commands": [
            "maint contracts",
            "maint source-runtime diff",
            "maint refs registry-check",
            "maint audit",
            "maint timezone-catalog inspect",
        ],
        "runtime_sync_requires_approval": True,
    },
    "privacy": {
        "chat_summary_must_omit": [
            "no_pnr_keys",
            "no_full_booking_urls",
            "no_passenger_names",
            "no_ticket_numbers",
            "no_document_contact_or_payment_data",
            "no_generated_ics_dump",
            "no_agent_owned_output_plumbing",
        ]
    },
}


def build_agent_contract() -> dict[str, Any]:
    """Return the stable agent contract shape used by doctor output."""
    return deepcopy(_AGENT_CONTRACT_TEMPLATE)


def build_command_registry() -> dict[str, list[str]]:
    """Return a copy of command-surface classifications for JSON output."""
    return deepcopy(COMMAND_SURFACES)
