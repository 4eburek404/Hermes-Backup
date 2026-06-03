#!/usr/bin/env python3
"""Single agent-facing CLI for flight-calendar-ics.

The CLI is intentionally a thin orchestrator around the skill's stdlib helper
modules. Its contract surface is the JSON envelope emitted with ``--json``:
future agents should parse that envelope instead of scraping human stdout.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import aeroflot_pnr_to_itinerary as aeroflot
import itinerary_contract
import make_flight_ics
import travelpayouts_airport_catalog as airport_catalog
import ural_airlines_to_itinerary as ural
import utair_to_itinerary as utair
import redwings_to_itinerary as redwings

SCHEMA_VERSION = "flight-calendar-ics-cli.v1"
BUNDLE_ROUTES = ["make", "aeroflot", "ural", "utair", "redwings"]
BUILD_ROUTE_CHOICES = ["auto", *BUNDLE_ROUTES]
COMMANDS = ["doctor", "validate", "make", "build", "aeroflot", "ural", "utair", "redwings"]
BUNDLE_ITINERARY_NAME = "itinerary.json"
BUNDLE_ICS_NAME = "flights.ics"
BUNDLE_ENVELOPE_NAME = "envelope.json"
AGENT_CONTRACT: dict[str, Any] = {
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
            "instruction": "Parse stdout or bundle/envelope.json; require schema_version, ok=true, data.segments_count>=1, data.ics_path, and data.verification.ok=true.",
        },
        {
            "id": "deliver",
            "instruction": "Send MEDIA:/absolute/path/flights.ics with a safe summary only.",
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
        "envelope": ["schema_version=flight-calendar-ics-cli.v1", "ok=true", "command=build", "data.segments_count>=1", "data.verification.ok=true"],
        "bundle": ["private output directory 0700", "itinerary.json 0600", "flights.ics 0600", "envelope.json 0600", "VEVENT count equals segments_count", "UTC DTSTART/DTEND ending Z", "no TBD/UNKNOWN/None"],
    },
    "privacy": {
        "chat_summary_must_omit": [
            "no_pnr_keys", "no_full_booking_urls", "no_passenger_names", "no_ticket_numbers", "no_document_contact_or_payment_data",
        ]
    },
}


class CliFailure(Exception):
    """Expected CLI failure that should become a machine-readable error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "validation_error",
        exit_code: int = 2,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}


def add_step(process: list[dict[str, Any]], step: str, status: str = "ok", **data: Any) -> None:
    item: dict[str, Any] = {"step": step, "status": status}
    if data:
        item.update(data)
    process.append(item)


def redact(text: str) -> str:
    """Redact known booking credentials without trying to identify names."""
    patterns = [
        (r"(?i)(pnrKey=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(pnr_key[\"'\s:=]+)[0-9a-f]{16,256}", r"\1[REDACTED]"),
        (r"(?i)(pnrLocator=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(pnr_locator[\"'\s:=]+)[A-Z0-9]{5,8}", r"\1[REDACTED]"),
        (r"(?i)(pnr=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(pnrNumber=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(lastName=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(rloc=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(last_name=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(filters(?:%5B|\[)locator(?:%5D|\])=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(filters(?:%5B|\[)passenger_lastname(?:%5D|\])=)[^&\s]+", r"\1[REDACTED]"),
        (r"(?i)(Authorization:\s*Bearer\s+)[^\s&]+", r"\1[REDACTED]"),
        (r"(?i)(#/find/)[^/\s]+/[^/\s]+(/Submit)", r"\1[REDACTED]/[REDACTED]\2"),
        (r"(?i)((?:access[-_ ]?key|access_code|finder_code)[\"'\s:=]+)[^\s&\"']+", r"\1[REDACTED]"),
        (r"(?i)([\"']secret[\"']\s*:\s*[\"'])[^\"']+([\"'])", r"\1[REDACTED]\2"),
        (r"(?i)(ticket=)\d{6,}", r"\1[REDACTED]"),
        (r"(?i)(ticket[_ -]?number[\"'\s:=]+)\d{6,}", r"\1[REDACTED]"),
        (r"\b\d{13}\b", "[REDACTED]"),
    ]
    out = text
    for pattern, repl in patterns:
        out = re.sub(pattern, repl, out)
    return out


def envelope(
    *,
    ok: bool,
    command: str,
    process: list[dict[str, Any]],
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "command": command,
        "process": process,
    }
    if ok:
        obj["data"] = data or {}
    else:
        obj["error"] = error or {"code": "unknown_error", "message": "unknown error"}
    return obj


def emit_json(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def emit_human(obj: dict[str, Any]) -> None:
    if obj["ok"]:
        data = obj.get("data") or {}
        print(f"OK: {obj['command']}")
        if "segments_count" in data:
            print(f"segments: {data['segments_count']}")
        if data.get("ics_path"):
            print(f"ics: {data['ics_path']}")
        if data.get("json_path"):
            print(f"json: {data['json_path']}")
    else:
        err = obj.get("error") or {}
        print(f"ERROR: {err.get('message', 'unknown error')}", file=sys.stderr)


def secure_write_text(path: Path, text: str) -> None:
    """Write sensitive itinerary artifacts as owner-only files."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    finally:
        try:
            os.chmod(path, 0o600)
        except FileNotFoundError:
            pass


def create_private_output_dir(output_dir: Path | None, process: list[dict[str, Any]]) -> Path:
    if output_dir is None:
        path = Path(tempfile.mkdtemp(prefix="flight-ics."))
    else:
        path = output_dir
        if path.exists() and not path.is_dir():
            raise CliFailure(f"output dir path exists and is not a directory: {path}", code="usage_error")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    add_step(process, "create_output_bundle")
    return path


def bundle_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "json": output_dir / BUNDLE_ITINERARY_NAME,
        "ics": output_dir / BUNDLE_ICS_NAME,
        "envelope": output_dir / BUNDLE_ENVELOPE_NAME,
    }


def file_mode(path: Path) -> str:
    return format(path.stat().st_mode & 0o777, "03o")


def require_private_mode(path: Path, expected: str = "600") -> None:
    try:
        mode = file_mode(path)
    except FileNotFoundError as exc:
        raise CliFailure(f"expected artifact does not exist: {path}") from exc
    if mode != expected:
        raise CliFailure(f"artifact {path} has mode {mode}; expected {expected}")


def read_private_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise CliFailure(f"input file not found: {path}", code="usage_error") from exc


def first_url_from_args(args: argparse.Namespace) -> str | None:
    url = getattr(args, "url", None)
    url_file = getattr(args, "url_file", None)
    if url and url_file:
        raise CliFailure("use either --url or --url-file, not both", code="usage_error")
    if url_file:
        text = read_private_text(url_file)
        if not text:
            raise CliFailure(f"url file is empty: {url_file}", code="usage_error")
        return text.splitlines()[0].strip()
    return url


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith(f".{suffix}")


def _safe_host_evidence(host: str) -> str | None:
    if _host_matches(host, "aeroflot.ru"):
        return "host:aeroflot.ru"
    if host == "service.uralairlines.ru":
        return "host:service.uralairlines.ru"
    if _host_matches(host, "uralairlines.ru"):
        return "host:uralairlines.ru"
    if _host_matches(host, "utair.ru"):
        return "host:utair.ru"
    if _host_matches(host, "flyredwings.com"):
        return "host:flyredwings.com"
    if _host_matches(host, "webskyx.com"):
        return "host:webskyx.com"
    return None


def _query_field_names(parsed: Any) -> list[str]:
    names = list(parse_qs(parsed.query, keep_blank_values=True).keys())
    fragment = parsed.fragment or ""
    if "?" in fragment:
        names.extend(parse_qs(fragment.split("?", 1)[1], keep_blank_values=True).keys())
    return _unique(names)


def _field_present(field_names: list[str], aliases: set[str]) -> bool:
    lower_names = {name.lower() for name in field_names}
    return any(alias.lower() in lower_names for alias in aliases)


def _field_evidence(field_names: list[str], aliases: set[str]) -> list[str]:
    out: list[str] = []
    alias_lowers = {alias.lower() for alias in aliases}
    for name in field_names:
        if name.lower() in alias_lowers:
            out.append(f"query_field:{name}")
    return out


def _merge_evidence(existing: dict[str, list[str]], route: str, evidence: list[str]) -> None:
    existing[route] = _unique([*existing.get(route, []), *[item for item in evidence if item]])


def _related_urls(raw_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if not value:
            return
        candidate = value.strip()
        if not candidate or candidate in seen:
            return
        seen.add(candidate)
        urls.append(candidate)

    add(raw_url)
    index = 0
    while index < len(urls) and len(urls) < 6:
        parsed = urlparse(urls[index])
        for values in parse_qs(parsed.query, keep_blank_values=True).values():
            for value in values:
                decoded = unquote(value).strip()
                if decoded.startswith(("http://", "https://")):
                    add(decoded)
        index += 1
    return urls


def _known_host_route(host: str) -> str | None:
    if _host_matches(host, "aeroflot.ru"):
        return "aeroflot"
    if _host_matches(host, "uralairlines.ru"):
        return "ural"
    if _host_matches(host, "utair.ru"):
        return "utair"
    if _host_matches(host, "flyredwings.com") or _host_matches(host, "webskyx.com"):
        return "redwings"
    return None


def _redwings_find_fragment(fragment: str) -> bool:
    return bool(re.match(r"^/?find/[^/]+/[^/]+/Submit/?$", fragment, flags=re.IGNORECASE))


def _redwings_order_fragment(fragment: str) -> bool:
    return bool(re.match(r"^/?booking/[^/]+/order/?$", fragment, flags=re.IGNORECASE))


def _aeroflot_field_evidence(field_names: list[str]) -> list[str]:
    if (
        _field_present(field_names, {"pnrKey"}) and _field_present(field_names, {"pnrLocator"})
    ) or (
        _field_present(field_names, {"pnr_key"}) and _field_present(field_names, {"pnr_locator"})
    ):
        return _field_evidence(field_names, {"pnrKey", "pnr_key", "pnrLocator", "pnr_locator"})
    return []


def _ural_field_evidence(field_names: list[str]) -> list[str]:
    if _field_present(field_names, {"pnr", "pnrNumber", "pnrnumber"}) and _field_present(
        field_names, {"lastName", "lastname", "surname"}
    ):
        return _field_evidence(field_names, {"pnr", "pnrNumber", "pnrnumber", "lastName", "lastname", "surname"})
    return []


def _utair_field_evidence(field_names: list[str], *, host_bound: bool) -> list[str]:
    locator_aliases = {"rloc", "RLOC", "pnr"} if host_bound else {"rloc", "RLOC"}
    surname_aliases = {"last_name", "lastName", "lastname", "surname"}
    if _field_present(field_names, locator_aliases) and _field_present(field_names, surname_aliases):
        return _field_evidence(field_names, locator_aliases | surname_aliases)
    return []


def _route_url_credential_evidence(route: str, field_names: list[str], fragment: str, *, host_bound: bool) -> list[str]:
    if route == "aeroflot":
        return _aeroflot_field_evidence(field_names)
    if route == "ural":
        return _ural_field_evidence(field_names)
    if route == "utair":
        return _utair_field_evidence(field_names, host_bound=host_bound)
    if route == "redwings" and _redwings_find_fragment(fragment):
        return ["fragment_route:redwings_find"]
    return []


def _url_fingerprints(raw_url: str) -> list[dict[str, Any]]:
    fingerprints: list[dict[str, Any]] = []
    for related_url in _related_urls(raw_url):
        parsed = urlparse(related_url)
        host = (parsed.hostname or "").lower()
        fragment = parsed.fragment or ""
        field_names = _query_field_names(parsed)
        host_evidence = _safe_host_evidence(host)
        fingerprints.append(
            {
                "known_host_route": _known_host_route(host),
                "host_evidence": host_evidence,
                "field_names": field_names,
                "fragment": fragment,
                "redwings_order_page": _redwings_order_fragment(fragment),
            }
        )
    return fingerprints


def _route_input_insufficient(route: str, message: str | None = None) -> CliFailure:
    default_message = f"{route} source fingerprint is known, but required route-specific credentials are missing"
    return CliFailure(
        message or default_message,
        code="route_input_insufficient",
        details={"route": route, "required_disambiguation": ["provide route-specific URL/arguments", "or use explicit build <route> for diagnostics"]},
    )


def _route_ambiguous(routes: list[str], *, required: str = "explicit route or carrier URL") -> CliFailure:
    return CliFailure(
        "source matches multiple route signatures",
        code="route_ambiguous",
        details={"safe_candidates": sorted(set(routes)), "required_disambiguation": [required]},
    )


def _detection(route: str, confidence: float, evidence: list[str]) -> dict[str, Any]:
    return {"mode": "auto", "route": route, "confidence": confidence, "evidence": _unique(evidence)}


def _explicit_arg_route_evidence(args: argparse.Namespace) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    if getattr(args, "pnr_locator", None) and (getattr(args, "pnr_key", None) or getattr(args, "last_name", None)):
        _merge_evidence(candidates, "aeroflot", ["arg:pnr_locator", "arg:pnr_key_or_last_name"])
    if getattr(args, "pnr", None) and getattr(args, "access_code", None):
        _merge_evidence(candidates, "redwings", ["arg:pnr", "arg:access_key"])
    if getattr(args, "rloc", None) and getattr(args, "last_name", None):
        _merge_evidence(candidates, "utair", ["arg:rloc", "arg:last_name"])
    if getattr(args, "pnr", None) and getattr(args, "last_name", None):
        _merge_evidence(candidates, "ural", ["arg:pnr", "arg:last_name"])
        if not getattr(args, "access_code", None):
            _merge_evidence(candidates, "utair", ["arg:pnr", "arg:last_name"])
    return candidates


def _global_url_route_evidence(fingerprints: list[dict[str, Any]]) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    for item in fingerprints:
        field_names = list(item["field_names"])
        fragment = str(item["fragment"])
        aeroflot_evidence = _aeroflot_field_evidence(field_names)
        if aeroflot_evidence:
            _merge_evidence(candidates, "aeroflot", aeroflot_evidence)
        if _redwings_find_fragment(fragment):
            _merge_evidence(candidates, "redwings", ["fragment_route:redwings_find"])
        ural_evidence = _ural_field_evidence(field_names)
        if ural_evidence:
            _merge_evidence(candidates, "ural", ural_evidence)
        if _field_present(field_names, {"pnr"}) and _field_present(field_names, {"lastName", "lastname", "surname"}):
            _merge_evidence(candidates, "utair", _field_evidence(field_names, {"pnr", "lastName", "lastname", "surname"}))
        utair_evidence = _utair_field_evidence(field_names, host_bound=False)
        if utair_evidence:
            _merge_evidence(candidates, "utair", utair_evidence)
    return candidates


def infer_build_route(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "input", None) is not None:
        return _detection("make", 1.0, ["input_kind:canonical_itinerary_json"])

    url = first_url_from_args(args)
    fingerprints = _url_fingerprints(url) if url else []
    known_host_evidence: dict[str, list[str]] = {}
    known_complete: dict[str, list[str]] = {}
    redwings_order_routes: set[str] = set()
    for item in fingerprints:
        route = item.get("known_host_route")
        if not route:
            continue
        host_evidence = [str(item["host_evidence"])] if item.get("host_evidence") else []
        _merge_evidence(known_host_evidence, str(route), host_evidence)
        credential_evidence = _route_url_credential_evidence(
            str(route), list(item["field_names"]), str(item["fragment"]), host_bound=True
        )
        if credential_evidence:
            _merge_evidence(known_complete, str(route), [*host_evidence, *credential_evidence])
        if route == "redwings" and item.get("redwings_order_page"):
            redwings_order_routes.add("redwings")

    if len(known_host_evidence) > 1:
        raise _route_ambiguous(list(known_host_evidence), required="single carrier URL")

    if len(known_host_evidence) == 1:
        route = next(iter(known_host_evidence))
        explicit_evidence = _explicit_arg_route_evidence(args).get(route, [])
        if route in known_complete or explicit_evidence:
            evidence = [*known_host_evidence[route], *known_complete.get(route, []), *explicit_evidence]
            return _detection(route, 1.0, evidence)
        if route == "redwings" and route in redwings_order_routes:
            raise _route_input_insufficient(
                route,
                "Red Wings order page URL is not enough; provide the direct find link shaped #/find/<PNR>/<ACCESS_KEY>/Submit.",
            )
        raise _route_input_insufficient(route)

    candidates = _global_url_route_evidence(fingerprints)
    for route, evidence in _explicit_arg_route_evidence(args).items():
        _merge_evidence(candidates, route, evidence)

    if len(candidates) == 1:
        route, evidence = next(iter(candidates.items()))
        return _detection(route, 0.9, evidence)
    if len(candidates) > 1:
        raise _route_ambiguous(list(candidates))

    if any(item.get("redwings_order_page") for item in fingerprints):
        raise _route_input_insufficient(
            "redwings",
            "Red Wings order page URL is not enough; provide the direct find link shaped #/find/<PNR>/<ACCESS_KEY>/Submit.",
        )
    raise CliFailure(
        "could not infer carrier route from safe source fingerprint",
        code="route_unknown",
        details={"required_disambiguation": ["provide build <route> explicitly", "or provide route-specific URL/arguments"]},
    )


def verify_bundle_artifacts(paths: dict[str, Path], segments_count: int, process: list[dict[str, Any]]) -> dict[str, Any]:
    require_private_mode(paths["json"])
    require_private_mode(paths["ics"])
    ics_text = paths["ics"].read_text(encoding="utf-8")
    make_flight_ics.validate_ics_text(ics_text, segments_count)
    event_count = ics_text.count("BEGIN:VEVENT")
    dt_lines = [line for line in ics_text.splitlines() if line.startswith(("DTSTART", "DTEND"))]
    non_utc = [line for line in dt_lines if not line.endswith("Z")]
    if non_utc:
        raise CliFailure("generated ICS contains DTSTART/DTEND values without UTC Z suffix")
    add_step(process, "verify_bundle", segments_count=segments_count)
    return {
        "ok": True,
        "event_count": event_count,
        "utc_datetime_count": len(dt_lines),
        "placeholder_free": True,
        "private_modes": {"json": file_mode(paths["json"]), "ics": file_mode(paths["ics"])},
    }


def build_make_bundle(args: argparse.Namespace, paths: dict[str, Path], process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    if args.input is None:
        raise CliFailure("build make requires --input", code="usage_error")
    data = make_flight_ics.load_input(args.input)
    add_step(process, "load_input")
    data = validate_itinerary_contract(data, process)
    ics_text, summaries = make_flight_ics.build_calendar(data, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(paths["json"], json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    secure_write_text(paths["ics"], ics_text)
    add_step(process, "write_ics", artifact="ics", mode="0600")
    return 0, {
        "segments_count": len(summaries),
        "segments": [safe_segment_summary(item) for item in summaries],
        "json_path": str(paths["json"]),
        "ics_path": str(paths["ics"]),
        "write_performed": True,
    }


def build_route_args(args: argparse.Namespace, paths: dict[str, Path]) -> argparse.Namespace:
    url = first_url_from_args(args)
    if args.route == "aeroflot":
        return argparse.Namespace(
            url=url,
            pnr_locator=args.pnr_locator,
            pnr_key=args.pnr_key,
            last_name=args.last_name,
            first_name=args.first_name,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
        )
    if args.route == "ural":
        return argparse.Namespace(
            url=url,
            pnr=args.pnr,
            last_name=args.last_name,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
            frontend_base=args.frontend_base,
        )
    if args.route == "utair":
        return argparse.Namespace(
            url=url,
            rloc=args.rloc,
            last_name=args.last_name,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
        )
    if args.route == "redwings":
        return argparse.Namespace(
            url=url,
            pnr=args.pnr,
            access_code=args.access_code,
            output_json=paths["json"],
            output_ics=paths["ics"],
            tz=args.tz,
            no_alarms=args.no_alarms,
            graphql_endpoint=args.graphql_endpoint,
        )
    raise CliFailure(f"unknown build route: {args.route}", code="usage_error")


def command_build(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    route = args.route
    route_detection: dict[str, Any] | None = None
    if route == "auto":
        try:
            route_detection = infer_build_route(args)
        except CliFailure as exc:
            add_step(process, "infer_route", "error", reason=exc.code)
            raise
        route = str(route_detection["route"])
        add_step(
            process,
            "infer_route",
            route=route,
            confidence=route_detection["confidence"],
            evidence=route_detection["evidence"],
        )

    output_dir = create_private_output_dir(args.output_dir, process)
    paths = bundle_paths(output_dir)
    route_args_source = argparse.Namespace(**vars(args))
    route_args_source.route = route
    if route == "make":
        exit_code, data = build_make_bundle(route_args_source, paths, process)
    else:
        route_args = build_route_args(route_args_source, paths)
        handlers: dict[str, Callable[[argparse.Namespace, list[dict[str, Any]]], tuple[int, dict[str, Any]]]] = {
            "aeroflot": command_aeroflot,
            "ural": command_ural,
            "utair": command_utair,
            "redwings": command_redwings,
        }
        exit_code, data = handlers[route](route_args, process)
    segments_count = int(data.get("segments_count") or 0)
    verification = verify_bundle_artifacts(paths, segments_count, process)
    bundled = dict(data)
    bundled.update(
        {
            "route": route,
            "output_dir": str(output_dir),
            "json_path": str(paths["json"]),
            "ics_path": str(paths["ics"]),
            "envelope_path": str(paths["envelope"]),
            "verification": verification,
        }
    )
    if route_detection is not None:
        bundled["route_detection"] = route_detection
    return exit_code, bundled


def write_envelope_artifact_if_requested(data: dict[str, Any], obj: dict[str, Any]) -> None:
    envelope_path = data.get("envelope_path")
    if envelope_path:
        secure_write_text(Path(envelope_path), json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def load_travelpayouts_airport_timezone_document(catalog_path: Path | None = None) -> dict[str, Any]:
    """Load the bundled minimal Travelpayouts airport timezone catalog document."""
    return airport_catalog.load_catalog_document(catalog_path)


def load_travelpayouts_airport_timezones(catalog_path: Path | None = None) -> dict[str, str]:
    """Load IATA -> IANA timezone data from the skill-bundled Travelpayouts asset."""
    return airport_catalog.load_airport_timezones(catalog_path)


def build_timezone_map(
    overrides: dict[str, str] | None = None,
    *,
    catalog_path: Path | None = None,
) -> dict[str, str]:
    """Build timezone map: bundled Travelpayouts catalog < explicit --tz overrides."""
    return airport_catalog.build_timezone_map(overrides, catalog_path=catalog_path)


def add_timezone_map_step(process: list[dict[str, Any]], catalog_timezones: dict[str, str], overrides_count: int) -> None:
    add_step(
        process,
        "load_timezone_map",
        defaults_count=0,
        catalog_source="skill-bundled-travelpayouts-airport-timezones",
        catalog_timezones_count=len(catalog_timezones),
        overrides_count=overrides_count,
    )


def safe_segment_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "flight_number": summary.get("flight_number"),
        "route": summary.get("route"),
        "dtstart_utc": summary.get("dtstart_utc"),
        "dtend_utc": summary.get("dtend_utc"),
    }


def validate_itinerary_contract(itinerary: dict[str, Any], process: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = itinerary_contract.normalize_legacy_itinerary(itinerary)
    try:
        itinerary_contract.validate_itinerary_schema(normalized)
    except ValueError:
        add_step(process, "validate_itinerary_schema", "error")
        raise
    add_step(process, "validate_itinerary_schema", schema_version=itinerary_contract.SCHEMA_VERSION)
    try:
        itinerary_contract.validate_itinerary_semantics(normalized)
    except ValueError:
        add_step(process, "validate_itinerary_semantics", "error")
        raise
    add_step(process, "validate_itinerary_semantics")
    return normalized


def build_and_validate(input_path: Path, *, no_alarms: bool, process: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    data = make_flight_ics.load_input(input_path)
    add_step(process, "load_input")
    data = validate_itinerary_contract(data, process)
    ics_text, summaries = make_flight_ics.build_calendar(data, no_alarms=no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    return ics_text, summaries


def command_doctor(_args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    add_step(process, "load_input", "skipped", reason="doctor has no itinerary input")
    data = {
        "entrypoint": str(Path(__file__).resolve()),
        "entrypoint_kind": "single-python-executable",
        "schema_version": SCHEMA_VERSION,
        "commands": COMMANDS,
        "legacy_scripts": [
            "scripts/make_flight_ics.py",
            "scripts/aeroflot_pnr_to_itinerary.py",
            "scripts/ural_airlines_to_itinerary.py",
            "scripts/utair_to_itinerary.py",
            "scripts/redwings_to_itinerary.py",
        ],
        "json_contract": {
            "ok": "boolean",
            "command": "string",
            "process": "ordered list of step/status objects",
            "data": "object when ok=true",
            "error": "object when ok=false",
        },
        "input_contract": {
            "schema_version": itinerary_contract.SCHEMA_VERSION,
            "schema_path": str(itinerary_contract.SCHEMA_PATH),
        },
        "sensitive_stdout_policy": "route/timestamp summaries only; no PNR keys, passenger names, ticket numbers, or full booking URLs",
        "agent_contract": AGENT_CONTRACT,
    }
    return 0, data


def command_validate(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    _ics_text, summaries = build_and_validate(args.input, no_alarms=args.no_alarms, process=process)
    add_step(process, "no_write")
    return 0, {
        "segments_count": len(summaries),
        "segments": [safe_segment_summary(item) for item in summaries],
        "write_performed": False,
    }


def command_make(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    ics_text, summaries = build_and_validate(args.input, no_alarms=args.no_alarms, process=process)
    output = args.output or args.input.with_suffix(".ics")
    secure_write_text(output, ics_text)
    add_step(process, "write_output", artifact="ics", mode="0600")
    return 0, {
        "segments_count": len(summaries),
        "segments": [safe_segment_summary(item) for item in summaries],
        "ics_path": str(output),
        "write_performed": True,
    }


def aeroflot_segments(itinerary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "flight_number": f.get("flight_number"),
            "route": f"{(f.get('departure') or {}).get('airport')}->{(f.get('arrival') or {}).get('airport')}",
            "departure_local": (f.get("departure") or {}).get("local"),
            "arrival_local": (f.get("arrival") or {}).get("local"),
        }
        for f in itinerary.get("flights", [])
    ]


def command_aeroflot(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, key, booking_url = aeroflot.resolve_pnr_source(
        args.url,
        args.pnr_locator,
        args.pnr_key,
        args.last_name,
        args.first_name,
    )
    add_step(process, "parse_pnr_source")
    timezone_overrides = aeroflot.parse_tz_overrides(args.tz)
    airport_catalog_timezones = load_travelpayouts_airport_timezones()
    tz_map = build_timezone_map(timezone_overrides)
    add_timezone_map_step(process, airport_catalog_timezones, len(args.tz))
    data = aeroflot.fetch_aeroflot_pnr(locator, key)
    add_step(process, "fetch_aeroflot_pnr")
    itinerary = aeroflot.convert_to_itinerary(data, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def command_ural(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, last_name, booking_url = ural.parse_ural_source(args.url, args.pnr, args.last_name)
    add_step(process, "parse_pnr_source")
    timezone_overrides = ural.parse_tz_overrides(args.tz)
    airport_catalog_timezones = load_travelpayouts_airport_timezones()
    tz_map = build_timezone_map(timezone_overrides)
    add_timezone_map_step(process, airport_catalog_timezones, len(args.tz))
    reservation = ural.fetch_ural_reservation(
        locator,
        last_name,
        booking_url=booking_url,
        frontend_base=args.frontend_base,
    )
    add_step(process, "fetch_ural_reservation")
    itinerary = ural.convert_to_itinerary(reservation, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def command_utair(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, last_name, booking_url = utair.parse_utair_source(args.url, args.rloc, args.last_name)
    add_step(process, "parse_pnr_source")
    timezone_overrides = utair.parse_tz_overrides(args.tz)
    airport_catalog_timezones = load_travelpayouts_airport_timezones()
    tz_map = build_timezone_map(timezone_overrides)
    add_timezone_map_step(process, airport_catalog_timezones, len(args.tz))
    token = utair.fetch_utair_token()
    add_step(process, "fetch_utair_token")
    orders = utair.fetch_utair_orders(locator, last_name, token=token)
    add_step(process, "fetch_utair_orders")
    itinerary = utair.convert_to_itinerary(orders, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def command_redwings(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    locator, finder_code, booking_url = redwings.parse_redwings_source(args.url, args.pnr, args.access_code)
    add_step(process, "parse_redwings_source")
    timezone_overrides = redwings.parse_tz_overrides(args.tz)
    airport_catalog_timezones = load_travelpayouts_airport_timezones()
    tz_map = build_timezone_map(timezone_overrides)
    add_timezone_map_step(process, airport_catalog_timezones, len(args.tz))
    order = redwings.fetch_redwings_order(locator, finder_code, graphql_endpoint=args.graphql_endpoint)
    add_step(process, "fetch_redwings_order")
    itinerary = redwings.convert_to_itinerary(order, tz_map, booking_url=booking_url)
    add_step(process, "convert_to_itinerary", segments_count=len(itinerary.get("flights", [])))
    itinerary = validate_itinerary_contract(itinerary, process)
    ics_text, summaries = make_flight_ics.build_calendar(itinerary, no_alarms=args.no_alarms)
    add_step(process, "build_calendar", segments_count=len(summaries))
    make_flight_ics.validate_ics_text(ics_text, len(summaries))
    add_step(process, "validate_ics")
    secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
    add_step(process, "write_json", artifact="json", mode="0600")
    ics_path = None
    if args.output_ics:
        secure_write_text(args.output_ics, ics_text)
        ics_path = str(args.output_ics)
        add_step(process, "write_ics", artifact="ics", mode="0600")
    else:
        add_step(process, "write_ics", "skipped", reason="--output-ics not supplied")
    return 0, {
        "segments_count": len(summaries),
        "segments": aeroflot_segments(itinerary),
        "json_path": str(args.output_json),
        "ics_path": ics_path,
        "write_performed": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single CLI entrypoint for the flight-calendar-ics skill.")
    parser.add_argument("--json", action="store_true", help="Emit the stable machine-readable JSON envelope")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Report CLI contract and available commands")

    validate = sub.add_parser("validate", help="Validate an itinerary JSON without writing an .ics file")
    validate.add_argument("--input", "-i", required=True, type=Path, help="Path to itinerary JSON")
    validate.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders while validating")

    make = sub.add_parser("make", help="Validate an itinerary JSON and write an .ics file")
    make.add_argument("--input", "-i", required=True, type=Path, help="Path to itinerary JSON")
    make.add_argument("--output", "-o", type=Path, help="Output .ics path; defaults to input basename")
    make.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")

    build = sub.add_parser("build", help="Create a private bundle: itinerary.json, flights.ics, envelope.json")
    build.add_argument("route", choices=BUILD_ROUTE_CHOICES, help="Source route to build from; use auto to let the CLI infer from input/source fingerprint")
    build.add_argument("--output-dir", type=Path, help="Optional bundle directory; defaults to a private /tmp/flight-ics.* directory")
    build.add_argument("--input", "-i", type=Path, help="Canonical itinerary JSON for build make")
    build.add_argument("--url", help="Carrier booking URL; prefer --url-file for private inputs")
    build.add_argument("--url-file", type=Path, help="Private file containing the carrier booking URL")
    build.add_argument("--pnr-locator", help="Aeroflot booking locator, if not using --url/--url-file")
    build.add_argument("--pnr-key", help="Aeroflot PNR key, if not using --url/--url-file")
    build.add_argument("--pnr", help="Carrier booking locator for Ural/Red Wings, if not using --url/--url-file")
    build.add_argument("--rloc", help="Utair booking locator, if not using --url/--url-file")
    build.add_argument("--last-name", help="Passenger surname for lookup routes")
    build.add_argument("--first-name", help="Passenger first name fallback for Aeroflot ambiguous surname lookup")
    build.add_argument("--access-key", dest="access_code", help="Red Wings access key, if not using --url/--url-file")
    build.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    build.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    build.add_argument("--frontend-base", help="Override Ural frontend base URL for diagnostics/tests")
    build.add_argument("--graphql-endpoint", help="Override Websky GraphQL endpoint for diagnostics/tests")

    aero = sub.add_parser("aeroflot", help="Fetch an Aeroflot PNR and write standard itinerary JSON, optionally .ics")
    aero.add_argument("--url", help="Aeroflot PNR share URL containing pnrKey and pnrLocator")
    aero.add_argument("--pnr-locator", help="Booking locator, if not using --url")
    aero.add_argument("--pnr-key", help="PNR key, if not using --url")
    aero.add_argument("--last-name", help="Passenger surname; used to generate pnr_key when --pnr-key/--url is absent")
    aero.add_argument("--first-name", help="Passenger first name fallback for ambiguous surname searches")
    aero.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    aero.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    aero.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    aero.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")

    ural_parser = sub.add_parser("ural", help="Fetch a Ural Airlines PNR and write standard itinerary JSON, optionally .ics")
    ural_parser.add_argument("--url", help="Ural Airlines manage-booking URL containing pnr and lastName")
    ural_parser.add_argument("--pnr", help="Booking locator, if not using --url")
    ural_parser.add_argument("--last-name", help="Passenger surname, if not using --url")
    ural_parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    ural_parser.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    ural_parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    ural_parser.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    ural_parser.add_argument("--frontend-base", help="Override Ural frontend base URL for diagnostics/tests")

    utair_parser = sub.add_parser("utair", help="Fetch a Utair PNR and write standard itinerary JSON, optionally .ics")
    utair_parser.add_argument("--url", help="Utair order-manage URL containing rloc and last_name")
    utair_parser.add_argument("--rloc", help="Booking locator, if not using --url")
    utair_parser.add_argument("--last-name", help="Passenger surname, if not using --url")
    utair_parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    utair_parser.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    utair_parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    utair_parser.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    redwings_parser = sub.add_parser("redwings", help="Fetch a Red Wings/Websky booking and write standard itinerary JSON, optionally .ics")
    redwings_parser.add_argument("--url", help="Red Wings direct email/manage link shaped #/find/<PNR>/<ACCESS_KEY>/Submit")
    redwings_parser.add_argument("--pnr", help="Booking locator, if not using --url")
    redwings_parser.add_argument("--access-key", dest="access_code", help="Access key from the direct email/manage link, if not using --url")
    redwings_parser.add_argument("--output-json", required=True, type=Path, help="Where to write itinerary JSON")
    redwings_parser.add_argument("--output-ics", type=Path, help="Optional .ics path to generate immediately")
    redwings_parser.add_argument("--tz", action="append", default=[], help="Timezone override CODE=Area/City; repeatable")
    redwings_parser.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    redwings_parser.add_argument("--graphql-endpoint", help="Override Websky GraphQL endpoint for diagnostics/tests")
    return parser


def run_command(args: argparse.Namespace, process: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    handlers: dict[str, Callable[[argparse.Namespace, list[dict[str, Any]]], tuple[int, dict[str, Any]]]] = {
        "doctor": command_doctor,
        "validate": command_validate,
        "make": command_make,
        "build": command_build,
        "aeroflot": command_aeroflot,
        "ural": command_ural,
        "utair": command_utair,
        "redwings": command_redwings,
    }
    handler = handlers.get(args.command)
    if handler is None:
        raise CliFailure(f"unknown command: {args.command}", code="usage_error")
    return handler(args, process)


def infer_command(argv: list[str]) -> str:
    for token in argv:
        if token in COMMANDS:
            return token
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv_list
    parser = build_parser()
    process: list[dict[str, Any]] = []
    stderr_buffer = io.StringIO()
    args: argparse.Namespace | None = None
    try:
        parse_redirect = contextlib.redirect_stderr(stderr_buffer) if json_mode else contextlib.nullcontext()
        with parse_redirect:
            args = parser.parse_args(argv_list)
        add_step(process, "parse_args")
        stderr_buffer = io.StringIO()
        redirect = contextlib.redirect_stderr(stderr_buffer) if args.json else contextlib.nullcontext()
        with redirect:
            exit_code, data = run_command(args, process)
        if args.json and data.get("envelope_path"):
            add_step(process, "write_envelope", artifact="envelope", mode="0600")
        add_step(process, "emit_json" if args.json else "emit_human")
        obj = envelope(ok=True, command=args.command, process=process, data=data)
        if args.json:
            write_envelope_artifact_if_requested(data, obj)
            emit_json(obj)
        else:
            emit_human(obj)
        return exit_code
    except CliFailure as exc:
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        add_step(process, "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        error_obj: dict[str, Any] = {"code": exc.code, "message": redact(str(exc))}
        for key in ("safe_candidates", "required_disambiguation"):
            if key in exc.details:
                error_obj[key] = exc.details[key]
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error=error_obj,
        )
        emit_json(obj) if active_json else emit_human(obj)
        return exc.exit_code
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        if code == 0:
            return 0
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        message = stderr_buffer.getvalue().strip() or str(exc) or "command failed"
        message = re.sub(r"^ERROR:\s*", "", message)
        add_step(process, "parse_args" if args is None else "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error={"code": "usage_error" if args is None else "validation_error", "message": redact(message)},
        )
        emit_json(obj) if active_json else emit_human(obj)
        return code
    except ValueError as exc:
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        add_step(process, "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error={"code": "validation_error", "message": redact(str(exc))},
        )
        emit_json(obj) if active_json else emit_human(obj)
        return 2
    except Exception as exc:  # pragma: no cover - defensive envelope for agents
        active_json = bool(json_mode if args is None else args.json)
        command = infer_command(argv_list) if args is None else getattr(args, "command", "unknown")
        add_step(process, "error", "error")
        add_step(process, "emit_json" if active_json else "emit_human")
        obj = envelope(
            ok=False,
            command=command,
            process=process,
            error={"code": "internal_error", "message": redact(f"{type(exc).__name__}: {exc}")},
        )
        emit_json(obj) if active_json else emit_human(obj)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
