---
name: test-driven-development
description: Use when changing Python behavior with test-first workflow: RED, GREEN, REFACTOR, VERIFY.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [python, testing, pytest, tdd, red-green-refactor, quality]
    related_skills: [systematic-debugging, writing-plans, subagent-driven-development]
---

# Test-Driven Development

## Goal
Change Python behavior safely by proving the expected behavior with a failing test first, then making the smallest code change that turns the test green.

## When to Use
Use for Python code changes that affect behavior:
- new behavior;
- bug fixes;
- behavior changes;
- risky refactoring;
- legacy code changes where behavior must be preserved.

## Modes
- New behavior: write one failing pytest test for the next observable behavior.
- Bug fix: write or identify a regression test that fails because of the bug.
- Refactor: first prove current behavior is covered; add characterization tests if coverage is weak.
- Spike/exploration: allowed only as throwaway work. Do not commit spike code as production.

## Steps
1. Inspect the project’s existing test style and commands before editing.
2. Run a relevant baseline test when practical.
3. Write one focused pytest test for the next observable behavior.
4. Run only that test and confirm RED:
   - it fails;
   - it fails for the expected reason;
   - the failure proves missing or broken behavior, not a typo or setup error.
5. Write the smallest production code change needed for GREEN.
6. Run the same targeted test and confirm it passes.
7. Refactor only after GREEN; do not add behavior during refactor.
8. Run relevant tests, then the full suite when practical.
9. Run project lint, format, and type checks if the project already uses them.
10. Commit the completed change after successful checks.

## Python Test Rules
- Prefer pytest and the project’s existing conventions.
- Test observable behavior, not private implementation details.
- Test through public functions, CLI boundaries, stable module APIs, or documented integration points.
- Test internal helpers directly only when they contain real domain logic, parsing, validation, branching, or error handling.
- Use parametrization for related edge cases.
- Use fixtures for repeated setup, but keep each test readable.
- Use monkeypatch or mocks only at external boundaries: network, filesystem, time, environment, subprocess, database, API clients, or LLM clients.
- Do not mock your own domain logic just to make a test pass.
- Do not finish with temporary hardcode, throwaway spike code, or knowingly incomplete edge-case handling.

## Output
Final reply must include:
- changed behavior;
- tests added or changed;
- RED command and expected failure summary;
- GREEN command result;
- relevant or full test command result;
- lint, format, or typecheck result when used;
- commit hash.

## Check
Before completion:
- focused test exists for the changed behavior;
- RED was observed, unless this is pure refactor with existing coverage;
- GREEN was observed on the targeted test;
- relevant tests pass;
- full suite was run, or the reason for not running it is stated;
- no unrelated code was rewritten;
- no temporary hardcode or spike code remains;
- final commit is created.

## Stop
Stop and report instead of guessing if:
- expected behavior is ambiguous;
- baseline tests fail for unrelated reasons;
- the test command cannot run because dependencies or environment are missing;
- required credentials, network, or services are unavailable;
- the fix requires unrelated architecture changes.

## References
- `references/python-pytest-patterns.md` — open when test design is non-trivial.
- `references/legacy-refactor-and-bugfix.md` — open for bug fixes, legacy code, missing tests, or pure refactoring.

## Do Not
- Do not write production code for new behavior before a failing test.
- Do not claim TDD if RED was not observed.
- Do not change tests after GREEN just to fit the implementation.
- Do not test implementation details when behavior can be tested through a stable boundary.
- Do not delete existing user or project code merely because it lacks test-first history.
- Do not commit failing tests or unfinished spike code.
