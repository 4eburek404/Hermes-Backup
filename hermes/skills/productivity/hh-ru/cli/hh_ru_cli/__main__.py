#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from hh_ru_cli import __version__


DEFAULT_BASE_URL = "https://api.hh.ru"
DEFAULT_USER_AGENT = "hh-ru-cli/0.1 (+local-codex-tool)"
DEFAULT_CONFIG = Path.home() / ".hh-ru" / "config.json"


class CliError(Exception):
    def __init__(
        self,
        kind: str,
        message: str,
        *,
        status: int | None = None,
        details: Any = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.details = details
        self.exit_code = exit_code


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CliError("config_parse_error", f"Cannot parse config JSON: {path}", details=str(exc))


def write_json_file_private(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def load_context(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config).expanduser()
    config = read_json_file(config_path)
    token, token_source = resolve_token(args, config)
    return {
        "json": bool(args.json),
        "config_path": config_path,
        "config": config,
        "base_url": args.base_url or config.get("base_url") or DEFAULT_BASE_URL,
        "user_agent": args.user_agent or config.get("user_agent") or DEFAULT_USER_AGENT,
        "timeout": args.timeout,
        "token": token,
        "token_source": token_source,
    }


def resolve_token(args: argparse.Namespace, config: dict[str, Any]) -> tuple[str | None, str]:
    if getattr(args, "api_key", None):
        return args.api_key, "flag"
    for env_name in ("HH_API_TOKEN", "HH_RU_TOKEN"):
        value = os.environ.get(env_name)
        if value:
            return value, f"env:{env_name}"
    if config.get("api_token"):
        return str(config["api_token"]), "config"
    return None, "missing"


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    sensitive = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}
    out: dict[str, str] = {}
    for key, value in headers.items():
        out[key] = "***" if key.lower() in sensitive else value
    return out


def make_headers(ctx: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": ctx["user_agent"],
    }
    if ctx.get("token"):
        headers["Authorization"] = f"Bearer {ctx['token']}"
    return headers


def normalize_path(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        raise CliError("invalid_endpoint", "Pass API paths such as /vacancies, not full URLs")
    if not path.startswith("/"):
        path = "/" + path
    return path


def build_url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    clean_base = base_url.rstrip("/")
    clean_path = normalize_path(path)
    if not params:
        return clean_base + clean_path
    filtered = {k: v for k, v in params.items() if v is not None and v != []}
    query = urllib.parse.urlencode(filtered, doseq=True)
    return clean_base + clean_path + (("?" + query) if query else "")


def request_json(
    ctx: dict[str, Any],
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    method = method.upper()
    if method != "GET":
        raise CliError("unsupported_method", "This CLI currently exposes live raw requests for GET only")
    url = build_url(ctx["base_url"], path, params)
    headers = make_headers(ctx)
    request_info = {
        "method": method,
        "url": url,
        "headers": redact_headers(headers),
        "auth_source": ctx["token_source"],
    }
    if dry_run:
        return {"dry_run": True, "request": request_info}

    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=ctx["timeout"]) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                data = json.loads(text) if text else None
            except json.JSONDecodeError:
                raise CliError("response_parse_error", "API response was not valid JSON", details=text[:500])
            return {
                "status": resp.status,
                "headers": redact_headers(dict(resp.headers.items())),
                "data": data,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        details: Any = body[:1000]
        try:
            details = json.loads(body)
        except json.JSONDecodeError:
            pass
        raise CliError("api_error", f"hh.ru API returned HTTP {exc.code}", status=exc.code, details=details)
    except urllib.error.URLError as exc:
        raise CliError("network_error", "Network request failed", details=str(exc.reason))
    except TimeoutError:
        raise CliError("network_timeout", "Network request timed out")


def parse_kv(items: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise CliError("invalid_param", f"Expected key=value, got: {item}")
        key, value = item.split("=", 1)
        if not key:
            raise CliError("invalid_param", f"Empty parameter key in: {item}")
        if key in result:
            old = result[key]
            if isinstance(old, list):
                old.append(value)
            else:
                result[key] = [old, value]
        else:
            result[key] = value
    return result


def add_if(params: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        params[key] = value


def add_list(params: dict[str, Any], key: str, value: list[str] | None) -> None:
    if value:
        params[key] = value


def command_doctor(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    config_path: Path = ctx["config_path"]
    config_mode = None
    if config_path.exists():
        config_mode = oct(stat.S_IMODE(config_path.stat().st_mode))
    result: dict[str, Any] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "base_url": ctx["base_url"],
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "config_mode": config_mode,
        "token_available": bool(ctx.get("token")),
        "token_source": ctx["token_source"],
        "user_agent": ctx["user_agent"],
        "api_check": {"ran": False},
    }
    if args.check_api:
        started = time.monotonic()
        api = request_json(ctx, "GET", "/dictionaries")
        result["api_check"] = {
            "ran": True,
            "status": api["status"],
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    return result


def command_init(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    config_path: Path = ctx["config_path"]
    config = dict(ctx["config"])
    changed: list[str] = []
    if args.base_url:
        config["base_url"] = args.base_url
        changed.append("base_url")
    elif "base_url" not in config:
        config["base_url"] = DEFAULT_BASE_URL
        changed.append("base_url")
    if args.user_agent:
        config["user_agent"] = args.user_agent
        changed.append("user_agent")
    elif "user_agent" not in config:
        config["user_agent"] = DEFAULT_USER_AGENT
        changed.append("user_agent")
    if args.token:
        config["api_token"] = args.token
        changed.append("api_token")
    if args.client_id:
        config["client_id"] = args.client_id
        changed.append("client_id")
    if args.client_secret:
        config["client_secret"] = args.client_secret
        changed.append("client_secret")
    write_json_file_private(config_path, config)
    return {
        "config_path": str(config_path),
        "saved_fields": changed,
        "token_saved": "api_token" in changed,
        "client_secret_saved": "client_secret" in changed,
    }


def command_auth_url(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    config = ctx["config"]
    client_id = args.client_id or os.environ.get("HH_CLIENT_ID") or config.get("client_id")
    if not client_id:
        raise CliError("missing_client_id", "Provide --client-id, HH_CLIENT_ID, or config client_id")
    params = {
        "response_type": "code",
        "client_id": client_id,
    }
    add_if(params, "redirect_uri", args.redirect_uri)
    add_if(params, "state", args.state)
    add_if(params, "code_challenge", args.code_challenge)
    add_if(params, "code_challenge_method", args.code_challenge_method)
    url = "https://hh.ru/oauth/authorize?" + urllib.parse.urlencode(params)
    return {"url": url, "client_id_source": "arg" if args.client_id else ("env:HH_CLIENT_ID" if os.environ.get("HH_CLIENT_ID") else "config")}


def command_vacancies_search(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    add_if(params, "text", args.text)
    add_if(params, "area", args.area)
    add_if(params, "industry", args.industry)
    add_if(params, "professional_role", args.professional_role)
    add_if(params, "salary_from", args.salary_from)
    add_if(params, "salary_to", args.salary_to)
    add_if(params, "currency", args.currency)
    add_if(params, "experience", args.experience)
    add_if(params, "employment_type", args.employment_type)
    add_if(params, "employment_form", args.employment_form)
    add_if(params, "schedule", args.schedule)
    add_if(params, "work_format", args.work_format)
    add_if(params, "order_by", args.order_by)
    add_if(params, "page", args.page)
    add_if(params, "per_page", args.per_page)
    add_if(params, "search_field", args.search_field)
    add_if(params, "employer_id", args.employer_id)
    if args.only_with_salary:
        params["only_with_salary"] = "true"
    if args.premium:
        params["premium"] = "true"
    add_list(params, "label", args.label)
    params.update(parse_kv(args.param))
    return request_json(ctx, "GET", "/vacancies", params=params, dry_run=args.dry_run)


def command_get_path(ctx: dict[str, Any], args: argparse.Namespace, path: str) -> dict[str, Any]:
    params = parse_kv(getattr(args, "param", None))
    return request_json(ctx, "GET", path, params=params, dry_run=getattr(args, "dry_run", False))


def command_area_resolve(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    endpoint = f"/areas/{args.country_id}"
    if args.dry_run:
        return {
            "dry_run": True,
            "resolver": {
                "name": args.name,
                "country_id": args.country_id,
                "case_sensitive": False,
            },
            "request": request_json(ctx, "GET", endpoint, dry_run=True)["request"],
        }
    payload = request_json(ctx, "GET", endpoint)
    matches = []
    needle = args.name.lower()

    def walk(node: dict[str, Any], trail: list[str]) -> None:
        name = str(node.get("name", ""))
        current_trail = trail + ([name] if name else [])
        if needle in name.lower():
            matches.append({
                "id": node.get("id"),
                "name": name,
                "parent_id": node.get("parent_id"),
                "path": current_trail,
            })
        for child in node.get("areas") or []:
            if isinstance(child, dict):
                walk(child, current_trail)

    data = payload["data"]
    if isinstance(data, dict):
        walk(data, [])
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                walk(item, [])
    return {"query": args.name, "matches": matches[: args.limit], "count": len(matches)}


SUGGEST_ENDPOINTS = {
    "areas": "/suggests/areas",
    "companies": "/suggests/companies",
    "professional-roles": "/suggests/professional_roles",
    "skill-set": "/suggests/skill_set",
    "vacancy-search-keyword": "/suggests/vacancy_search_keyword",
    "vacancy-positions": "/suggests/vacancy_positions",
    "resume-search-keyword": "/suggests/resume_search_keyword",
    "positions": "/suggests/positions",
    "educational-institutions": "/suggests/educational_institutions",
    "fields-of-study": "/suggests/fields_of_study",
    "area-leaves": "/suggests/area_leaves",
}


SALARY_DICT_ENDPOINTS = {
    "areas": "/salary_statistics/dictionaries/salary_areas",
    "industries": "/salary_statistics/dictionaries/salary_industries",
    "professional-areas": "/salary_statistics/dictionaries/professional_areas",
    "employee-levels": "/salary_statistics/dictionaries/employee_levels",
}


def command_suggest(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    endpoint = SUGGEST_ENDPOINTS[args.kind]
    params = {"text": args.text}
    params.update(parse_kv(args.param))
    return request_json(ctx, "GET", endpoint, params=params, dry_run=args.dry_run)


def command_salary_dict(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return request_json(ctx, "GET", SALARY_DICT_ENDPOINTS[args.kind], dry_run=args.dry_run)


def command_raw_get(ctx: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    params = parse_kv(args.param)
    return request_json(ctx, "GET", args.path, params=params, dry_run=args.dry_run)


def emit(result: Any, *, command: str, json_mode: bool) -> None:
    envelope = {"ok": True, "command": command, "data": result}
    if json_mode:
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def emit_error(error: CliError, *, json_mode: bool) -> None:
    payload = {
        "ok": False,
        "error": {
            "type": error.kind,
            "message": error.message,
            "status": error.status,
            "details": error.details,
        },
    }
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    else:
        print(f"hh-ru: {error.kind}: {error.message}", file=sys.stderr)
        if error.details is not None:
            print(json.dumps(error.details, ensure_ascii=False, indent=2), file=sys.stderr)


def add_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="Print the request that would be made without calling hh.ru")


def add_params(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="Extra query parameter; repeat for multiple values")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hh-ru", description="Composable CLI for the hh.ru public API")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON envelope")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help=f"Config path (default: {DEFAULT_CONFIG})")
    parser.add_argument("--api-key", help="One-off API token; prefer HH_API_TOKEN/HH_RU_TOKEN or config")
    parser.add_argument("--base-url", help=f"API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--user-agent", help="User-Agent header; hh.ru rejects unset or blacklisted user agents")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Show config/auth status; no network unless --check-api")
    doctor.add_argument("--check-api", action="store_true", help="Call GET /dictionaries to verify endpoint reachability")
    doctor.set_defaults(func=command_doctor, command_name="doctor")

    init = sub.add_parser("init", help="Create or update ~/.hh-ru/config.json")
    init.add_argument("--token", help="Store API token in config; env vars are safer for normal use")
    init.add_argument("--client-id", help="Store OAuth client_id for auth authorize-url")
    init.add_argument("--client-secret", help="Store OAuth client_secret metadata; never printed")
    init.add_argument("--base-url", default=DEFAULT_BASE_URL)
    init.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    init.set_defaults(func=command_init, command_name="init")

    auth = sub.add_parser("auth", help="OAuth helper commands that do not exchange tokens")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_url = auth_sub.add_parser("authorize-url", help="Build hh.ru OAuth authorization URL without network")
    auth_url.add_argument("--client-id")
    auth_url.add_argument("--redirect-uri")
    auth_url.add_argument("--state")
    auth_url.add_argument("--code-challenge")
    auth_url.add_argument("--code-challenge-method", choices=["S256", "plain"])
    auth_url.set_defaults(func=command_auth_url, command_name="auth authorize-url")

    vacancies = sub.add_parser("vacancies", help="Search and read vacancies")
    vac_sub = vacancies.add_subparsers(dest="vacancies_command", required=True)
    vac_search = vac_sub.add_parser("search", help="GET /vacancies with common filters")
    vac_search.add_argument("text", nargs="?", help="Full-text search query")
    vac_search.add_argument("--area")
    vac_search.add_argument("--industry")
    vac_search.add_argument("--professional-role")
    vac_search.add_argument("--salary-from")
    vac_search.add_argument("--salary-to")
    vac_search.add_argument("--currency", default="RUR")
    vac_search.add_argument("--experience")
    vac_search.add_argument("--employment-type")
    vac_search.add_argument("--employment-form")
    vac_search.add_argument("--schedule")
    vac_search.add_argument("--work-format")
    vac_search.add_argument("--order-by")
    vac_search.add_argument("--page", type=int, default=0)
    vac_search.add_argument("--per-page", type=int, default=20)
    vac_search.add_argument("--search-field")
    vac_search.add_argument("--employer-id")
    vac_search.add_argument("--only-with-salary", action="store_true")
    vac_search.add_argument("--premium", action="store_true")
    vac_search.add_argument("--label", action="append")
    add_params(vac_search)
    add_dry_run(vac_search)
    vac_search.set_defaults(func=command_vacancies_search, command_name="vacancies search")

    vac_get = vac_sub.add_parser("get", help="GET /vacancies/{id}")
    vac_get.add_argument("id")
    add_params(vac_get)
    add_dry_run(vac_get)
    vac_get.set_defaults(func=lambda ctx, a: command_get_path(ctx, a, f"/vacancies/{a.id}"), command_name="vacancies get")

    vac_similar = vac_sub.add_parser("similar", help="GET /vacancies/{id}/similar_vacancies")
    vac_similar.add_argument("id")
    add_params(vac_similar)
    add_dry_run(vac_similar)
    vac_similar.set_defaults(func=lambda ctx, a: command_get_path(ctx, a, f"/vacancies/{a.id}/similar_vacancies"), command_name="vacancies similar")

    vac_related = vac_sub.add_parser("related", help="GET /vacancies/{id}/related_vacancies")
    vac_related.add_argument("id")
    add_params(vac_related)
    add_dry_run(vac_related)
    vac_related.set_defaults(func=lambda ctx, a: command_get_path(ctx, a, f"/vacancies/{a.id}/related_vacancies"), command_name="vacancies related")

    employers = sub.add_parser("employers", help="Read employers and their vacancies")
    emp_sub = employers.add_subparsers(dest="employers_command", required=True)
    emp_get = emp_sub.add_parser("get", help="GET /employers/{id}")
    emp_get.add_argument("id")
    add_params(emp_get)
    add_dry_run(emp_get)
    emp_get.set_defaults(func=lambda ctx, a: command_get_path(ctx, a, f"/employers/{a.id}"), command_name="employers get")

    emp_vac = emp_sub.add_parser("vacancies", help="GET /employers/{id}/vacancies")
    emp_vac.add_argument("id")
    emp_vac.add_argument("--page", type=int, default=0)
    emp_vac.add_argument("--per-page", type=int, default=20)
    add_dry_run(emp_vac)
    emp_vac.set_defaults(
        func=lambda ctx, a: request_json(ctx, "GET", f"/employers/{a.id}/vacancies", params={"page": a.page, "per_page": a.per_page}, dry_run=a.dry_run),
        command_name="employers vacancies",
    )

    areas = sub.add_parser("areas", help="Read and resolve area IDs")
    areas_sub = areas.add_subparsers(dest="areas_command", required=True)
    area_tree = areas_sub.add_parser("tree", help="GET /areas or /areas/{id}")
    area_tree.add_argument("--id", default=None, help="Area ID; use 113 for Russia")
    add_dry_run(area_tree)
    area_tree.set_defaults(func=lambda ctx, a: request_json(ctx, "GET", f"/areas/{a.id}" if a.id else "/areas", dry_run=a.dry_run), command_name="areas tree")

    area_resolve = areas_sub.add_parser("resolve", help="Resolve area name by reading /areas/{country-id}")
    area_resolve.add_argument("--name", required=True)
    area_resolve.add_argument("--country-id", default="113")
    area_resolve.add_argument("--limit", type=int, default=20)
    add_dry_run(area_resolve)
    area_resolve.set_defaults(func=command_area_resolve, command_name="areas resolve")

    suggest = sub.add_parser("suggest", help="GET /suggests/* autocomplete endpoints")
    suggest.add_argument("kind", choices=sorted(SUGGEST_ENDPOINTS))
    suggest.add_argument("text")
    add_params(suggest)
    add_dry_run(suggest)
    suggest.set_defaults(func=command_suggest, command_name="suggest")

    roles = sub.add_parser("roles", help="GET /professional_roles")
    add_dry_run(roles)
    roles.set_defaults(func=lambda ctx, a: request_json(ctx, "GET", "/professional_roles", dry_run=a.dry_run), command_name="roles")

    dictionaries = sub.add_parser("dictionaries", help="GET /dictionaries")
    add_dry_run(dictionaries)
    dictionaries.set_defaults(func=lambda ctx, a: request_json(ctx, "GET", "/dictionaries", dry_run=a.dry_run), command_name="dictionaries")

    industries = sub.add_parser("industries", help="GET /industries")
    add_dry_run(industries)
    industries.set_defaults(func=lambda ctx, a: request_json(ctx, "GET", "/industries", dry_run=a.dry_run), command_name="industries")

    salary = sub.add_parser("salary-dicts", help="Read salary statistics dictionary endpoints")
    salary.add_argument("kind", choices=sorted(SALARY_DICT_ENDPOINTS))
    add_dry_run(salary)
    salary.set_defaults(func=command_salary_dict, command_name="salary-dicts")

    request = sub.add_parser("request", help="Raw read-only API request escape hatch")
    request_sub = request.add_subparsers(dest="request_command", required=True)
    request_get = request_sub.add_parser("get", help="GET an API path with configured auth")
    request_get.add_argument("path", help="API path, e.g. /vacancies/123")
    add_params(request_get)
    add_dry_run(request_get)
    request_get.set_defaults(func=command_raw_get, command_name="request get")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = bool(args.json)
    try:
        ctx = load_context(args)
        result = args.func(ctx, args)
        emit(result, command=args.command_name, json_mode=json_mode)
        return 0
    except CliError as exc:
        emit_error(exc, json_mode=json_mode)
        return exc.exit_code


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()

