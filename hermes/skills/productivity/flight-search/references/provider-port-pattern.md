# Provider Port Pattern for Flight Search CLI

Use this when refactoring or extending provider execution in `flights_cli`.

## Durable lesson

Do not let execution-layer modules call provider-specific functions directly. `execution/` should assemble a probe query and call a concrete `FlightProviderPort`; provider-specific fetch/cache/normalization/summary logic belongs in `adapters/providers/*_adapter.py`.

## Target shape

- `ports/providers.py`
  - owns `FlightProviderPort`, `ProviderCapabilities`, `ProviderProbeResult`, provider/probe/evidence/cache literals.
- `adapters/providers/registry.py`
  - registry returns concrete provider adapters, not bare descriptors.
  - keep lightweight descriptor/capability access only as backward-compatible projection if older planning code still needs it.
- `adapters/providers/<provider>_adapter.py`
  - implements `search_segment(query) -> ProviderProbeResult`.
  - implements `search_aggregate(query) -> ProviderProbeResult` or returns structured `not_supported`.
  - owns provider-specific cached search calls, normalization, post-validation, summaries, and cache-status projection.
- `execution/probe_dispatcher.py`
  - loops over `provider_adapters_for_segment(...)` and translates `ProviderProbeResult` into existing probe ledger/outcome types.
- `execution/aggregate_control_runner.py`
  - calls `provider_adapter(...).search_aggregate(...)`; it must not contain Kupibilet-only algorithm branches.

## Migration checklist

1. RED: add/keep tests that fail if `execution/` calls provider functions directly.
2. RED: assert registry values are concrete `FlightProviderPort` objects and `provider_adapter(...)`/`provider_adapters_for_segment(...)` exist.
3. Move provider-specific calls from dispatcher/aggregate runner into adapter modules.
4. Keep old public behavior through projections, not duplicate algorithms.
5. Update tests to patch the new adapter-level seam:
   - `flights_cli.adapters.providers.registry.providers_for_segment` for provider selection.
   - `flights_cli.adapters.providers.<provider>_adapter.cached_*_search` for provider fetch stubs.
   - provider adapter summary/converter functions in the adapter module, not in `execution.probe_dispatcher`.
6. Run focused provider tests before full route tests.

## Pitfalls observed

- After moving direct calls out of `probe_dispatcher.py`, old tests that patch `flights_cli.execution.probe_dispatcher.cached_*` or `providers_for_segment` become invalid. Update the tests to patch adapter seams; do not re-export old symbols just to keep tests green.
- Avoid a registry that stores only capabilities/descriptors while separate code constructs adapters elsewhere. That recreates split ownership.
- If a provider cannot support aggregate probes, return a `ProviderProbeResult(execution_state="not_supported", evidence_type="not_supported")` so reports can explain the source boundary instead of silently skipping it.
- Preserve dedupe and fail-fast semantics in the dispatcher adapter bridge; these are execution semantics, not provider-specific behavior.
