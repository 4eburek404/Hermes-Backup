# stdlib unittest fallback when pytest is absent

Use this when a project has no pytest dependency and the user did not ask to add dependencies.

## Pattern

1. Write tests with stdlib `unittest`:

```python
import unittest

class FeatureTests(unittest.TestCase):
    def test_behavior(self):
        self.assertEqual(actual(), expected)

if __name__ == "__main__":
    unittest.main()
```

2. Verify RED with the module path, not file path:

```bash
.venv/bin/python -m unittest tests.test_feature -q
```

3. Implement minimal production code.

4. Verify GREEN and run documented syntax/project gates.

## Importing single-file apps safely

For Flask/single-file scripts without a package, import by path so tests do not require packaging changes:

```python
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "vps_dashboard" / "server_monitor.py"

spec = importlib.util.spec_from_file_location("server_monitor_under_test", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
```

## Pitfall

Do not keep trying `pytest` after `No module named pytest`. Either use the project runner or switch to `unittest`; adding pytest is a dependency decision, not a default test step.
