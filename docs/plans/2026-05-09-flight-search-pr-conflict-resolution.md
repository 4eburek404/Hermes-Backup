# Flight-search PR conflict resolution

Current status: completed / pushed

## Goal
Resolve conflicts for branch `feat/flight-search-agent-report-controls` against `origin/main`, preserving the flight-search agent-report improvements and the upstream security/runtime fixes.

## Scope
- Repo: `/home/konstantin/.hermes/hermes-agent`
- Branch: `feat/flight-search-agent-report-controls`
- Base: `origin/main`
- Resolve conflicts only under `skills/productivity/flight-search` unless git proves another path is required.
- Preserve unrelated dirty files outside flight-search; do not stage/commit them.

## Strategy
1. Fetch `origin` and inspect branch/base divergence.
2. Prefer a normal merge of `origin/main` into the feature branch to avoid force-push on an already-pushed branch.
3. Resolve content conflicts by keeping both sets of intended behavior:
   - upstream security/runtime/output fixes from `origin/main`;
   - local P0 `detail_status`/compact recommendation completeness;
   - local P1 `moscow_gateway_control`;
   - local overnight/long-wait `tradeoffs` instead of risk penalty;
   - obsolete `aeroflot_research/` stays deleted.
4. Verify offline: focused tests, full flight-search CLI suite, doctor, diff-check, pycache cleanup/check.
5. Commit conflict resolution and push; verify remote SHA matches local.

## Findings
- Feature branch was 1 commit ahead and 2 commits behind `origin/main`.
- Current dirty files outside flight-search were unrelated and left untouched.
- `origin/main` changed flight-search files, and the actual manual conflict was in `skills/productivity/flight-search/SKILL.md`.
- Upstream renamed `skills/productivity/flight-search/agents/openai.yaml` to `skills/productivity/flight-search/assets/openai.yaml`; merge keeps the upstream asset layout.

## Resolution
- Merged `origin/main` into `feat/flight-search-agent-report-controls` with `--no-commit`.
- Resolved `SKILL.md` by combining:
  - local `Improving the CLI` guidance for P0/P1/overnight agent-report work;
  - upstream `Common Pitfalls` and `Verification Checklist` for Travelpayouts header auth, FLI MCP URL policy, and audit hygiene;
  - both local operational references and upstream security/audit references.
- No conflict markers remain under `skills/productivity/flight-search`.

## Verification
Offline only; no live flight/provider searches.

- `test_agent_report_p0_completeness.py`: 1 test OK.
- `test_agent_report_p1_moscow_control.py`: 1 test OK.
- `test_agent_report_overnight_tradeoffs.py`: 1 test OK.
- `test_agent_report_contract.py`: 12 tests OK.
- `test_cli_contract.py`: 10 tests OK.
- `test_fli_mcp.py`: 11 tests OK.
- `test_travelpayouts_layers.py`: 10 tests OK.
- `test_route_workflows.py -k agent_report`: 1 test OK.
- Full flight-search CLI suite: 99 tests OK.
- `python3 -m flights_cli --json doctor`: exit 0, `ok=true`.
- `git diff --cached --check -- skills/productivity/flight-search`: clean.
- `git diff --check -- skills/productivity/flight-search`: clean.
- `audit_skill.py --skill flight-search --json`: exit 0, blockers 0, warnings 0.
- `audit_skill.py --changed --json`: no flight-search findings; unrelated dirty files outside scope still have existing findings and were not staged.
- `__pycache__` / `*.pyc` under `flight-search/cli`: absent.

## Commit and push
- Commit: `6fa1d4bec5b3eff2c868c01d979901b14dc733a4` (`chore(flight-search): resolve main merge conflicts`).
- Push: `origin/feat/flight-search-agent-report-controls`.
- Remote SHA: `6fa1d4bec5b3eff2c868c01d979901b14dc733a4`.
- Local/remote match: true.
- `skills/productivity/flight-search` working tree is clean after push.
- Unrelated dirty files outside flight-search remain untouched.
