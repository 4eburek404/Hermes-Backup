# External-source plan review pattern

Use when a durable plan depends on an external repository, API, project, or current internet state and Konstantin asks to analyze it with internet checking before possible updates.

## Session-derived recipe

Example trigger: "План searcharvester подними, анализируй, ищи в интернете, при необходимости предложи обновления".

1. **Read local control surface first**
   - Load `konstantin-plan-governance` and read `/home/konstantin/docs/plans/README.md`.
   - Read the target plan from `/home/konstantin/docs/plans/`.
   - Use `session_search` / `fact_store` when the plan references previous work or a named project.

2. **Check local source state**
   - If the plan references a local clone, inspect local git status/head/remote without mutating it.
   - Confirm whether local HEAD matches the upstream state before treating local files as current.

3. **Check internet/upstream state**
   - Query GitHub/API/current web source for default branch, latest commit, tags/releases, open PRs/issues, and relevant raw files.
   - Pull only concise evidence into the plan: latest commit, local-vs-remote result, release/PR status, and issues that affect the plan's priority.

4. **Answer analysis-first**
   - If user asked to analyze/propose, do not edit the plan yet.
   - Give verdict, checked evidence, and exact proposed edits.

5. **When user approves update**
   - Apply the patch.
   - Fix naming-policy drift if the active plan lacks `YYYY-MM-DD-` prefix.
   - Add a short note under `## Notes` with what changed.
   - Verify required sections and `## Status` first-line machine-readable form.
   - Confirm old path absent if renamed and new path present.

## Useful evidence fields

- `repo/default_branch`
- latest remote commit SHA/date/message
- local HEAD SHA and whether it matches remote
- tags/releases/open PRs
- open issues that change plan priority or scope
- exact files/lines/patterns that confirm the plan's assumptions

## Pitfalls

- Do not use an external issue to expand current scope unless it directly changes the plan's P0/P1 work; record unrelated issues as deferred/P3 context.
- Do not mutate during an analysis-only request. Mutation starts after explicit approval such as "обнови план".
- Do not leave a renamed plan with stale references to the old path in `## Notes`; it is fine to preserve history, but add the new path/update note first.
