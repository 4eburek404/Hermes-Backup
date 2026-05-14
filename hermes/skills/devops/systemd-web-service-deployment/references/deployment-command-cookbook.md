# Systemd web service deployment command cookbook

Executable snippets for `systemd-web-service-deployment`. Keep this file operational and copy/paste-friendly, but treat all placeholders as examples. Do not paste real secrets into chat, docs, commits, or skill references.

Conventions:

- Replace `<service>.service`, `/path/to/app`, and URLs before running.
- Prefer read-only inspection first.
- Use the owning CLI for structured reports when possible:

```bash
cd ~/.hermes/hermes-agent/skills/devops/systemd-web-service-deployment/cli
python3 -m systemd_web_service_cli --json doctor
python3 -m systemd_web_service_cli --json inspect --service <service>.service --url <url>
```

## Preflight: host, service, ports

```bash
hostname
pwd
systemctl is-active <service>.service || true
systemctl cat <service>.service || true
systemctl show <service>.service -p FragmentPath -p DropInPaths -p WorkingDirectory -p ExecStart || true
ss -ltnp || true
```

For user-level services:

```bash
systemctl --user is-active <service>.service || true
systemctl --user cat <service>.service || true
systemctl --user show <service>.service -p FragmentPath -p DropInPaths -p WorkingDirectory -p ExecStart || true
journalctl --user -u <service>.service -n 50 --no-pager || true
```

## Inspect systemd unit and ingress

```bash
systemctl cat <service>.service
systemctl show <service>.service \
  -p FragmentPath \
  -p DropInPaths \
  -p WorkingDirectory \
  -p ExecStart \
  -p EnvironmentFiles
journalctl -u <service>.service -n 80 --no-pager
```

Tailscale ingress:

```bash
tailscale serve status || true
tailscale funnel status || true
```

Interpretation:

- `(tailnet only)` means Tailscale login is still required.
- `Funnel on` means public internet exposure; verify app-level auth.

## Backup before overwrite

```bash
app_dir=/path/to/app
stamp=$(date +%Y%m%d%H%M%S)
backup_dir="$app_dir/backups/$stamp"
mkdir -p "$backup_dir"

# Copy every file you will overwrite.
cp "$app_dir/app.py" "$backup_dir/app.py"
cp "$app_dir/requirements.txt" "$backup_dir/requirements.txt"
cp -a "$app_dir/templates" "$backup_dir/templates"
cp -a "$app_dir/static" "$backup_dir/static"

printf 'backup_dir=%s\n' "$backup_dir"
```

If unit/drop-ins change, back those up too:

```bash
sudo mkdir -p "$backup_dir/systemd"
systemctl show <service>.service -p FragmentPath -p DropInPaths
sudo cp /etc/systemd/system/<service>.service "$backup_dir/systemd/" 2>/dev/null || true
sudo cp -a /etc/systemd/system/<service>.service.d "$backup_dir/systemd/" 2>/dev/null || true
```

## Runtime env and systemd drop-in

Create or edit the env file locally on the host. Do not echo generated secret values into chat.

```bash
app_dir=/path/to/app
env_file="$app_dir/<service>.env"

umask 077
sudo install -m 0600 -o root -g root /dev/null "$env_file"
sudoedit "$env_file"
```

Example key shape only:

```text
APP_REQUIRE_AUTH=true
APP_USERNAME=<non-secret username>
APP_PASSWORD=[REDACTED]
APP_SESSION_SECRET=[REDACTED]
```

Connect the env file through a drop-in:

```bash
sudo mkdir -p /etc/systemd/system/<service>.service.d
printf '%s\n' '[Service]' "EnvironmentFile=$env_file" |
  sudo tee /etc/systemd/system/<service>.service.d/env.conf >/dev/null
sudo systemctl daemon-reload
```

Check keys without printing values:

```bash
sudo awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $1}' "$env_file"
sudo stat -c '%a %U:%G %n' "$env_file"
```

CLI equivalent:

```bash
python3 -m systemd_web_service_cli --json inspect \
  --service <service>.service \
  --env-file /path/to/app/<service>.env \
  --required-env APP_USERNAME \
  --required-env APP_PASSWORD
```

## Narrow artifact deploy

```bash
install -m 0644 src/app.py /path/to/app/app.py
install -m 0644 requirements.txt /path/to/app/requirements.txt
install -m 0644 static/app.css /path/to/app/static/app.css
install -m 0644 templates/index.html /path/to/app/templates/index.html
```

Do not overwrite runtime files such as env files, logs, databases, uploaded data, backups, or local-only config unless that is explicitly required and backed up.

## Validate before restart

Python service example:

```bash
cd /path/to/app
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m py_compile app.py
```

If the app exposes an importable object, check imports in the same venv:

```bash
.venv/bin/python - <<'PY'
import importlib
mod = importlib.import_module('app')
print('import_ok', bool(mod))
PY
```

Node service example:

```bash
cd /path/to/app
npm ci
npm run build --if-present
npm test --if-present
```

## Restart and journal verification

```bash
sudo systemctl restart <service>.service
sleep 2
systemctl is-active <service>.service
journalctl -u <service>.service -n 80 --no-pager
ss -ltnp || true
```

User-level service:

```bash
systemctl --user restart <service>.service
sleep 2
systemctl --user is-active <service>.service
journalctl --user -u <service>.service -n 80 --no-pager
```

## Local/public/auth URL checks

Unauthenticated/public checks:

```bash
curl -ksS -o /tmp/noauth.html -w 'status=%{http_code}\n' https://example.com/dashboard
curl -ksS -o /tmp/local.html -w 'status=%{http_code}\n' http://127.0.0.1:8080/health
```

Basic Auth check using env values without printing them:

```bash
set -a
. /path/to/app/<service>.env
set +a
curl -ksS -u "$APP_USERNAME:$APP_PASSWORD" \
  -o /tmp/auth.html \
  -w 'status=%{http_code}\n' \
  https://example.com/dashboard
```

Content marker check:

```bash
grep -q 'Expected UI Marker' /tmp/auth.html && echo marker_ok
```

CLI equivalents:

```bash
python3 -m systemd_web_service_cli --json verify \
  --url https://example.com/dashboard \
  --expect-status 401

python3 -m systemd_web_service_cli --json verify \
  --url https://example.com/dashboard \
  --env-file /path/to/app/<service>.env \
  --auth-user-env APP_USERNAME \
  --auth-password-env APP_PASSWORD \
  --expect-status 200 \
  --content-marker 'Expected UI Marker'
```

Auth values may be read to build the request header, but the CLI does not print them. When an Authorization header is used, redirects are not followed so credentials are not forwarded to a different origin.

## Tailscale Funnel enablement and rollback

Enable only when public non-tailnet access is required:

```bash
sudo tailscale funnel --bg --yes 8080
tailscale funnel status
```

Expected signal includes:

```text
Funnel on
```

Rollback public exposure:

```bash
sudo tailscale funnel --https=443 off
tailscale funnel status || true
```

If enabling fails with `Access denied: serve config denied`, either run with `sudo` or configure an operator:

```bash
sudo tailscale set --operator=$USER
```

## Rollback patterns

Restore overwritten files:

```bash
backup_dir=/path/to/app/backups/<stamp>
cp "$backup_dir/app.py" /path/to/app/app.py
cp "$backup_dir/requirements.txt" /path/to/app/requirements.txt
cp -a "$backup_dir/templates" /path/to/app/templates
cp -a "$backup_dir/static" /path/to/app/static
sudo systemctl restart <service>.service
systemctl is-active <service>.service
```

Remove a bad env drop-in:

```bash
sudo rm -f /etc/systemd/system/<service>.service.d/env.conf
sudo systemctl daemon-reload
sudo systemctl restart <service>.service
journalctl -u <service>.service -n 80 --no-pager
```

Rollback checklist:

```bash
systemctl is-active <service>.service
journalctl -u <service>.service -n 80 --no-pager
curl -ksS -o /tmp/rollback-check.html -w 'status=%{http_code}\n' https://example.com/dashboard
```

## Docker bind-mount diagnosis

Read-only diagnosis:

```bash
docker inspect <container> --format '{{json .Mounts}}' | python3 -m json.tool
ls -la <host-source-path>
docker inspect <container> --format '{{.Config.User}}'
docker logs <container> --tail 30 2>&1
```

CLI read-only diagnosis:

```bash
python3 -m systemd_web_service_cli --json docker-bind-diagnose \
  --path <host-source-path> \
  --container <container> \
  --expected-uid 1000 \
  --expected-gid 1000
```

Apply ownership fix only after diagnosis confirms the expected UID/GID:

```bash
sudo chown -R <uid>:<gid> <host-source-path>
docker restart <container>
docker ps --filter name=<container> --format '{{.Status}}'
```
