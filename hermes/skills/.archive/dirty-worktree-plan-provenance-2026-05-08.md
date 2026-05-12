# Dirty Worktree Plan Provenance Case — 2026-05-08

## Context

After a scoped skill change was committed and pushed, the repository remained dirty. The user asked whether the dirty state came from unfinished plans.

## Reusable lesson

A dirty worktree after a verified scoped commit is not automatically failed cleanup, and not automatically safe to commit. Treat it as a provenance problem:

1. Verify branch, HEAD, remote, and exact dirty paths from live Git state.
2. Confirm the just-committed scope by checking the committed paths and staged paths, not memory.
3. Map each dirty path to active plans, recent commits, and changed-skill audit results.
4. Classify paths as:
   - committed-work leftovers that should be finished or separately committed;
   - active-plan work that should stay dirty or move to its own branch;
   - completed-but-unarchived plan notes;
   - unrelated or pre-existing changes that must not be staged.
5. Run metadata-only changed-skill audit before recommending commit; do not print secret-like values from examples or findings.
6. Report whether the dirty state is caused by the just-finished task, by older/in-progress plans, or by unrelated work.

## Observed pattern

In this case, the finished knowledge CLI P3 commit was scoped and pushed. Remaining dirty paths belonged to several separate skill/documentation workstreams: Ollama routing notes, skill-audit/workflow hardening, and native MCP/Context7 documentation. Some changed files triggered `secret_like_value` audit blockers due placeholder examples, so a broad commit would have been unsafe.

## Safe response pattern

- State the verified commit/remote status first.
- Say “not from the just-finished scoped commit” only after checking paths.
- Use “partly from unfinished/unclosed plans” when dirty files map to active or not-yet-archived plans.
- Recommend split cleanup: separate commits by workstream, fix audit blockers first, and leave unrelated dirty files untouched.
