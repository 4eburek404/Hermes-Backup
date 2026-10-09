# GitHub development skills

GitHub workflows follow the same mandatory BDD rule as the software-development
skills.

## Behavioral boundary

GitHub skills are evaluated by externally meaningful states and effects:

- whether the live/current issue state was understood;
- whether the requested software behavior was achieved;
- whether review found material problems without modifying reviewed work;
- whether the intended commit/branch/PR state was actually created or observed;
- whether CI, review, merge, cleanup, and release states are reported separately;
- whether unrelated user work is preserved.

The name of the skill that performed a step is not itself a behavioral
requirement. Routing and 'skill_view' evidence are diagnostic unless a platform
contract explicitly makes a particular routing decision observable.

## Migration status

'github-code-review' already has an agent-level fixture eval whose useful
acceptance properties are behavioral (findings, no mutation, evidence handling).

The older 'tests/contract/test_github_*_contract.py' checks inspect 'SKILL.md'
text and structure. They are migration-era checks, not the target BDD
specification. Do not extend them with new wording/name requirements.

'github-pr-workflow' remains intentionally unimplemented. Its existing
source-text RED contract must not be turned GREEN by writing prose to satisfy
regular expressions. First migrate its useful requirements into behavioral
scenarios, then implement the smallest workflow that makes those scenarios pass.

## Review order

1. establish behavioral scenarios and baseline evidence;
2. review/revise software-development ownership;
3. rerun the same scenarios;
4. review/revise GitHub orchestration and review;
5. replace the useful parts of the PR-delivery RED contract with behavioral
   delivery scenarios;
6. only then implement the delivery owner;
7. retire source-text contracts after equivalent behavioral coverage exists.
