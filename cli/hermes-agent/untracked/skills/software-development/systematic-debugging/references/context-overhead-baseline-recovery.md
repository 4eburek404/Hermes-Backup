# Context-overhead baseline recovery

Use this when a read-only analyzer already compiles, but the associated test baseline is stale or shrank after fixture changes.

## Signals

- `py_compile` passes for the analyzer, but `pytest tests/test_analyze_context_overhead.py -q` collects fewer tests than expected.
- The analyzer reports the right sections/keys in JSON, but the test file only covers a subset.
- Backup files exist next to the analyzer, but the tests are the missing piece.

## Recovery sequence

1. Snapshot the worktree:
   - `git status --short --branch --untracked-files=all`
   - `git diff --stat`
   - `git diff --name-only`
2. Inventory fixtures and backups:
   - `find tests/fixtures/context_overhead -maxdepth 1 -type f -print | sort`
   - `find . -maxdepth 4 -type f \( -name '*analyze_context_overhead*' -o -name '*context*baseline*' -o -name '*.backup*' \) -print | sort`
3. Inspect the current analyzer JSON shape with a minimal fixture run.
4. Rebuild *tests only* to match the analyzer's current scope.
   - Cover: sessions index, missing index, system_prompt, tools, messages, snapshot sizing vs provider input, and one CLI subprocess regression.
5. Gate on collected count before trusting the suite:
   - `pytest tests/test_analyze_context_overhead.py -q --collect-only`
   - expect at least 7 tests for the restored baseline used in this repo.
6. Run the analyzer via subprocess on the fixture directory and verify both outputs exist.

## What to verify in JSON

- `system_prompt`
- `system_prompt_sections`
- `tools_schema`
- `message_roles`
- `snapshot_sizing`
- `estimated_provider_input`
- `storage_only_fields`
- `provider_bound_assumptions`

## Pitfalls

- Don't patch the analyzer to satisfy missing tests unless the analyzer is actually broken.
- Don't trust `git diff -- tests/test_analyze_context_overhead.py` if the file was rewritten in place; inspect the collected test count instead.
- If a sanitizer test accidentally absorbs the subprocess regression body, collect-only may still pass with fewer tests. Restore the missing `def test_snapshot_sizing_provider_input_and_cli_subprocess_regression(...):` header as a separate test and require the expected collected count before trusting pytest.
- If fixtures already encode the current analyzer scope, the correct fix is usually to expand the test file, not the runtime.
- For standard chat-completions provider-input updates, assert both the nested JSON shape (`estimated_provider_input.standard_chat_completions`) and markdown headings (`Standard chat-completions filtering`, `Excluded storage-only fields`, `Uncertain fields`).
- Keep fixture token expectations grounded in a fresh CLI fixture JSON run; avoid inventing algebra over snapshot/provider deltas when the analyzer uses separate estimators for snapshot sizing and sanitized provider payloads.
- Keep the CLI regression subprocess-based; it catches packaging/entrypoint regressions that direct module import tests miss.
