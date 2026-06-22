"""Internal route inference helpers for booking URLs."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from flight_calendar.errors import CliFailure


def read_private_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise CliFailure(f"input file not found: {path}", code="usage_error") from exc


def first_url_from_args(args: argparse.Namespace) -> str | None:
    url = getattr(args, "url", None)
    url_file = getattr(args, "url_file", None)
    if url:
        raise CliFailure("--url is not supported; use --url-file", code="usage_error")
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
        details={"route": route, "required_disambiguation": ["provide a carrier booking URL via --url-file"]},
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
        details={"required_disambiguation": ["provide a supported carrier booking URL via --url-file"]},
    )
