# Docker Bind Mount Permission Failure After Host Reboot

## Symptom

A container with a host bind mount enters a crash loop immediately after host reboot.

- `docker ps -a` shows `Restarting (1)` or similar non-zero exit code.
- Container logs show `EACCES: permission denied` writing to the mounted path.
- Container dies within seconds; Docker restart policy loops it indefinitely.

## Root Cause

When Docker starts containers after a host reboot, it may recreate mount source directories as `root:root` if they do not exist yet, or if the host filesystem/restore process reset ownership. This is common when:

1. the bind source directory was created by Docker during `docker run`, not pre-created by the user;
2. the container process runs as a non-root user, for example UID `1000`;
3. the application writes generated config/state into the mounted directory during startup.

## Read-Only CLI Diagnosis

From the owning skill CLI:

```bash
cd ~/.hermes/hermes-agent/skills/devops/systemd-web-service-deployment/cli
python3 -m systemd_web_service_cli --json docker-bind-diagnose \
  --path <host-bind-source-path> \
  --container <container> \
  --expected-uid 1000 \
  --expected-gid 1000
```

The CLI does not run `chown` or restart the container. It reports current owner, expected owner match, optional container user, mounts, and recent permission-denied log signals.

## Manual Diagnosis Steps

```bash
# 1. Find the bind mount source on host.
docker inspect <container> --format '{{json .Mounts}}' | python3 -m json.tool
# Look for Source (host path) and Destination (container path).

# 2. Check ownership of the host-side directory.
ls -la <host-source-path>
stat -c '%u:%g %U:%G %a %n' <host-source-path>

# 3. Check what user the container runs as.
docker inspect <container> --format '{{.Config.User}}'
# Empty string means root; a name or UID usually means non-root.

# 4. Confirm crash loop and permission symptom.
docker ps -a --filter name=<container>
docker logs <container> --tail 30 2>&1
# Look for EACCES / permission denied on the destination path.
```

## Fix

Apply only after confirming the expected container UID/GID:

```bash
sudo chown -R <uid>:<gid> <host-bind-source-path>
docker restart <container>
sleep 5
docker ps --filter name=<container> --format '{{.Status}}'
docker logs <container> --tail 15 2>&1
```

## Specific Example: n8n (2026-05-03)

- Container: `n8n` (image `n8nio/n8n:latest`, v2.16.2)
- Bind: `/home/konstantin/n8n/data` → `/home/node/.n8n`
- Error: `EACCES: permission denied, open '/home/node/.n8n/config'`
- Ownership was `root:root` on `/home/konstantin/n8n/data/`
- Fix used after diagnosis: `sudo chown -R 1000:1000 /home/konstantin/n8n/data && docker restart n8n`

## Prevention

- Pre-create bind source directories with correct ownership before `docker run` / compose startup.
- In docker-compose, set `user: "1000:1000"` when the image supports it and make host ownership match.
- For single-host stacks, use a systemd `ExecStartPre` or wrapper that verifies/chowns known bind sources before container startup.
- After provider incidents or forced reboots, inspect bind mounts before assuming application data corruption.
