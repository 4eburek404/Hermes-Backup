# Docker Bind Mount Permission Failure After Host Reboot

## Symptom

A container with a host bind mount enters a crash loop immediately after host reboot.
- `docker ps -a` shows `Restarting (1)` or similar non-zero exit code.
- Container logs show `EACCES: permission denied` writing to the mounted path.
- Container dies within seconds; Docker restart policy loops it indefinitely.

## Root Cause

When Docker starts containers after a host reboot, it may recreate mount source directories
as `root:root` if they don't exist yet (or if the host filesystem reset ownership). This
is especially common when:

1. The bind source directory was created by Docker during `docker run` (not pre-created by user).
2. The container process runs as a non-root user (e.g. n8n runs as `node` UID 1000).
3. A service like `n8n` tries to write its auto-generated config on first boot inside the
   container path (`/home/node/.n8n/config`), which maps to the host-side bind source.

## Diagnosis Steps

```bash
# 1. Find the bind mount source on host
docker inspect <container> --format '{{json .Mounts}}' | python3 -m json.tool
# Look for Source (host path) and Destination (container path).

# 2. Check ownership of the host-side directory
ls -la <host-source-path>

# 3. Check what user the container runs as
docker inspect <container> --format '{{.Config.User}}'
# Empty string means root; "node" or a UID means non-root.

# 4. Confirm crash loop
docker logs <container> --tail 20 2>&1
# Look for EACCES / permission denied on the destination path.
```

## Fix

```bash
# Match the ownership to the container's UID/GID (commonly 1000:1000)
sudo chown -R 1000:1000 <host-bind-source-path>

# Restart the container
docker restart <container>

# Verify
sleep 5
docker ps --filter name=<container> --format '{{.Status}}'
docker logs <container> --tail 15 2>&1
```

## Specific Example: n8n (2026-05-03)

- Container: `n8n` (image `n8nio/n8n:latest`, v2.16.2)
- Bind: `/home/konstantin/n8n/data` → `/home/node/.n8n`
- Error: `EACCES: permission denied, open '/home/node/.n8n/config'`
- Ownership was `root:root` on `/home/konstantin/n8n/data/`
- Fix: `sudo chown -R 1000:1000 /home/konstantin/n8n/data && docker restart n8n`

## Prevention

- Add a `chown` to the container's restart policy or a systemd `ExecStartPre` that fixes
  ownership before Docker brings up the container stack.
- Alternatively, pre-create the bind source with correct ownership before `docker run`.
- In docker-compose, use `user: "1000:1000"` explicitly and ensure the bind source exists
  with matching ownership.