# CLI security review notes — 2026-05-07

Session-specific reference for the class-level `systemd-web-service-deployment` skill. Use when adding or reviewing read-only deployment auditor CLIs that fetch URLs, read env files, or include raw service/log output.

## Context

A read-only owning-skill CLI was added under `skills/devops/systemd-web-service-deployment/cli/` with commands such as `doctor`, `inspect`, `verify`, and `docker-bind-diagnose`. An independent review found two important classes of risk even though the CLI did not mutate system state.

## Lessons to preserve

1. **Basic Auth + redirects can leak credentials.**
   - If a CLI builds an `Authorization` header from env secrets, do not let the HTTP client follow redirects automatically.
   - Safe default: when `Authorization` is present, do not follow redirects; report the 3xx status and redacted `Location`.
   - More advanced option: follow redirects only when scheme, host, and port are unchanged, and strip `Authorization` otherwise.

2. **Read-only does not mean non-sensitive.**
   - `systemctl cat`, `systemctl show`, `journalctl`, Docker logs, and env files may contain secrets.
   - Redact before emitting JSON or text output.
   - Redaction must cover more than `PASSWORD`/`TOKEN`: include `DATABASE_URL`, `DSN`, `CONNECTION_STRING`, `CREDENTIAL`, `PRIVATE_KEY`, `ACCESS_KEY`, cookies, sessions, Authorization headers, and URL userinfo like `scheme://user:pass@host`.

3. **URL verification should be web-only by default.**
   - Deployment verifier CLIs should restrict URL checks to `http` and `https` unless another scheme is explicitly required.
   - This avoids surprising behavior from file/ftp-like URL handlers.

4. **Test the security behavior, not just the happy path.**
   - Add a local redirect test proving auth requests are not followed.
   - Add redaction tests for DB URLs and Authorization headers.
   - Add a structured JSON shape test for `doctor` and at least one local URL `verify` test.

## Review checklist for future CLI changes

- [ ] CLI default commands are read-only; mutating actions require an explicit future `--apply` design.
- [ ] No `shell=True`, `os.system`, or string-built shell commands.
- [ ] URL fetches are limited to `http`/`https`.
- [ ] Authorization-bearing requests do not forward credentials across redirects.
- [ ] Raw command output is redacted before returning.
- [ ] Env-file parsing reports key presence/metadata, not values.
- [ ] Tests cover redaction and redirect behavior.
