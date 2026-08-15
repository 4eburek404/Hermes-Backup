# flight-search testing principles

Tests should protect current behavior, not the history of deleted behavior.

## Contract tests

- Assert the active public contract by version, required top-level sections, schema
  validation, and structured fields.
- Do not keep deny-list tests for deleted fields, deleted commands, deleted files, or
  removed compatibility adapters.
- Unknown-field handling belongs to JSON Schema `additionalProperties`, not to
  hand-maintained lists of historical field names.

## Answer tests

- Prefer catalog items, prices, route fields, evidence status, caveat booleans, and
  validation errors over exact rendered prose.
- Assert exact `rendered_text` only when the renderer grammar itself is the behavior
  under test. In those tests, keep the assertion local to the renderer contract.
- Do not test that old wording, old debug labels, or old report fragments are absent
  from final text.

## Test architecture

- Shared report factories live in `tests/fixtures`, not in another `test_*.py` file.
- Test modules may import production code and fixture helpers; they should not import
  other test modules.
- Architecture tests should inspect structured code facts such as imports, schemas, or
  parser registrations. Avoid raw source-text scans for old names.
- Live provider checks stay opt-in via `@pytest.mark.live_provider` and
  `--run-live-providers`.

## Refactor rule

When a migration deletes a public surface, remove tests for that old surface in the
same change. Add only positive tests for the new public surface and current runtime
behavior.
