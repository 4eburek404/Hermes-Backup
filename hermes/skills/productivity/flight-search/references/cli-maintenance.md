# CLI Maintenance Notes

Keep CLI maintenance focused on current live provider assembly and the `agent_report` contract.

## Workflow

- Work offline by default unless a task explicitly requires live provider access.
- Add or update tests before behavior changes.
- Keep `agent_report` schema, docs, fixtures, and tests coupled in the same change.
- Keep search behavior limited to current live provider assembly.
- Static catalogs are metadata only: city, airport, airline, and aircraft data. Flight options come from live provider assembly.

## JSON stdout/stderr Rules

- In `--json` mode, stdout must contain only the JSON envelope.
- Diagnostics, warnings, and provider logs belong on stderr or inside structured JSON fields.
- Do not print secrets, full credential paths, or unredacted provider URLs with sensitive query data.
- If an error occurs, return the standard JSON error envelope with a concrete layer and actionable detail.

## Provider URL Safety for FLI MCP

- Treat FLI MCP as a sidecar selected by URL/config.
- Validate URL shape before network use.
- Do not log sensitive query parameters unnecessarily.
- If the sidecar is unavailable, report degradation through provider failure fields rather than hiding the failure.

## Schema, Docs, and Tests Coupling

When changing `data.agent_report`:

1. Update the schema contract.
2. Update report-building code.
3. Update docs that tell agents how to read the fields.
4. Update fixtures and tests that assert the contract.
5. Re-run the focused contract tests before any broader validation.

Do not add answer-facing fields without documenting how the agent should use them.

## Version Bump Checklist

When bumping the skill/CLI version, keep these aligned:

- `hermes/skills/productivity/flight-search/SKILL.md` frontmatter.
- `hermes/skills/productivity/flight-search/cli/pyproject.toml`.
- `hermes/skills/productivity/flight-search/cli/flights_cli/__init__.py`.
- Tests that assert the CLI version or doctor envelope.

Do not change schema version constants unless the schema contract itself changes incompatibly.

## Generated Artifact Cleanup

Before final reporting, check for generated files under the skill tree:

```bash
find hermes/skills/productivity/flight-search -type d -name __pycache__ -o -name '*.pyc'
```

Remove generated artifacts only when cleanup is in scope. Prefer `PYTHONDONTWRITEBYTECODE=1` for validation commands.

## Source/Runtime Validation Pointer

Source edits happen under `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search`. Runtime state under `/home/konstantin/.hermes/skills/productivity/flight-search` is a separate deployment/sync surface.

Before claiming a source edit is ready, report branch, HEAD, dirty state, changed files, validation commands, and whether runtime sync was intentionally not performed.
