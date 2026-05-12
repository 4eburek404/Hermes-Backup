# systemd-web-service-deployment Skill + CLI Improvement Plan

> **For Hermes:** Implement in the active Hermes development repo only after checking branch, HEAD, target-path diff, and unrelated dirty state.

**Goal:** Clean and optimize the `systemd-web-service-deployment` skill, normalize its references, and add a safe read-only owning-skill CLI for systemd web-service inspection and verification.

**Architecture:** Keep `SKILL.md` as the compact decision/runbook layer. Move long executable snippets and incident details into `references/`. Add `skills/devops/systemd-web-service-deployment/cli/` as a self-contained Python module with JSON-first read-only commands; mutating deploy/restart actions are intentionally out of scope.

**Tech Stack:** Markdown skill/reference files; Python stdlib CLI; local validation via Python/yaml; optional live checks using `systemctl`, `journalctl`, `ss`, `curl`, `tailscale`, `docker` when present.

---

## Task 1: Baseline and Audit

**Objective:** Confirm the active repo/branch and target skill state before writes.

**Files:**
- Inspect: `/home/konstantin/.hermes/hermes-agent/skills/devops/systemd-web-service-deployment/`

**Steps:**
1. Run `git status --short`, `git branch --show-current`, and `git rev-parse --short HEAD` in `/home/konstantin/.hermes/hermes-agent`.
2. Confirm `git diff -- skills/devops/systemd-web-service-deployment` is empty before editing.
3. Read `SKILL.md` and all `references/*.md`.
4. Identify redundant headers, stale command pointers, unsafe secret handling, and CLI-worthy repeated checks.

## Task 2: Rewrite the Skill Core

**Objective:** Make `SKILL.md` shorter, more direct, and better connected to the future CLI.

**Files:**
- Modify: `skills/devops/systemd-web-service-deployment/SKILL.md`

**Steps:**
1. Preserve valid frontmatter and description.
2. Replace repeated “snippet moved…” prose with a compact workflow table/list.
3. Add explicit CLI section: read-only by default, JSON report, no secrets printed, no deploy/restart unless future explicit `--apply` command exists.
4. Keep mandatory production checks: live host, service, ingress, backup, env/secrets, narrow artifacts, restart/log verification, local/public/auth/realtime verification, rollback.
5. Keep incident/Docker pointers concise and reference detailed docs.

## Task 3: Normalize References

**Objective:** Clean navigation and remove mechanical duplication in reference files.

**Files:**
- Modify: `references/deployment-command-cookbook.md`
- Leave incident files mostly intact unless obvious heading/secret cleanup is needed.

**Steps:**
1. Fix duplicate numbered headings like `## 1. 1.`.
2. Group snippets by workflow: preflight, backup, env/drop-in, deploy, restart/verify, ingress/Funnel, rollback, Docker diagnosis.
3. Use placeholders for all service/path/secret values.
4. Avoid printing secret values; show commands that test presence or source env safely.
5. Preserve useful one-liners and rollback commands.

## Task 4: Add Minimal Owning-Skill CLI

**Objective:** Add a safe CLI that audits systemd web services and emits machine-readable reports.

**Files:**
- Create: `skills/devops/systemd-web-service-deployment/cli/systemd_web_service_cli/__init__.py`
- Create: `skills/devops/systemd-web-service-deployment/cli/systemd_web_service_cli/__main__.py`
- Create: `skills/devops/systemd-web-service-deployment/cli/README.md`

**Commands:**
- `python3 -m systemd_web_service_cli --json doctor`
- `python3 -m systemd_web_service_cli --json inspect --service NAME [--url URL ...] [--required-env VAR ...]`
- `python3 -m systemd_web_service_cli --json docker-bind-diagnose --path PATH [--expected-uid UID] [--expected-gid GID]`

**Rules:**
1. Read-only only.
2. Redact env values and suspicious tokens.
3. Never restart services, write files, enable Funnel, or change Docker permissions.
4. Return JSON with `ok`, `command`, `data`, and `issues`.

## Task 5: Verify

**Objective:** Prove the modified skill and CLI are safe and usable.

**Checks:**
1. Validate frontmatter and size constraints for `SKILL.md`.
2. Run CLI doctor from the owning `cli/` dir.
3. Run CLI inspect against a likely harmless service if available, otherwise doctor only.
4. Compile Python module with `python3 -m compileall`.
5. Search touched files for obvious unredacted secrets.
6. Show `git diff --stat` and `git status --short`.

## Out of Scope

- No commit/push unless explicitly requested.
- No live production restart or deployment.
- No writing to `/home/konstantin/code/clis`, `local/skill-clis`, or runtime `~/.hermes/skills`.
