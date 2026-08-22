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
- Shared cross-cutting test helpers live in `tests/helpers.py`.
- Test modules may import production code and fixture helpers; they should not import
  other test modules.
- Architecture tests should inspect structured code facts such as imports, schemas, or
  parser registrations. Avoid raw source-text scans for old names.
- Live provider checks stay opt-in via `@pytest.mark.live_provider` and
  `--run-live-providers`.

## Dates and timestamps

- Use `future_departure_date()` from `tests/helpers.py` when a date must pass
  validation against the real current day.
- Compute return dates, date-window bounds, provider query dates, related timestamps,
  and expected output from the same departure value.
- Do not use a far-future literal such as `2099-...` to postpone test expiry.
- Fixed dates are appropriate when the test injects `today` or `now`, exercises
  calendar or timezone arithmetic, or parses a historical provider fixture without
  validating it against the current day.

```python
depart = future_departure_date()
return_date = depart + timedelta(days=7)
departure_at = f"{depart.isoformat()}T08:00:00+05:00"
```

## Refactor rule

When a migration deletes a public surface, remove tests for that old surface in the
same change. Add only positive tests for the new public surface and current runtime
behavior.
