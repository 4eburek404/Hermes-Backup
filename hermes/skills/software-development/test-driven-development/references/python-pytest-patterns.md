# Python Pytest Patterns

Open this file only when the test design is non-trivial. The normal path stays in `SKILL.md`: write one focused pytest test, confirm RED, implement GREEN, refactor, verify, commit.

## Test Shape
Use Arrange / Act / Assert when it keeps the test clear:

```python
def test_parses_valid_airport_code():
    parser = AirportParser()

    result = parser.parse("SVX")

    assert result.code == "SVX"
```

Prefer one behavior per test. If the name needs "and", split the test unless the behaviors are inseparable.

## Parametrized Edge Cases
Use parametrization for related inputs with the same expected behavior:

```python
import pytest

@pytest.mark.parametrize("raw", [" svx ", "SVX", "svx"])
def test_normalizes_airport_code(raw):
    assert normalize_airport_code(raw) == "SVX"
```

Do not hide unrelated scenarios inside one parametrized test.

## Exceptions and Error Messages
Use `pytest.raises` for expected failures:

```python
import pytest

def test_rejects_unknown_airport_code():
    with pytest.raises(ValueError, match="unknown airport"):
        normalize_airport_code("XXX")
```

Assert the meaningful part of the error, not the entire string unless the full text is a stable contract.

## Filesystem
Use `tmp_path` for file tests:

```python
def test_writes_json_result(tmp_path):
    output = tmp_path / "result.json"

    write_result(output, {"ok": True})

    assert output.read_text(encoding="utf-8") == '{"ok": true}\n'
```

Do not write tests that mutate the real repository, home directory, or global configuration.

## CLI Boundaries
For CLI behavior, prefer the project’s existing CLI test style. Common options:
- call a `main(argv)` function directly if the project exposes one;
- use `subprocess.run` for end-to-end command behavior;
- assert exit code, stdout/stderr contract, and generated files.

Keep CLI tests deterministic. Avoid real network, real credentials, and user-specific paths.

## stdout and stderr
Use `capsys` when testing direct Python calls that print:

```python
def test_prints_success_message(capsys):
    main(["--summary"])

    captured = capsys.readouterr()
    assert "ok" in captured.out
    assert captured.err == ""
```

## Time, Environment, and External Boundaries
Use `monkeypatch` or dependency injection for unstable boundaries:
- current time;
- environment variables;
- network clients;
- filesystem roots;
- subprocess calls;
- database/API/LLM clients.

Example:

```python
def test_uses_configured_timeout(monkeypatch):
    monkeypatch.setenv("APP_TIMEOUT", "5")

    assert load_timeout() == 5
```

## Mocks
Mocks are acceptable at external boundaries. They are risky inside domain logic.

Good uses:
- network request client;
- payment, booking, or LLM API client;
- filesystem gateway;
- clock;
- subprocess wrapper.

Bad uses:
- mocking the function under test;
- mocking internal domain methods just to assert they were called;
- testing call order when the user-visible behavior is enough.

Prefer fakes or small in-memory implementations when they make behavior clearer.

## Fixtures
Use fixtures for repeated setup, not for hiding the whole test:

```python
import pytest

@pytest.fixture
def sample_ticket():
    return {"flight_number": "SU1401", "from": "SVX", "to": "SVO"}

def test_reads_flight_number(sample_ticket):
    assert parse_ticket(sample_ticket).flight_number == "SU1401"
```

Avoid fixture chains that make the test unreadable.

## Safety Invariants
Test the invariant directly. Do not rely on brittle "string not present anywhere" checks.

Weak:
```python
assert "config.yaml" not in source
```

Better:
```python
body = extract_function_body(source, "load_runtime_state")
assert "config.yaml" in body
assert ".write(" not in body
assert "write_text" not in body
assert "UPDATE " not in body
assert "DELETE " not in body
```

Prefer function-scoped checks and mutation deny-lists when protecting read-only behavior.

## Flaky Test Avoidance
Do not use real sleeps, real clocks, random ordering, real external services, or local machine assumptions. Inject the boundary or use deterministic test data.
