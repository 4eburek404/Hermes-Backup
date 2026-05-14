from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import ssl
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen

from . import __version__

SECRET_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie|session|credential|private[_-]?key|access[_-]?key|database[_-]?url|dsn|connection[_-]?string)"
)
SENSITIVE_ASSIGN_RE = re.compile(
    r"(?im)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|AUTHORIZATION|COOKIE|SESSION|CREDENTIAL|PRIVATE_KEY|ACCESS_KEY|DATABASE_URL|DSN|CONNECTION_STRING)[A-Z0-9_]*=)([^\s\n]+)"
)
URL_CREDENTIAL_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@")
AUTH_HEADER_RE = re.compile(r"(?i)(Authorization:\s*(?:Bearer|Basic)\s+)[^\s]+")
BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}")
BASIC_RE = re.compile(r"(?i)\b(Basic\s+)[A-Za-z0-9+/=-]{12,}")

CORE_COMMANDS = ["systemctl", "journalctl"]
OPTIONAL_COMMANDS = ["ss", "curl", "tailscale", "docker"]


def redact_text(value: Any) -> str:
    """Return a string with obvious secret material redacted."""
    if value is None:
        return ""
    text = str(value)
    text = AUTH_HEADER_RE.sub(r"\1[REDACTED]", text)
    text = BEARER_RE.sub(r"\1[REDACTED]", text)
    text = BASIC_RE.sub(r"\1[REDACTED]", text)
    text = URL_CREDENTIAL_RE.sub(r"\1[REDACTED]:[REDACTED]@", text)
    text = SENSITIVE_ASSIGN_RE.sub(r"\1[REDACTED]", text)
    return text


def redact_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        redacted: dict[str, Any] = {}
        for key, value in obj.items():
            if SECRET_KEY_RE.search(str(key)):
                if isinstance(value, bool) or value is None:
                    redacted[key] = value
                elif isinstance(value, (int, float)):
                    redacted[key] = value
                else:
                    redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_obj(value)
        return redacted
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def issue(severity: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    item.update(extra)
    return redact_obj(item)


def run_cmd(cmd: list[str], timeout: int = 8) -> dict[str, Any]:
    if not cmd:
        return {"cmd": cmd, "found": False, "returncode": None, "stdout": "", "stderr": "empty command"}
    if shutil.which(cmd[0]) is None:
        return {
            "cmd": cmd,
            "found": False,
            "returncode": None,
            "stdout": "",
            "stderr": f"{cmd[0]} not found",
        }
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        return redact_obj(
            {
                "cmd": cmd,
                "found": True,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
        )
    except subprocess.TimeoutExpired as exc:
        return redact_obj(
            {
                "cmd": cmd,
                "found": True,
                "returncode": None,
                "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
                "stderr": f"timed out after {timeout}s",
                "timeout": timeout,
            }
        )


def systemctl_cmd(args: list[str], *, user: bool) -> list[str]:
    return ["systemctl", *( ["--user"] if user else [] ), *args]


def journalctl_cmd(args: list[str], *, user: bool) -> list[str]:
    return ["journalctl", *( ["--user"] if user else [] ), *args]


def parse_systemctl_show(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key] = redact_text(value)
    return parsed


def parse_env_file(path: str | None) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, Any] | None]:
    if not path:
        return {}, [], None

    p = Path(path).expanduser()
    issues: list[dict[str, Any]] = []
    if not p.exists():
        return {}, [issue("error", "env_file_missing", f"env file does not exist: {p}")], {"path": str(p), "exists": False}
    if not p.is_file():
        return {}, [issue("error", "env_file_not_file", f"env path is not a file: {p}")], {"path": str(p), "exists": True, "is_file": False}

    values: dict[str, str] = {}
    try:
        for raw in p.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                values[key] = value
    except PermissionError:
        issues.append(issue("error", "env_file_permission_denied", f"permission denied reading env file: {p}"))
    except UnicodeDecodeError:
        issues.append(issue("error", "env_file_decode_error", f"env file is not valid text: {p}"))

    st = p.stat()
    mode = stat.S_IMODE(st.st_mode)
    meta = {
        "path": str(p),
        "exists": True,
        "is_file": True,
        "mode_octal": oct(mode),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "keys": sorted(values.keys()),
        "value_count": len(values),
    }
    if mode & 0o077:
        issues.append(
            issue(
                "warning",
                "env_file_permissive_mode",
                f"env file is readable/writable/executable by group/others: {oct(mode)}",
                path=str(p),
            )
        )
    return values, issues, meta


def env_presence(required: list[str], values: dict[str, str] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    values = values or {}
    missing = [name for name in required if not values.get(name)]
    present = [name for name in required if values.get(name)]
    issues = [issue("error", "required_env_missing", f"required env var is missing or empty: {name}", variable=name) for name in missing]
    return {"required": required, "present": present, "missing": missing}, issues


def basic_auth_header(env: dict[str, str], user_var: str | None, password_var: str | None) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if not user_var and not password_var:
        return {}, []
    if not user_var or not password_var:
        return {}, [issue("error", "auth_env_incomplete", "both --auth-user-env and --auth-password-env are required")]
    user = env.get(user_var) or os.environ.get(user_var)
    password = env.get(password_var) or os.environ.get(password_var)
    issues: list[dict[str, Any]] = []
    if not user:
        issues.append(issue("error", "auth_user_env_missing", f"auth user env var missing: {user_var}", variable=user_var))
    if not password:
        issues.append(issue("error", "auth_password_env_missing", f"auth password env var missing: {password_var}", variable=password_var))
    if issues:
        return {}, issues
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}, []


class NoRedirectHandler(HTTPRedirectHandler):
    """Prevent urllib from forwarding Authorization headers to redirect targets."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def open_url(request: Request, *, timeout: int, context: ssl.SSLContext | None, no_redirect: bool):
    handlers = []
    if no_redirect:
        handlers.append(NoRedirectHandler())
    if context is not None:
        handlers.append(HTTPSHandler(context=context))
    if handlers:
        return build_opener(*handlers).open(request, timeout=timeout)
    return urlopen(request, timeout=timeout)


def fetch_url(url: str, *, headers: dict[str, str] | None = None, timeout: int = 10, insecure: bool = False, marker: str | None = None) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"url": url, "ok": False, "error": f"unsupported URL scheme: {parsed.scheme or '<missing>'}", "scheme": parsed.scheme}

    request_headers = headers or {}
    no_redirect = any(key.lower() == "authorization" for key in request_headers)
    request = Request(url, headers=request_headers, method="GET")
    context = ssl._create_unverified_context() if insecure and parsed.scheme == "https" else None
    try:
        with open_url(request, timeout=timeout, context=context, no_redirect=no_redirect) as resp:  # nosec: operator-supplied deployment URL
            body = resp.read(1_000_000)
            text = body.decode("utf-8", errors="replace")
            return {
                "url": url,
                "ok": True,
                "status": resp.getcode(),
                "bytes_sampled": len(body),
                "content_marker": marker,
                "marker_found": (marker in text) if marker else None,
            }
    except HTTPError as exc:
        body = exc.read(200_000)
        text = body.decode("utf-8", errors="replace")
        return {
            "url": url,
            "ok": True,
            "status": exc.code,
            "bytes_sampled": len(body),
            "content_marker": marker,
            "marker_found": (marker in text) if marker else None,
            "http_error": True,
            "redirect_not_followed": bool(no_redirect and 300 <= exc.code < 400),
            "location": redact_text(exc.headers.get("Location", "")) if 300 <= exc.code < 400 else None,
        }
    except URLError as exc:
        return {"url": url, "ok": False, "error": redact_text(str(exc.reason))}
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return {"url": url, "ok": False, "error": redact_text(str(exc))}


def cmd_doctor(_: argparse.Namespace) -> dict[str, Any]:
    commands = {name: bool(shutil.which(name)) for name in [*CORE_COMMANDS, *OPTIONAL_COMMANDS]}
    issues: list[dict[str, Any]] = []
    for name in CORE_COMMANDS:
        if not commands[name]:
            issues.append(issue("error", "missing_core_command", f"required command not found: {name}", command=name))
    for name in OPTIONAL_COMMANDS:
        if not commands[name]:
            issues.append(issue("warning", "missing_optional_command", f"optional command not found: {name}", command=name))

    systemctl_version = run_cmd(["systemctl", "--version"], timeout=5) if commands.get("systemctl") else None
    return {
        "ok": not any(item["severity"] == "error" for item in issues),
        "command": "doctor",
        "data": {
            "version": __version__,
            "python": sys.version.split()[0],
            "commands": commands,
            "systemctl_version": systemctl_version,
            "read_only": True,
        },
        "issues": issues,
    }


def cmd_inspect(args: argparse.Namespace) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    service = args.service
    env_values, env_issues, env_meta = parse_env_file(args.env_file)
    issues.extend(env_issues)
    env_check, env_check_issues = env_presence(args.required_env or [], env_values)
    issues.extend(env_check_issues)

    is_active = run_cmd(systemctl_cmd(["is-active", service], user=args.user), timeout=8)
    show = run_cmd(
        systemctl_cmd(
            [
                "show",
                service,
                "-p",
                "FragmentPath",
                "-p",
                "DropInPaths",
                "-p",
                "WorkingDirectory",
                "-p",
                "ExecStart",
                "-p",
                "EnvironmentFiles",
                "-p",
                "LoadState",
                "-p",
                "ActiveState",
                "-p",
                "SubState",
            ],
            user=args.user,
        ),
        timeout=8,
    )
    cat = run_cmd(systemctl_cmd(["cat", service], user=args.user), timeout=8)
    logs = run_cmd(journalctl_cmd(["-u", service, "-n", str(args.log_lines), "--no-pager"], user=args.user), timeout=10)
    ports = run_cmd(["ss", "-ltnp"], timeout=8)
    tailscale_serve = run_cmd(["tailscale", "serve", "status"], timeout=8)
    tailscale_funnel = run_cmd(["tailscale", "funnel", "status"], timeout=8)

    if is_active.get("found") and is_active.get("returncode") != 0:
        issues.append(issue("error", "service_not_active", f"service is not active: {service}", stdout=is_active.get("stdout"), stderr=is_active.get("stderr")))
    if not is_active.get("found"):
        issues.append(issue("error", "systemctl_missing", "systemctl is not available"))

    url_results = [fetch_url(url, timeout=args.timeout, insecure=args.insecure) for url in (args.url or [])]
    for result in url_results:
        if not result.get("ok"):
            issues.append(issue("warning", "url_check_failed", f"URL check failed: {result['url']}", error=result.get("error")))

    data = {
        "service": service,
        "user_service": args.user,
        "systemd": {
            "is_active": is_active,
            "show": parse_systemctl_show(show.get("stdout", "")),
            "show_raw": show,
            "unit": cat,
            "recent_logs": logs,
        },
        "ports": ports,
        "tailscale": {"serve": tailscale_serve, "funnel": tailscale_funnel},
        "env_file": env_meta,
        "env_check": env_check,
        "url_checks": url_results,
    }
    return {"ok": not any(item["severity"] == "error" for item in issues), "command": "inspect", "data": redact_obj(data), "issues": issues}


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    env_values, env_issues, env_meta = parse_env_file(args.env_file)
    issues.extend(env_issues)
    headers, auth_issues = basic_auth_header(env_values, args.auth_user_env, args.auth_password_env)
    issues.extend(auth_issues)

    results = [
        fetch_url(url, headers=headers, timeout=args.timeout, insecure=args.insecure, marker=args.content_marker)
        for url in args.url
    ]
    for result in results:
        if not result.get("ok"):
            issues.append(issue("error", "url_fetch_failed", f"URL fetch failed: {result['url']}", error=result.get("error")))
            continue
        if args.expect_status is not None and result.get("status") != args.expect_status:
            issues.append(
                issue(
                    "error",
                    "unexpected_status",
                    f"unexpected HTTP status for {result['url']}: {result.get('status')} != {args.expect_status}",
                    url=result["url"],
                    actual=result.get("status"),
                    expected=args.expect_status,
                )
            )
        if args.content_marker and not result.get("marker_found"):
            issues.append(issue("error", "content_marker_missing", f"content marker not found for {result['url']}", url=result["url"]))

    return {
        "ok": not any(item["severity"] == "error" for item in issues),
        "command": "verify",
        "data": redact_obj(
            {
                "urls": results,
                "expected_status": args.expect_status,
                "content_marker": args.content_marker,
                "auth_from_env": bool(args.auth_user_env or args.auth_password_env),
                "env_file": env_meta,
            }
        ),
        "issues": issues,
    }


def owner_name(uid: int, gid: int) -> dict[str, Any]:
    result: dict[str, Any] = {"uid": uid, "gid": gid}
    try:
        import pwd

        result["user"] = pwd.getpwuid(uid).pw_name
    except Exception:
        result["user"] = None
    try:
        import grp

        result["group"] = grp.getgrgid(gid).gr_name
    except Exception:
        result["group"] = None
    return result


def cmd_docker_bind_diagnose(args: argparse.Namespace) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    p = Path(args.path).expanduser()
    path_data: dict[str, Any] = {"path": str(p), "exists": p.exists()}
    if not p.exists():
        issues.append(issue("error", "path_missing", f"bind source path does not exist: {p}"))
    else:
        st = p.stat()
        mode = stat.S_IMODE(st.st_mode)
        owner = owner_name(st.st_uid, st.st_gid)
        path_data.update(
            {
                "is_dir": p.is_dir(),
                "mode_octal": oct(mode),
                "owner": owner,
                "expected_uid": args.expected_uid,
                "expected_gid": args.expected_gid,
                "matches_expected_uid": None if args.expected_uid is None else st.st_uid == args.expected_uid,
                "matches_expected_gid": None if args.expected_gid is None else st.st_gid == args.expected_gid,
            }
        )
        if args.expected_uid is not None and st.st_uid != args.expected_uid:
            issues.append(issue("error", "uid_mismatch", f"path uid {st.st_uid} != expected {args.expected_uid}", path=str(p)))
        if args.expected_gid is not None and st.st_gid != args.expected_gid:
            issues.append(issue("error", "gid_mismatch", f"path gid {st.st_gid} != expected {args.expected_gid}", path=str(p)))
        if st.st_uid == 0 and st.st_gid == 0 and (args.expected_uid not in (None, 0) or args.expected_gid not in (None, 0)):
            issues.append(issue("warning", "root_owned_bind_source", "bind source is root:root while a non-root owner may be expected", path=str(p)))

    container_data: dict[str, Any] | None = None
    if args.container:
        inspect_mounts = run_cmd(["docker", "inspect", args.container, "--format", "{{json .Mounts}}"], timeout=8)
        inspect_user = run_cmd(["docker", "inspect", args.container, "--format", "{{.Config.User}}"], timeout=8)
        logs = run_cmd(["docker", "logs", args.container, "--tail", str(args.log_lines)], timeout=8)
        container_data = {"name": args.container, "mounts": inspect_mounts, "user": inspect_user, "recent_logs": logs}
        if inspect_mounts.get("found") and inspect_mounts.get("returncode") != 0:
            issues.append(issue("warning", "docker_inspect_failed", f"docker inspect failed for {args.container}", stderr=inspect_mounts.get("stderr")))
        log_text = f"{logs.get('stdout', '')}\n{logs.get('stderr', '')}".lower()
        if "eacces" in log_text or "permission denied" in log_text:
            issues.append(issue("warning", "permission_error_in_logs", "recent container logs mention EACCES/permission denied"))

    return {
        "ok": not any(item["severity"] == "error" for item in issues),
        "command": "docker-bind-diagnose",
        "data": redact_obj({"path": path_data, "container": container_data, "read_only": True}),
        "issues": issues,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only systemd web service deployment auditor")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument("--version", action="version", version=f"systemd_web_service_cli {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check local command availability")
    doctor.set_defaults(func=cmd_doctor)

    inspect_p = sub.add_parser("inspect", help="inspect a systemd web service without changing it")
    inspect_p.add_argument("--service", required=True, help="systemd service name, e.g. app.service")
    inspect_p.add_argument("--user", action="store_true", help="inspect a user-level systemd service")
    inspect_p.add_argument("--url", action="append", default=[], help="URL to fetch without auth; may be repeated")
    inspect_p.add_argument("--env-file", help="env file to inspect for key presence; values are never printed")
    inspect_p.add_argument("--required-env", action="append", default=[], help="required env var name; may be repeated")
    inspect_p.add_argument("--log-lines", type=int, default=80, help="journal lines to collect")
    inspect_p.add_argument("--timeout", type=int, default=10, help="URL timeout seconds")
    inspect_p.add_argument("--insecure", action="store_true", help="skip TLS certificate verification for URL checks")
    inspect_p.set_defaults(func=cmd_inspect)

    verify = sub.add_parser("verify", help="verify one or more URLs")
    verify.add_argument("--url", action="append", required=True, help="URL to fetch; may be repeated")
    verify.add_argument("--expect-status", type=int, help="expected HTTP status for all URLs")
    verify.add_argument("--content-marker", help="string that must be present in the sampled response body")
    verify.add_argument("--env-file", help="env file containing Basic Auth env vars")
    verify.add_argument("--auth-user-env", help="env var containing Basic Auth username")
    verify.add_argument("--auth-password-env", help="env var containing Basic Auth password")
    verify.add_argument("--timeout", type=int, default=10, help="URL timeout seconds")
    verify.add_argument("--insecure", action="store_true", help="skip TLS certificate verification")
    verify.set_defaults(func=cmd_verify)

    docker_p = sub.add_parser("docker-bind-diagnose", help="inspect bind-mount ownership without changing it")
    docker_p.add_argument("--path", required=True, help="host bind source path")
    docker_p.add_argument("--container", help="optional Docker container name/id for mount/log inspection")
    docker_p.add_argument("--expected-uid", type=int, help="expected host path uid")
    docker_p.add_argument("--expected-gid", type=int, help="expected host path gid")
    docker_p.add_argument("--log-lines", type=int, default=30, help="container log lines to inspect")
    docker_p.set_defaults(func=cmd_docker_bind_diagnose)

    return parser


def emit(result: dict[str, Any], *, as_json: bool) -> None:
    result = redact_obj(result)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return

    status = "OK" if result.get("ok") else "ISSUES"
    print(f"{status}: {result.get('command')}")
    for item in result.get("issues", []):
        print(f"- {item.get('severity')}: {item.get('code')} — {item.get('message')}")
    if not result.get("issues"):
        print("- no blocking issues found")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    emit(result, as_json=args.json)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
