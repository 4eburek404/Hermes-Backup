from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "evals/development-workflow/consumer.py"
sys.path.insert(0, str(ROOT))


def consumer_module():
    spec = importlib.util.spec_from_file_location("bdd_pytest_evidence", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def consumer():
    return consumer_module().DevelopmentWorkflowConsumer(ROOT, ROOT, {})


def cfg():
    return {
        "fixture_files": {
            "app.py": "def main(): pass\n",
            "tests/test_app.py": "def test_regular():\n    result = run_app('Alice')\n    assert result.returncode == 0\n    assert result.stdout == 'Hello, Alice!'\n",
        },
        "behavior_probes": [
            {"command": ["python3", "app.py", "Alice"], "stdout": "Hello, Alice!\n", "exit_code": 0},
            {"command": ["python3", "app.py"], "stdout": "Hello, World!\n", "exit_code": 0},
            {"command": ["python3", "app.py", "Alice", "--shout"], "stdout": "HELLO, ALICE!\n", "exit_code": 0},
        ],
        "current_behavior_probes": [
            {"stdout": "Hello, Alice!\n", "exit_code": 0, "input_signals": ["Alice"]},
            {"stdout": "Hello, World!\n", "exit_code": 0, "input_signals": []},
        ],
        "preserved_behavior_probes": [
            {"stdout": "Hello, Alice!\n", "exit_code": 0, "input_signals": ["Alice"]},
            {"stdout": "Hello, World!\n", "exit_code": 0, "input_signals": []},
        ],
        "target_check_signals": ["HELLO, ALICE!", "--shout"],
    }


def tool(name, args, result):
    return [
        {"type": "tool_use", "name": name, "input": args},
        {"type": "tool_result", "name": name, "output": json.dumps(result)},
    ]


def fixture(tmp_path):
    config = cfg()
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "app.py").write_text(config["fixture_files"]["app.py"])
    (root / "tests").mkdir()
    (root / "tests/test_app.py").write_text(config["fixture_files"]["tests/test_app.py"])
    return config, root


def add_tests(root, names=("shout", "default")):
    functions = {
        "shout": "def test_shout():\n    result = run_app('Alice', '--shout')\n    assert result.returncode == 0\n    assert result.stdout == 'HELLO, ALICE!'\n",
        "default": "def test_default():\n    result = run_app()\n    assert result.returncode == 0\n    assert result.stdout == 'Hello, World!'\n",
    }
    additions = "".join("+" + line for name in names for line in functions[name].splitlines(keepends=True))
    path = root / "tests/test_app.py"
    patch = f"*** Begin Patch\n*** Update File: {path}\n@@\n{additions}*** End Patch"
    return path, patch


def test_v4a_context_patch_replays_snapshot_only_on_unique_match(tmp_path):
    config, root = fixture(tmp_path)
    module = consumer_module()
    test_path = root / "tests/test_app.py"
    original = test_path.read_text()
    patch = f"""*** Begin Patch
*** Update File: {test_path}
@@
 def test_regular():
     result = run_app('Alice')
     assert result.returncode == 0
     assert result.stdout == 'Hello, Alice!'
+
+def test_default():
+    result = run_app()
+    assert result.returncode == 0
+    assert result.stdout == 'Hello, World!'
*** End Patch"""
    blocks = module._test_patch_blocks(patch)
    assert len(blocks) == 1
    path, hunk = blocks[0]
    assert path == str(test_path)
    replayed = module._apply_test_patch(original, hunk)
    assert replayed is not None and "def test_default" in replayed
    assert original == test_path.read_text()
    assert module._apply_test_patch("different source", hunk) is None


def test_reconstructs_test_snapshot_and_red_green_without_splitting_stdout(tmp_path):
    config, root = fixture(tmp_path)
    path, patch = add_tests(root)
    events = tool("patch", {"mode": "patch", "patch": patch}, {"success": True, "files_modified": [str(path)]})
    events += tool("terminal", {"command": "python3 -m pytest -q"}, {
        "output": "FAILED tests/test_app.py::test_shout - AssertionError\n1 failed, 2 passed\n", "exit_code": 1
    })
    prod = root / "app.py"
    events += tool("patch", {"mode": "patch", "patch": f"*** Begin Patch\n*** Update File: {prod}\n@@\n-def main(): pass\n+def main(): print('changed')\n*** End Patch"}, {"success": True, "files_modified": [str(prod)]})
    events += tool("terminal", {"command": "python3 -m pytest -q && python3 app.py"}, {"output": "3 passed\nHello, World!\n", "exit_code": 0})
    facts = consumer().event_summary(events, config, root)["workflow_events"]
    assert not any(f.get("kind", "").endswith("test_result") for f in facts), facts
    assert any(f.get("kind") == "test_evidence_unconfirmed" for f in facts), facts


def test_late_test_never_backdates_and_selected_or_skipped_tests_are_unconfirmed(tmp_path):
    config, root = fixture(tmp_path)
    prod = root / "app.py"
    events = tool("patch", {"mode": "patch", "patch": f"*** Begin Patch\n*** Update File: {prod}\n@@\n-def main(): pass\n+def main(): print('changed')\n*** End Patch"}, {"success": True, "files_modified": [str(prod)]})
    path, patch = add_tests(root, ("shout",))
    events += tool("patch", {"mode": "patch", "patch": patch}, {"success": True, "files_modified": [str(path)]})
    events += tool("terminal", {"command": "python3 -m pytest -q"}, {"output": "2 passed\n", "exit_code": 0})
    facts = consumer().event_summary(events, config, root)["workflow_events"]
    prod_index = next(f["index"] for f in facts if f["kind"] == "production_changed")
    late = [f for f in facts if f.get("kind") == "current_behavior_test_result"]
    assert not late
    assert any(f.get("kind") == "test_evidence_unconfirmed" for f in facts), facts
    for command, output in (("python3 -m pytest -q -k shout", "1 passed\n"),
                            ("python3 -m pytest -q", "1 passed, 1 skipped\n"),
                            ("echo '1 passed'", "1 passed\n")):
        unconfirmed = consumer().event_summary(
            tool("terminal", {"command": command}, {"output": output, "exit_code": 0}), config, root
        )["workflow_events"]
        assert not any(f.get("kind", "").endswith("test_result") for f in unconfirmed)


def test_aggregate_program_output_is_not_attributed_by_expected_strings(tmp_path):
    config, root = fixture(tmp_path)
    command = "python3 app.py Alice --shout && python3 app.py Alice && python3 app.py"
    output = "HELLO, ALICE!\nHello, Alice!\nHello, World!\n"
    facts = consumer().event_summary(
        tool("terminal", {"command": command}, {"output": output, "exit_code": 0}), config, root
    )["workflow_events"]
    assert not any(f.get("kind") in {"current_behavior_observed", "preserved_behavior_observed"} for f in facts)
    assert not any(f.get("kind", "").endswith("test_result") for f in facts)


def _run_pytest(root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=root,
        text=True, capture_output=True, check=False,
    )
    return {"output": result.stdout + result.stderr, "exit_code": result.returncode}


def _executable_fixture(root: Path, helper: str) -> tuple[dict, Path]:
    config = cfg()
    (root / "tests").mkdir(parents=True)
    (root / "app.py").write_text(
        "import sys\n"
        "def main(argv):\n"
        "    name = argv[0] if argv else 'World'\n"
        "    shout = '--shout' in argv\n"
        "    if shout: name = name.upper()\n"
        "    print(('HELLO, ' if shout else 'Hello, ') + name + '!')\n"
        "if __name__ == '__main__': main(sys.argv[1:])\n",
        encoding="utf-8",
    )
    test_path = root / "tests/test_app.py"
    test_path.write_text(
        "import subprocess\nimport sys\n\n" + helper + "\n\n"
        "def test_regular():\n"
        "    result = run_app('Alice')\n"
        "    assert result.returncode == 0\n"
        "    assert result.stdout == 'Hello, Alice!\\n'\n\n"
        "def test_default():\n"
        "    result = run_app()\n"
        "    assert result.returncode == 0\n"
        "    assert result.stdout == 'Hello, World!\\n'\n\n"
        "def test_shout():\n"
        "    result = run_app('Alice', '--shout')\n"
        "    assert result.returncode == 0\n"
        "    assert result.stdout == 'HELLO, ALICE!\\n'\n",
        encoding="utf-8",
    )
    config["fixture_files"] = {
        "app.py": (root / "app.py").read_text(encoding="utf-8"),
        "tests/test_app.py": test_path.read_text(encoding="utf-8"),
    }
    return config, test_path


def test_successful_write_file_replaces_pytest_snapshot_without_stale_evidence(tmp_path):
    config, test_path = _executable_fixture(
        tmp_path,
        "def run_app(*args):\n"
        "    return subprocess.run([sys.executable, 'app.py', *args], "
        "text=True, capture_output=True, check=False)",
    )
    before = _run_pytest(tmp_path)
    assert before["exit_code"] == 0
    assert "3 passed" in before["output"]

    replacement = "def test_placeholder():\n    assert True\n"
    write_events = tool("write_file", {"path": str(test_path), "content": replacement},
                        {"success": True, "path": str(test_path)})
    test_path.write_text(replacement, encoding="utf-8")
    after = _run_pytest(tmp_path)
    assert after["exit_code"] == 0
    assert "1 passed" in after["output"]
    events = write_events + tool("terminal", {"command": "python3 -m pytest -q"}, after)

    facts = consumer().event_summary(events, config, tmp_path)["workflow_events"]

    assert not any(f.get("kind", "").endswith("test_result") for f in facts), facts
    assert any(f.get("kind") == "test_evidence_unconfirmed" for f in facts), facts


def test_edit_file_invalidates_old_test_snapshot_even_if_pytest_passes(tmp_path):
    config, test_path = _executable_fixture(
        tmp_path,
        "def run_app(*args):\n"
        "    return subprocess.run([sys.executable, 'app.py', *args], "
        "text=True, capture_output=True, check=False)",
    )
    original = test_path.read_text(encoding="utf-8")
    replacement = "def test_placeholder():\n    assert True\n"
    edit = tool("edit_file", {"path": str(test_path), "old_string": original,
                              "new_string": replacement}, {"success": True})
    test_path.write_text(replacement, encoding="utf-8")
    actual = _run_pytest(tmp_path)
    assert actual["exit_code"] == 0
    assert "1 passed" in actual["output"]
    edit += tool("terminal", {"command": "python3 -m pytest -q"}, actual)

    facts = consumer().event_summary(edit, config, tmp_path)["workflow_events"]

    assert not any(f.get("kind", "").endswith("test_result") for f in facts), facts
    assert any(f.get("kind") == "test_evidence_unconfirmed" for f in facts), facts


def test_run_app_that_returns_prepared_result_does_not_confirm_application(tmp_path):
    stub_values = repr({
        (): "Hello, World!\n",
        ("Alice",): "Hello, Alice!\n",
        ("Alice", "--shout"): "HELLO, ALICE!\n",
    })
    config, _ = _executable_fixture(
        tmp_path,
        "from types import SimpleNamespace\n"
        "def run_app(*args):\n"
        "    return SimpleNamespace(returncode=0, stdout=" + stub_values + "[args])",
    )
    actual = _run_pytest(tmp_path)
    assert actual["exit_code"] == 0
    assert "3 passed" in actual["output"]
    events = tool("terminal", {"command": "python3 -m pytest -q"}, actual)

    facts = consumer().event_summary(events, config, tmp_path)["workflow_events"]

    assert not any(f.get("kind", "").endswith("test_result") for f in facts), facts
    assert any(f.get("kind") == "test_evidence_unconfirmed" for f in facts), facts


def test_real_run_app_fixture_confirms_only_matching_probe(tmp_path):
    config, _ = _executable_fixture(
        tmp_path,
        "def run_app(*args):\n"
        "    return subprocess.run([sys.executable, 'app.py', *args], "
        "text=True, capture_output=True, check=False)",
    )
    run_result = _run_pytest(tmp_path)
    assert run_result["exit_code"] == 0, run_result
    assert "3 passed" in run_result["output"], run_result
    events = tool("terminal", {"command": "python3 -m pytest -q"}, run_result)

    facts = consumer().event_summary(events, config, tmp_path)["workflow_events"]

    confirmed = [f for f in facts if f.get("kind", "").endswith("test_result")]
    assert {f["probe_index"] for f in confirmed if f["result"] == "passed"} == {0, 1, 2}, facts
    assert all(f["result"] == "passed" for f in confirmed)
