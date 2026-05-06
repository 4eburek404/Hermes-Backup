# Plan: Server Monitor auth without Tailscale login dependency

## Goal
Make `server_monitor_iOS_app` usable without relying on Tailscale web login as the access gate, by restoring/implementing app-level authorization and preserving safe access to the dashboard/API.

## Context
- Repository: `/home/konstantin/github_repo/server_monitor_iOS_app`
- Branch created first as requested: `feat/auth-without-tailscale-login`
- Current documented state says access control is private Tailscale network and dashboard has no app login/basic auth/stored monitor password.
- User reports Tailscale access is unstable; need remove dependency on Tailscale login and add authorization.
- Need inspect git history for earlier auth implementation before designing changes.

## Non-goals
- Do not deploy to VPS until implementation and local verification are clear.
- Do not expose or store secrets in repository/docs/plans.
- Do not make broad UI refactors unrelated to auth.
- Do not change GitHub repo settings unless explicitly needed.

## Steps
- [x] Create a new feature branch from current `main`.
- [x] Inspect historical commits/diffs for earlier login/auth implementation.
- [x] Map current dashboard/API access flow and affected clients: web, API, WebSocket, iOS/macOS settings.
- [x] Choose minimal auth design based on prior implementation and current architecture.
- [x] Implement authorization with tests or focused verification.
- [x] Run local verification commands from project `AGENTS.md` where possible.
- [x] Commit changes, push branch, deploy server files, and report verification steps.

## Verification
- Git branch is not `main` and contains only intended changes.
- Auth endpoints/guards are covered by automated tests or a reproducible local smoke check.
- Existing `/api/stats` and `/api/live` clients have a defined auth path.
- No secret values are committed.
- Python/JS/Swift checks run where environment permits.

## Risks / pitfalls
- Auth may have existed in history but been removed for a reason; inspect decision docs before restoring blindly.
- WebSocket authorization needs separate handling from HTTP page/API routes.
- iOS client may need token/password storage and URL configuration updates.
- If Tailscale Funnel/Serve remains the ingress, app auth must not assume client IP or Tailscale identity.

## Status
Current status: done

## Notes
- 2026-04-30: Branch `feat/auth-without-tailscale-login` created at `8ba273b` before investigation.
- 2026-04-30: Prior auth implementation found in the parent of commit `74f0281` (the commit that removed Tailscale-independent auth).
- 2026-04-30: Local implementation restores Flask browser login/session auth, Basic Auth for API/WebSocket/native clients, iOS Keychain password storage, and Settings UI username/password fields.
- 2026-04-30: Verification passed: Python compile, JS syntax check, Flask auth smoke test, `git diff --check`. Swift typecheck skipped because `swiftc` is unavailable on this host.
- 2026-04-30: Pushed branch `feat/auth-without-tailscale-login`; deployed dashboard files to `/home/konstantin/dashboard`; configured systemd auth env file; enabled Tailscale Funnel so the login page is internet-reachable without tailnet login; service restarted active; public login/API/live checks passed.
