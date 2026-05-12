# Skill Audit and Improvement Skill Plan

> **For Hermes:** implement directly in the active Hermes source repo after branch/status verification.

**Goal:** Create a reusable skill that governs how agents audit, improve, verify, and commit Hermes skills and skill-owned CLIs.

**Active source:** `/home/konstantin/.hermes/hermes-agent/skills/`

**Branch at planning time:** `skills-improvements` @ `f5fbba250867`

---

## Scope

- Create `skills/software-development/skill-audit-and-improvement/SKILL.md`.
- Add reusable support files under `references/`, `templates/`, and/or `scripts/` if they make the workflow executable.
- Integrate the already-relevant dirty `hermes-agent-skill-authoring` post-session review note as a bridge to the new skill, without overwriting unrelated changes.
- Validate frontmatter, stale path references, secret patterns, and skill quality checks.
- Commit and push on the current tracked branch if verification passes.

## Analysis from the previous work

Observed useful workflow signals:

1. Good: provenance checks before editing prevented stale source/runtime assumptions.
2. Good: owning-skill CLI pattern made deterministic verification reusable.
3. Good: independent review caught Basic Auth redirect risk that self-review missed.
4. Good: secret/stale-path scans should be a standard skill-audit gate.
5. Risk: creating or patching skills without committing leaves the backup unable to reproduce the state.
6. Risk: post-session skill updates can become fragmented unless governed by a class-level audit/improvement skill.

## Tasks

1. Confirm repo status and existing similar skills.
2. Draft the new skill with explicit triggers, audit rubric, improvement decision tree, validation gates, and report format.
3. Add a compact audit report template and optional read-only audit helper script.
4. Patch `hermes-agent-skill-authoring` to point to the new workflow.
5. Run validation and security/stale-path scans.
6. Commit and push.
