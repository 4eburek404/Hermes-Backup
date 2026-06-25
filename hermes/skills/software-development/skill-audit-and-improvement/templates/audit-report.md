# Audit report

## Changed

- `<path>` — `<change>`
- `<path>` — `<change>`

## Why

- Request class: `<audit | improve | shrink | create | CLI/schema review | cleanup>`
- Concrete cause: `<finding / user correction / failing test / source-runtime mismatch>`
- Behavior delta: `<what future agent behavior changes, or not applicable>`

## Verified

| Check | Result |
|---|---|
| Branch/status checked | `<command/result>` |
| Static audit | `<command/result>` |
| Tests or focused checks | `<command/result>` |
| Report schema validation | `<command/result or not applicable>` |
| Generated artifacts absent | `<command/result>` |
| Secrets redacted | `<evidence or not applicable>` |

## Remaining

- `<baseline issue, risk, or follow-up>`

## Commit state

- Branch: `<branch>`
- Commit: `<sha/message or not committed>`
- Push/PR: `<state>`
- Rollback: `<git revert <sha> or file restore path>`

<details>
<summary>Optional: deep audit</summary>

## Scenario coverage

| Scenario | Result | Evidence |
|---|---|---|
| Simple path | `<pass/gap/unknown>` | `<evidence>` |
| Edge path | `<pass/gap/unknown>` | `<evidence>` |
| Failure path | `<pass/gap/unknown>` | `<evidence>` |
| Dangerous side effect | `<pass/gap/unknown>` | `<evidence>` |

## Gap analysis

- Behavior before: `<summary>`
- Behavior after: `<summary>`
- Golden path: `<summary>`
- Anti-paths checked: `<summary>`
- Mistake prevented: `<summary>`

</details>

<details>
<summary>Optional: CLI/schema audit</summary>

## CLI contract findings

- Mode: `<static | advisory>`
- Execution performed: `<true | false>`
- Enforced: `false unless explicit future enforcement flag exists`
- Entrypoints: `<list or none>`
- Mutating candidates blocked/skipped: `<list or none>`

## Schema findings

- Decision: `<not_applicable | optional | recommended | required>`
- Schemas found: `<count>`
- Doctor envelope: `<valid | invalid | skipped | not applicable>`
- Schema-output mappings: `<count/confidence summary>`

## Evidence

- `<evidence id/path/command/result>`

</details>
