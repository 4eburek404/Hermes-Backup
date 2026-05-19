# Travelpayouts Price-Surface Retirement

Use this when maintaining the flight-search CLI or auditing hidden Travelpayouts/Aviasales price-search paths.

## Durable Rule

Travelpayouts remains a static reference-catalog provider only. Cached Travelpayouts/Aviasales price search must not be in the normal route/search path. If retained temporarily for migration, it must be fail-closed behind explicit legacy/debug gates and excluded from `doctor`, docs examples, wrappers, and route-plan output.

## Surfaces to Audit

Repository/source-tree scope:

- Check every flight-search copy in the repo before committing. Hermes backups can contain both the runtime skill tree (`hermes/skills/productivity/flight-search/...`) and a source/distribution mirror (`cli/skill-clis/flights/...`). Do not treat one clean tree as complete while the other still exposes Travelpayouts price search.
- If both trees exist, patch and test both or explicitly document why one is out of scope/stale.

Executable/parser surfaces:

- `flights_cli/cli.py` parser commands such as `request search`, `request prices-for-dates`, `request grouped-prices`, and `results parse`.
- output renderers that keep those commands usable or documented.
- route orchestration fields that emit Aviasales/manual price links, especially `manual_links` and `metrics.without_cli.manual_direct_links` / `manual_aviasales_links`.

Provider/helper surfaces:

- GraphQL cached-search builders/fetchers and parsers.
- Data API cached price endpoints such as `prices_for_dates` and `grouped_prices`.
- Aviasales URL builders and marker/token-dependent price-link helpers.
- wrappers, Makefile examples, README/debug-playbook snippets, and test helpers that parse Travelpayouts raw fixtures.

Allowed surface:

- static catalogs under `api.travelpayouts.com/data/...` for airports, cities, airlines, countries, alliances, and aircraft metadata.

## Contract Shape

Add tests before implementation. Minimum invariants:

- normal route/search commands run without Travelpayouts token and without cached price calls;
- `doctor` reports `travelpayouts_usage = static_catalog_only` and `travelpayouts_price_search_enabled = false`;
- cached price commands are absent or return a clear legacy-disabled error before credential checks or network I/O;
- route-plan output contains no Aviasales/manual price links;
- package/source scan allows static catalog URLs but blocks `graphql/v1/query`, `prices_for_dates`, `grouped_prices`, `aviasales.ru/search`, and `aviasales.com` in executable paths;
- docs and examples do not teach agents to use cached TP/Aviasales price probes.

## Migration Notes

If existing route workflow tests rely on `results parse` or raw Travelpayouts GraphQL fixtures, replace them with direct normalized segment fixtures. Do not preserve a deprecated parser solely to keep fixtures convenient.

When the user asks for a branch + commit in a GitHub repo, finish the source-tree audit before the commit: `git status --short --branch`, scan both possible CLI roots, run targeted tests for each changed tree, then commit. If tool/time limits are likely, prefer a small verified commit over leaving a branch with only uncommitted runtime-tree changes.

If work is interrupted by disk-full, context compaction, or tool-call limits, resume from live provenance rather than the compacted task label alone: re-check branch/status, rerun the Travelpayouts surface scan, and classify remaining hits as executable paths, active docs/examples, tests/fixtures, or historical artifacts before reporting completion. Stale generated/historical files under `docs/plans/...` may need an explicit archive/update decision, but they are not proof that the normal CLI path still calls cached Travelpayouts prices.

When auditing after multiple resumed runs, separate active flight-search scope from broader repository leftovers. A useful final scan classifies hits as: active executable/config, active docs/skill, active tests/fixtures, historical plan artifacts, and other legacy/plugin trees. Do not block the flight-search retirement claim on historical `docs/plans/...` or separate plugin hits, but report them explicitly as out-of-scope residuals if they still mention Aviasales/Travelpayouts price surfaces.

Tests and `make test smoke` can regenerate `__pycache__`/`.pyc` even after an earlier cleanup. Always run generated-artifact cleanup *after* the final full test/smoke pass, then re-scan before staging. If a final verification pass is interrupted by the tool-call limit, report cleanup/read-back/commit/push as not completed rather than implying the branch is ready.

When the source layer is a runtime-only skill tree, report provenance explicitly: active release, runtime skill path, no source commit/push, changed files, and read-back hashes after edits.
