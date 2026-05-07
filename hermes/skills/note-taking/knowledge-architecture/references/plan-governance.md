# Plan Governance — Detailed Workflow

Create, update, close, archive, or review durable multi-step plans for Konstantin.

## Key Principle

This is a **thin procedural hook**. The canonical source of truth is:

```
/home/konstantin/docs/plans/README.md
```

Do not duplicate that policy here. If policy changes, update the README first.

Layering model:

- **This reference**: thin trigger, routing, and enforcement hook
- **`/home/konstantin/docs/plans/README.md`**: full canonical policy
- **Holographic `fact_store`**: retrieval pointer and durable atomic facts
- **Built-in memory**: always-on index to the docs system
- **Builtin `plan` / `writing-plans` skills**: generic plan mechanics and implementation-plan quality standards

## When to Use

- Create, update, execute from, close, archive, or review a multi-step plan for Konstantin
- Work inside `/home/konstantin/docs/plans/`
- Decide where an AI-agent plan should live
- Clean up plan status, root/archive layout, or plan lifecycle
- Reconcile a plan with docs, skills, holographic memory, or session history
- Before any multi-step task that changes durable Hermes state for Konstantin (docs, memory, skills, cron, config, credentials)

Do NOT use this to override an explicit user/project-local instruction. If the user or repository asks for a different plan path, follow that path and label the scope as project-local.

## Mandatory Workflow

Before mutating plan state:

1. Read `/home/konstantin/docs/plans/README.md`
2. Check whether a relevant active plan already exists in `/home/konstantin/docs/plans/`
3. Default path: `/home/konstantin/docs/plans/YYYY-MM-DD-short-topic.md`
4. Root clean: only `README.md` + active `planned`, `in_progress`, or `blocked` plans
5. Keep plan status machine-readable: `Current status: in_progress`
6. Before final response, update verification/status and archive closed plans
7. Promote durable outcomes to the right layer:
   - `../infrastructure.md` for current system facts
   - `../runbooks.md` for short repeatable procedures
   - Hermes skills for executable workflows
   - holographic `fact_store` for short durable facts / retrieval hooks
   - `session_search` for raw history and temporary progress

## Boundary Rules

- Do NOT copy the full canonical policy into this reference. Update `/home/konstantin/docs/plans/README.md` first.
- Do NOT edit builtin `plan` or `writing-plans` to encode Konstantin-specific policy; builtin skills may be overwritten by Hermes updates.
- Do NOT leave completed plans in root.
- Do NOT store secrets, raw logs, full transcripts, or token-like values in plans.
- Do NOT treat archived plans as current source of truth without checking current docs/config/tools.

## Plan Governance Pitfalls

1. Falling back to `.hermes/plans/` mechanically. For Konstantin's durable agent plans, use `/home/konstantin/docs/plans/` unless explicitly told otherwise.
2. Duplicating the README in this reference. That creates two policies and future drift. Stay small.
3. Overriding project-local conventions. If the user is working inside a repository with its own plan location, use the requested project path.
4. Leaving status in prose only. The first status line must remain machine-readable: `Current status: ...`.
5. Treating a completed plan as memory. Plans are control surface and audit trail. Durable knowledge belongs in docs, skills, or holographic memory.