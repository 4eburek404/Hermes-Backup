# Guest Hermes Docker dashboard telemetry

Session pattern: adding a dashboard/monitor card for a disposable guest Hermes Agent instance running in Docker.

## Trigger

Use this when a server monitor or status dashboard should distinguish the primary local Hermes gateway from an isolated guest/containerized Hermes runtime.

## Observed setup

- Guest containers may be managed by Docker Compose under a user directory such as `/home/konstantin/hermes-instances/guest/docker-compose.yml`.
- Container names used in the observed environment:
  - `hermes-guest`
  - `hermes-guest-dashboard`
- Image: `nousresearch/hermes-agent:latest`.
- Containers can run on host networking and may not expose ports in `docker ps` output.

## Implementation pattern for a dashboard

1. Make container names configurable by env var, with a sensible default, e.g.:
   - `SERVER_MONITOR_HERMES_GUEST_DOCKER_CONTAINERS=hermes-guest,hermes-guest-dashboard`
2. Inspect containers with `docker inspect <names...>` rather than parsing human `docker ps` output.
3. Treat Docker unavailability or missing containers as telemetry degradation, not dashboard failure.
4. Parse Docker `StartedAt` timestamps as RFC3339 with optional nanoseconds; trim fractional seconds to Python `datetime.fromisoformat()` microsecond precision.
5. Return a service payload separate from the primary Hermes service, for example:
   - key: `hermes_guest`
   - `code`: `online` when all configured containers are running, `busy`/degraded when only some run, `offline` when none run or missing
   - `phase`: e.g. `Docker guest online`
   - `meta`: e.g. `2/2 running · hermes-guest running · hermes-guest-dashboard running`
   - stats: `Running 2/2`, container uptime/status rows
6. Frontend: render a separate card such as `svc-hermes-guest` so users do not confuse guest state with the primary gateway.

## Verification checklist

- `python -m py_compile` for the dashboard backend.
- Unit/smoke call to the collector returns both `hermes` and `hermes_guest` keys.
- Template render contains the guest card marker (`svc-hermes-guest` or equivalent).
- Authenticated `/api/stats` exposes `services.hermes_guest` with expected code/meta.
- Public/authenticated dashboard HTML contains the card marker.
- Existing auth behavior remains intact (`401` for unauthenticated protected API).

## Pitfalls

- Do not hardcode the guest instance as the primary Hermes status. It is a separate runtime with separate semantics.
- Do not parse credentials or `.env` values into output while verifying authenticated dashboard endpoints; print only status codes and non-secret fields.
- `docker ps` is useful for discovery, but machine-readable dashboard collection should use `docker inspect` JSON.
- If the guest container is intentionally absent, show `missing`/`offline` rather than failing the whole dashboard payload.
