# CLI Maintenance Notes

Use this when modifying or auditing the flight-search CLI, `agent_report` contract, provider layers, or coverage controls. It is not needed for ordinary flight answers.

## Workflow

- Work offline by default. Do not run live provider searches unless the user asks.
- Add a focused failing test before behavior changes.
- For date behavior, test both the parser layer and the subprocess CLI contract. Past `depart-date`/`return-date` values must fail before provider search with `validation_error`, and short `DD.MM` dates must normalize to the nearest future occurrence rather than a past year.
- Preserve `--json --agent-brief` as JSON-only stdout. For JSON error cases, expect empty stdout and parse the error payload from stderr.
- If `agent_report.v1` fields change, update schema, contract tests, docs, and `report-contract.md` together.
- Keep compact schemas under existing line/byte gates; use deterministic compact formatting if pretty output breaks contract limits.
- Run a real parser smoke command for new documented flags; tests that instantiate `argparse.Namespace` do not prove the CLI accepts the flag.

## Security Rules

- Travelpayouts Data API fetches must send credentials in the `X-Access-Token` header, not URL/query params.
- Request metadata and human output may expose only auth status (`present`/`missing`) and transport (`header`), never credential values.
- Reject credential-like query-param keys before network I/O and in dry-run request builders.
- FLI MCP URL policy: allow `http` only for loopback hosts (`localhost`, `127.0.0.1`, `::1`); require `https` for remote hosts; reject unsupported schemes and any userinfo, including empty userinfo.
- Test fixtures should avoid scanner-triggering literals. Prefer neutral placeholders such as `test-placeholder-001`.
- Chat summaries of audits should include counts/classes/paths only; keep evidence and credential-like values redacted.

## Coverage-Control Rules

- Domestic-RU routing must be decided in one shared layer and propagated through `route plan`, `kb-assemble`, and `live-assemble`.
- Route-family metadata and segment-spec identity belong in shared route-graph helpers. Do not duplicate `ru-priority`, `asia-oceania`, or `domestic-ru` family definitions across dry and live planners.
- For domestic Russian round trips, assert the direct return segment `DEST -> ORIGIN` and absence of default international hubs such as `IST`, `DXB`, or `SHJ`.
- Keep `route_graph`, `routing_strategy`, `coverage_controls`, and `airport_scope` consistent across public builders.
- Moscow/SVO controls are first-class controls, not fallback-only behavior. Do not let new Moscow categories suppress existing `all_su_svo`, `all_su`, or `single_carrier` controls.
- New live coverage probes need query-budget design: provider-aware cache keys, in-run de-duplication, bounded per-provider concurrency, rate-limit backoff, and live/cache/stale labels.

## Assembly and Stop-Policy Rules

- Candidate generation is stop-policy-first. Generate direct/one-stop preferred candidates before fallback candidates; do not let T2/T3 routes consume `candidate_pool_limit` while preferred candidates still exist.
- `candidate_pool_limit` is a safety/debug cap inside the active generation mode, not a quality workaround. Do not raise it to hide generation-order defects.
- Use the shared stop-policy decision helper for assembly, ranking defense, provider aggregate projection, and report diagnostics. Do not reimplement reportability as a local `connections <= 2` check.
- `agent_report.v1` projects declared generation state. Do not infer fallback mode from compact projected options alone.

## Version Bump Checklist

When bumping the flight-search skill or CLI version, update **all three** locations together:

1. `SKILL.md` frontmatter — `version: X.Y.Z`
2. `cli/flights_cli/__init__.py` — `__version__` and `__skill_version__`
3. `cli/pyproject.toml` — `version = "X.Y.Z"` under `[project]`

Missing any one of these causes drift between `doctor` output, CLI `--version`, and skill metadata.

## Verification Baseline

Run the narrowest relevant tests first, then broaden:

```bash
cd ~/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_agent_report_contract.py'
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python -m flights_cli --json doctor
git diff --check -- skills/productivity/flight-search
```

After test/smoke/install flows, remove generated `__pycache__`, `.pyc`, and `*.egg-info` artifacts before final audit. If an independent review adds new changes after a green run, rerun the affected gates before reporting done.

## Useful Future CLI Commands

Consider these only when a real failure justifies them:

- `flights providers doctor` or `flights doctor --strict` for provider readiness and degradation explanations.
- `flights route validate-report --input result.json` for schema and semantic checks.
- `flights docs sync-check` for drift between live `--help`, SKILL.md, README, dependency metadata, and provider requirements.
