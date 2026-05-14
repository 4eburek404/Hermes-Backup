# systemd_web_service_cli

Read-only owning-skill CLI for `systemd-web-service-deployment`.

It exists to give the agent a structured preflight/verification report before and after production changes. By design it does **not** deploy files, restart services, edit systemd units, enable Tailscale Funnel, or change Docker permissions.

## Commands

Run from this directory:

```bash
python3 -m systemd_web_service_cli --json doctor
```

Inspect a system service:

```bash
python3 -m systemd_web_service_cli --json inspect \
  --service <service>.service \
  --url https://example.com/health
```

Inspect a user service:

```bash
python3 -m systemd_web_service_cli --json inspect --user --service hermes-gateway.service
```

Check required env keys without printing values:

```bash
python3 -m systemd_web_service_cli --json inspect \
  --service <service>.service \
  --env-file /path/to/app/<service>.env \
  --required-env APP_USERNAME \
  --required-env APP_PASSWORD
```

Verify auth/public behavior:

```bash
python3 -m systemd_web_service_cli --json verify \
  --url https://example.com/dashboard \
  --expect-status 200 \
  --content-marker 'Dashboard' \
  --env-file /path/to/app/<service>.env \
  --auth-user-env APP_USERNAME \
  --auth-password-env APP_PASSWORD
```

Diagnose Docker bind-mount ownership:

```bash
python3 -m systemd_web_service_cli --json docker-bind-diagnose \
  --path <host-bind-source-path> \
  --container <container> \
  --expected-uid 1000 \
  --expected-gid 1000
```

## Output contract

Every command returns:

```json
{
  "ok": true,
  "command": "doctor",
  "data": {},
  "issues": []
}
```

- `ok=false` means at least one blocking `error` issue was found.
- `warning` issues are non-blocking but should be reported.
- Secret-looking env values, Authorization headers, tokens, cookies, and session values are redacted.

## Safety rules

- Read-only by default and currently read-only only.
- No `systemctl restart`, `daemon-reload`, `tailscale funnel`, `chown`, `install`, or writes.
- Env files are parsed only for key presence unless Basic Auth verification is explicitly requested.
- Auth values may be read to construct a request header, but are never printed.
- When an Authorization header is used, redirects are not followed; this prevents credentials from being forwarded to a different origin.
