# flight-cli-past-date-reject — 2026-05-10

## Scope
Implement CLI-side rejection of past departure/return dates in the flight-search skill-owned CLI.

## Constraints
- Start from up-to-date `main`.
- Work on a new branch.
- TDD: add failing regression test before production code.
- Do not touch unrelated dirty/untracked files.
- Do not modify SKILL.md unless explicitly requested.

## Steps
1. Verify repo status and update `main` from `origin/main`.
2. Create a feature branch.
3. Add focused failing tests for past `--depart-date` and, if applicable, past `--return-date` / return-before-departure behavior.
4. Implement minimal validation in the shared date parser or command boundary.
5. Run focused tests, then flight-search CLI test suite.
6. Report touched files, verification, remaining dirty/untracked state, rollback.
