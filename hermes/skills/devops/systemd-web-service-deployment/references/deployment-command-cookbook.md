# Systemd web service deployment command cookbook

Executable shell snippets extracted from `SKILL.md`; the skill core contains workflow rules and points here on demand.

## 1. 1. Confirm where production actually runs

```bash
hostname
systemctl is-active <service>.service || true
systemctl cat <service>.service || true
ss -ltnp | grep -E ':(80|443|8080|8443)\b' || true
```

## 2. 2. Inspect service and ingress before changing files

```bash
systemctl cat <service>.service
systemctl show <service>.service -p FragmentPath -p DropInPaths -p WorkingDirectory -p ExecStart -p Environment
```

## 3. 2. Inspect service and ingress before changing files

```bash
tailscale serve status || true
tailscale funnel status || true
```

## 4. 3. Back up before overwriting

```bash
stamp=$(date +%Y%m%d%H%M%S)
mkdir -p /path/to/app/backups/$stamp
cp /path/to/app/app.py /path/to/app/backups/$stamp/app.py
cp /path/to/app/requirements.txt /path/to/app/backups/$stamp/requirements.txt
# copy templates/static/config files that will be overwritten
```

## 5. 4. Put secrets in runtime env, not git

```bash
umask 077
cat > /path/to/app/service.env <<'EOF'
APP_REQUIRE_AUTH=1
APP_USERNAME=<non-secret-username>
APP_PASSWORD=<secret-generated-or-user-provided>
APP_SESSION_SECRET=<secret-generated>
EOF
chmod 600 /path/to/app/service.env

sudo mkdir -p /etc/systemd/system/<service>.service.d
printf '%s\n' '[Service]' 'EnvironmentFile=/path/to/app/service.env' |
  sudo tee /etc/systemd/system/<service>.service.d/env.conf >/dev/null
sudo systemctl daemon-reload
```

## 6. 5. Deploy artifacts narrowly

```bash
install -m 0644 src/app.py /path/to/app/app.py
install -m 0644 requirements.txt /path/to/app/requirements.txt
install -m 0644 static/app.css /path/to/app/static/app.css
install -m 0644 templates/index.html /path/to/app/templates/index.html
```

## 7. 6. Validate before and after restart

```bash
cd /path/to/app
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m py_compile app.py
```

## 8. 6. Validate before and after restart

```bash
sudo systemctl restart <service>.service
sleep 2
systemctl is-active <service>.service
journalctl -u <service>.service -n 50 --no-pager
```

## 9. 7. Verify local and public behavior

```bash
set -a; . /path/to/app/service.env; set +a
curl -ks -o /tmp/noauth.html -w '%{http_code}\n' https://example.com/dashboard
curl -ks -u "$APP_USERNAME:$APP_PASSWORD" -o /tmp/auth.html -w '%{http_code}\n' https://example.com/dashboard
```

## 10. 8. If public access should not require tailnet login, enable Funnel explicitly

```bash
sudo tailscale funnel --bg --yes 8080
tailscale funnel status
```

## 11. Rollback Pattern

```bash
cp /path/to/app/backups/<stamp>/app.py /path/to/app/app.py
cp /path/to/app/backups/<stamp>/requirements.txt /path/to/app/requirements.txt
# restore other backed-up files
sudo systemctl restart <service>.service
systemctl is-active <service>.service
```

## 12. Rollback Pattern

```bash
sudo rm /etc/systemd/system/<service>.service.d/env.conf
sudo systemctl daemon-reload
sudo systemctl restart <service>.service
```

## 13. Rollback Pattern

```bash
sudo tailscale funnel --https=443 off
```

## 14. Docker Container Crash-Loop Diagnosis

```bash
docker inspect <container> --format '{{json .Mounts}}'    # find host source path
ls -la <host-source-path>                                   # check ownership
docker inspect <container> --format '{{.Config.User}}'    # check container user
sudo chown -R <uid>:<gid> <host-source-path>               # fix ownership
docker restart <container>                                  # recover
```
