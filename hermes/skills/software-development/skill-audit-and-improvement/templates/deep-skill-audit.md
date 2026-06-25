# Deep skill audit worksheet

Use this worksheet only for high-impact, ambiguous, or user-corrected skills. For routine lint/doc edits, use the compact final report instead.

## Target

- Skill: `<name/path>`
- Request class: `<audit | improve | shrink | create | CLI/schema review | cleanup>`
- Scope: `<read-only | source edit | runtime-only | docs/plan>`
- Source evidence: `<branch/head/status/path>`

## Audit question

What future mistake should this skill prevent, and how will we know the skill now prevents it?

## Scenario list

| Scenario | Prompt/task | Expected behavior | Evidence | Result |
|---|---|---|---|---|
| Simple path | `<ordinary request>` | `<golden path>` | `<proof>` | `<pass/gap/unknown>` |
| Edge path | `<ambiguous/source-runtime split>` | `<decision/fallback>` | `<proof>` | `<pass/gap/unknown>` |
| Failure path | `<missing tool/partial evidence>` | `<honest fallback>` | `<proof>` | `<pass/gap/unknown>` |
| Dangerous side effect | `<credential/service/external mutation>` | `<approval boundary>` | `<proof>` | `<pass/gap/unknown>` |

## Expected behavior

- Golden path: `<default route>`
- Anti-paths: `<wrong routes to block or require fallback>`
- Stop conditions: `<when to ask or refuse mutation>`
- Verification: `<read-back/test/audit command>`

## Observed gap

- Current behavior: `<what the skill allows or misses>`
- Root cause: `<missing trigger/evidence gate/layering/verification/stop condition>`
- Severity: `<blocker | warning | recommendation | info>`

## Recommended change

- Target layer: `<SKILL.md | references | templates | scripts | schemas | no durable change>`
- Minimal patch: `<specific edit>`
- Why this layer: `<reason>`

## Verification command/test

```bash
<command>
```

Expected result:

```text
<result>
```

## Final decision

Choose one:

- `pass` — skill already changes behavior and prevents the target mistake.
- `needs patch` — main operational path is missing or wrong.
- `needs reference` — long reusable knowledge belongs in references.
- `needs template` — future agents need a reusable worksheet/report shape.
- `needs script` — deterministic check/redaction/normalization is required.
- `needs source change` — runtime-only change is insufficient.
- `no durable change` — finding is session-specific or already covered.
