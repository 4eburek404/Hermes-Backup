---
name: systemd-web-service-deployment
description: "Use when deploying a Linux web service managed by systemd, especially Flask/Gunicorn services behind local reverse proxies, Tailscale Serve/Funnel, or similar ingress. Covers safe backups, env files, systemd drop-ins, restarts, read-only CLI audits, and public/private validation without leaking secrets."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [devops, systemd, deployment, web-service, tailscale, funnel, flask, gunicorn, cli, verification]
    related_skills: [github-pr-workflow, systematic-debugging]
---

# Systemd Web Service Deployment

## Overview

Use this skill for small production deployments where a Linux host runs a web app under `systemd` and exposes it through a local proxy, reverse proxy, Tailscale Serve/Funnel, or HTTPS ingress. The purpose is not merely to restart a unit. The purpose is to make the change **located, reversible, verified, and explainable**.

For Konstantin: if the work matters only when it is visible in production, do not stop at commit/push/PR unless he explicitly asked for Git-only work. Deploy or verify the live runtime, then report the URL/API, backup path, exact checks, and remaining risks.

This skill applies to Flask/Gunicorn, FastAPI/Uvicorn, Node services, static+API dashboards, and adjacent Docker containers on the same host. It is not for Kubernetes, serverless, or generic CI-only workflows.

## When to Use

Use when the user asks to:

- deploy, restart, or modify a Linux web service managed by `systemd`;
- change runtime environment variables, auth, or secrets;
- expose or debug a service through Tailscale Serve/Funnel;
- verify a deployment through local and public URLs;
- roll back a small file-based service deployment;
- diagnose Docker bind-mount permission failures around a systemd/Docker web stack.

Do not use for Kubernetes orchestration, serverless deployments, or GitHub-only PR work. If Docker is involved but the operational problem is host runtime, ingress, rollback, or verification, this skill still applies.

## Operating Rule

Evidence before interpretation:

1. Identify the actual production host, service, path, and ingress.
2. Inspect the current runtime before changing files.
3. Back up anything that will be overwritten.
4. Keep secrets in runtime env/secret stores, never git, docs, chat, or logs.
5. Deploy the narrowest artifact set possible.
6. Validate before restart, restart safely, then validate behavior through every relevant path.
7. If validation fails, roll back first, then explain root cause.

Command snippets live in `references/deployment-command-cookbook.md`. Use the owning CLI when a structured preflight/report is useful.

## Owning CLI: Read-Only Auditor

This skill owns a CLI under:

```bash
~/.hermes/hermes-agent/skills/devops/systemd-web-service-deployment/cli
```

Default commands are **read-only** and JSON-first. They inspect system state, URLs, env-file shape, and Docker bind mounts; they do not restart services, edit units, enable Funnel, change permissions, or deploy files.

Quick use:

```bash
cd ~/.hermes/hermes-agent/skills/devops/systemd-web-service-deployment/cli
python3 -m systemd_web_service_cli --json doctor
python3 -m systemd_web_service_cli --json inspect --service <service>.service --url <public-or-local-url>
python3 -m systemd_web_service_cli --json verify --url <url> --expect-status 200
python3 -m systemd_web_service_cli --json docker-bind-diagnose --path <host-bind-source> --expected-uid 1000 --expected-gid 1000
```

Use `--user` for user-level systemd services. Use `--env-file` and `--required-env` to check that required keys exist without printing their values. Use `--auth-user-env` and `--auth-password-env` for Basic Auth URL checks; the CLI reads the values, redacts them from output, and does not follow redirects while an Authorization header is present.

CLI output contract:

- top-level `ok`: whether blocking errors were found;
- `command`: executed subcommand;
- `data`: structured observations;
- `issues`: warnings/errors with machine-readable codes.

## Mandatory Workflow

### 1. Confirm where production actually runs

Do not assume an SSH alias, README, or old session is current. Check live host signals: hostname, service status, listening ports, service unit, and current working directory. In gateway/server sessions, the current execution host may already be production.

Cookbook: `references/deployment-command-cookbook.md` → **Preflight: host, service, ports**.

### 2. Inspect service and ingress before changing files

Inspect the unit and drop-ins before editing. Record:

- `FragmentPath`, `DropInPaths`, `WorkingDirectory`, `ExecStart`;
- env files by path, not by secret value;
- local listening ports;
- Tailscale Serve/Funnel state or reverse-proxy equivalent;
- recent logs.

Cookbook: **Inspect systemd unit and ingress**. CLI: `inspect`.

Tailscale distinction:

- `tailscale serve` with `(tailnet only)` still requires tailnet login.
- `tailscale funnel` with `Funnel on` exposes publicly; then app-level auth must protect the service.

### 3. Back up before overwriting

For file-based deploys, create a timestamped backup under the app path or documented backup directory. Back up every file you will overwrite, plus relevant unit/drop-in files when those change.

Cookbook: **Backup before overwrite**.

Final response must include the backup path or explicitly say why no backup was required.

### 4. Put secrets in runtime env, not git

Use a root-readable or service-user-readable env file with restrictive permissions and connect it through a systemd drop-in. Do not paste secret values into chat, docs, commits, skill references, or command output.

Cookbook: **Runtime env and systemd drop-in**. CLI: `inspect --env-file ... --required-env ...`.

If the user needs to reveal a credential, give them a local command/path to inspect it; do not print it yourself.

### 5. Deploy artifacts narrowly

Copy only intended artifacts and preserve the production layout. Prefer explicit `install -m ...` or a documented release directory over broad overwrites.

Avoid `git pull` directly in production unless that is the documented deployment model. File-based deploys are usually easier to roll back when current service files are not a git checkout.

Cookbook: **Narrow artifact deploy**.

### 6. Validate before restart

Before restart, validate syntax/imports/builds in the production-shaped environment:

- Python: venv, dependency install/update, `py_compile`, app import where safe;
- Node: install/build/test commands used by that app;
- static assets/templates: check files exist at the paths the service reads.

Cookbook: **Validate before restart**.

### 7. Restart and verify logs

Restart only after the above checks. Then verify:

- `systemctl is-active`;
- recent `journalctl` logs;
- local port/process state;
- no startup/import/auth/env errors.

Cookbook: **Restart and journal verification**. CLI: `inspect` after restart.

### 8. Verify local and public behavior

Do not treat `active` as done. Check the behavior matrix relevant to the request:

- local health/API endpoint;
- public URL through ingress;
- unauthenticated denial/redirect if auth exists;
- authenticated success;
- live/WebSocket/SSE path if present;
- content marker in rendered HTML if UI changed.

Cookbook: **Local/public/auth URL checks**. CLI: `verify`.

### 9. Enable Funnel only when explicitly required

If the user needs public access without tailnet login, `tailscale serve` alone is insufficient. Enable Funnel deliberately and confirm status includes `Funnel on`. If the command says `Access denied: serve config denied`, run with `sudo` or configure an operator with `sudo tailscale set --operator=$USER`.

Cookbook: **Tailscale Funnel enablement and rollback**.

### 10. Roll back quickly on failed validation

If public behavior, logs, auth, or imports fail after deploy, restore the backup and restart. If a drop-in caused the failure, remove/disable it and daemon-reload. If Funnel should not remain public, disable it.

Cookbook: **Rollback patterns**.

## Docker Bind-Mount Crash-Loop Diagnosis

A host reboot can leave Docker bind-mount source directories as `root:root`, causing non-root containers to fail with `EACCES` and restart forever. Diagnose host-source ownership, container user, and logs before applying `chown`.

CLI:

```bash
cd ~/.hermes/hermes-agent/skills/devops/systemd-web-service-deployment/cli
python3 -m systemd_web_service_cli --json docker-bind-diagnose --path <host-bind-source> --expected-uid 1000 --expected-gid 1000
```

Full procedure: `references/docker-bind-mount-permissions-after-reboot.md`.

## Post-VPS-Incident Recovery Checklist

After a VPS provider incident, power loss, forced rebuild, or ungraceful reboot:

1. Check `last reboot`, `uptime`, previous boot logs, and provider incident context.
2. Check all service states: `systemctl`, `docker ps -a`, listening ports.
3. Diagnose Docker bind-mount ownership before assuming app corruption.
4. Verify data integrity and whether bind-mount dirs are stale/empty.
5. Verify backup jobs and backup directory contents; local backups may be gone if the VPS was wiped.
6. Remove stale crons/scripts for retired services.
7. Check disk space and alerting after recovery.

Reference: `references/vps-provider-incident-recovery-2026-05-03.md`.

## Common Pitfalls

1. **Confusing Tailscale Serve with Funnel.** `tailnet only` still requires Tailscale login.
2. **Assuming an SSH alias works.** The current host may already be production; verify live state before blocking.
3. **Restarting before env/drop-in setup.** Auth or import-time config can fail if required keys are absent.
4. **Printing generated passwords.** Report storage path and local reveal command, not the value.
5. **Checking only `systemctl is-active`.** Active service can still have broken public ingress, auth, API, or live transport.
6. **Leaving validation scripts unauthenticated.** If app auth changes, update validation to use the same auth model.
7. **Using broad deploy commands.** Avoid accidental overwrite of runtime data, `.env`, logs, or backups.
8. **Leaving public Funnel on accidentally.** Funnel is public internet exposure; pair it with app auth and explicit rollback.
9. **Hardcoding concrete release paths in systemd units.** For release-dir deployments (where a symlink like `hermes-agent` points to `releases/hermes-agent-<hash>`), systemd units must use the **symlink path**, not the concrete release directory. A unit that hardcodes `WorkingDirectory=/.../releases/hermes-agent-d1c549c4` survives symlink switches and runs against the wrong release. Fix: use symlink paths in `WorkingDirectory`, `PATH`, and `ExecStart`; override via drop-in (`hermes-gateway.service.d/10-release-dir-paths.conf`) rather than editing the base unit. Verify with `systemctl --user show <unit> -p WorkingDirectory -p Environment`.

10. **CWD leak in subprocess calls with `--system-site-packages` venvs.**
11. **KillMode=mixed causing deactivating hangs on stop.** With `KillMode=mixed`, systemd sends SIGTERM only to MainPID, not to child processes. If the MainPID waits for un-signalled children to exit (common with gateway services that spawn npm/node subprocesses), the service hangs in `deactivating` state until `TimeoutStopSec` expires and `SendSIGKILL` kicks in. Fix: override `KillMode=control-group` via a user-level drop-in so all processes in the cgroup receive SIGTERM. Verify with `systemctl show -p KillMode --value`. This is critical for any service that spawns child processes (gateway, MCP servers, npm exec wrappers).
12. **Self-referential deployments — the service cannot stop itself.** When deploying to a gateway/messaging service that you are currently talking through, stopping the service kills the controlling session before the switch can complete. Use an external runner launched via `systemd-run --user --unit <name> --wait -- bash <script>`. The runner must handle stop → atomic symlink switch → start → verify as an atomic unit with automatic rollback on any failure after the symlink is moved. Full pattern in `references/external-switch-runner-pattern.md`.
13. **`systemctl stop` is the WRONG tool for services with graceful restart signals.** If the service supports a graceful restart signal (SIGUSR1 → drain active work → exit with a specific code like 75 → systemd `RestartForceExitStatus=<code>` auto-restarts), `systemctl stop` is the wrong approach. It sends SIGTERM (not SIGUSR1), can hang in `deactivating` state, and requires `systemctl start` which the controlling session may not survive. Always study the service's actual code for signal handlers and restart policy BEFORE writing a switch runner. The correct path is: atomic symlink switch (while service runs on old code) → graceful restart signal (e.g., SIGUSR1) → service drains + exits coded → systemd auto-restarts from new symlink. See `references/external-switch-runner-pattern.md` → Path B for the full pattern.
14. **Atomic symlink replacement, not `ln -sfn`.** For release-directory switches, `ln -sfn` does `unlink` + `symlink` in two non-atomic steps. Use `ln -s "$NEW" "$LINK.tmp.$$" && mv -Tf "$LINK.tmp.$$" "$LINK"` for an atomic replacement that leaves no window where the symlink is absent or pointing to a partial path. When a release preflight or test script creates a venv with `--system-site-packages` and then runs Python subprocesses (e.g. `venv/bin/python -c "import hermes_constants"`) without setting `cwd`, the calling script's CWD leaks into `sys.path[0]`. This causes modules to be imported from the repo checkout (or wherever the script runs) instead of the venv's installed package, breaking resource-path functions like `Path(__file__).resolve().parent / "skills"`. The fix is to always pass `cwd=<release_dir>` to subprocess calls that invoke the RC venv's Python, simulating the production `WorkingDirectory`. Additionally, add an import provenance check: verify `const_module.__file__` resolves under the RC path. Without `cwd=rc_dir`, `hermes_constants.__file__` resolved to the repo checkout, making `get_skills_dir()` return the wrong directory and causing preflight FAIL on skills architecture validation.
15. **Graceful switch runner reports need live restart-policy fields, not defaults.** For Path B runners, read `RestartUSec` before the switch path, compute `restart_wait_timeout_sec=max(180, RestartSec+90)`, and record actual `seconds_waited_for_new_pid`. In post-success audits, do not re-run the switch/restart/symlink/rollback; only audit live state and patch runner/docs with a timestamped backup if diagnostics or timeout reporting are incomplete. See `references/external-switch-runner-pattern.md`.

## Verification Checklist

- [ ] Branch/path/source of truth were verified before changes.
- [ ] Live host, service unit, runtime path, and ingress status were inspected.
- [ ] Current production files/drop-ins to be overwritten were backed up with a timestamp.
- [ ] Secrets are in runtime env/secret store and were not printed.
- [ ] Syntax/import/build checks passed before restart.
- [ ] `systemctl daemon-reload` ran if units/drop-ins changed.
- [ ] Service restarted and is `active`.
- [ ] Recent logs were checked for startup/runtime errors.
- [ ] Local endpoint and public endpoint were tested.
- [ ] Auth behavior was tested unauthenticated and authenticated when relevant.
- [ ] Realtime endpoint was tested if present.
- [ ] `Funnel on` was confirmed only when public non-tailnet access was required.
- [ ] Final response includes touched files, branch/commit if relevant, URL, backup path, verification, risks, and rollback/artifacts.

## References

- `references/deployment-command-cookbook.md` — executable snippets and CLI examples for preflight, backup, env/drop-ins, deploy, restart, verify, Funnel, rollback, and Docker diagnosis.
- `references/release-dir-systemd-paths.md` — release-directory systemd path convention: why units must use symlink paths, not concrete release directories; drop-in override pattern with verification and rollback.
- `references/cli-security-review-2026-05-07.md` — session-specific security review notes for read-only deployment auditor CLIs: Basic Auth redirects, redaction scope, URL-scheme limits, and tests.
- `references/server-monitor-deployment-case-study.md` — consolidated deployment session case study: auth/Funnel setup, holographic metrics, Docker bind-mount diagnosis, VPS incident recovery.
- `references/docker-bind-mount-permissions-after-reboot.md` — Docker bind-mount ownership reset after host reboot: diagnosis, fix, prevention.
- `references/vps-provider-incident-recovery-2026-05-03.md` — incident report: VPS provider hack, ungraceful reboot, crash-loop fix, backup cleanup.
- `references/release-preflight-cwd-leak.md` — CWD leak in subprocess calls with `--system-site-packages` venvs: why `cwd=rc_dir` is required, import provenance check, reproduction, and fix provenance.
