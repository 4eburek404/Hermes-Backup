from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from flights_cli.errors import CliError
from flights_cli.io import read_json_object
from flights_cli.output import emit_json


class JsonBoundaryTests(unittest.TestCase):
    def test_duplicate_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "request.json"
            path.write_text('{"origin":"SVX","origin":"NTE"}', encoding="utf-8")
            with self.assertRaises(CliError) as ctx:
                read_json_object(str(path))
        self.assertEqual(ctx.exception.error_type, "validation_error")
        self.assertIn("duplicate JSON key", ctx.exception.message)

    def test_non_finite_numbers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "request.json"
            path.write_text('{"timeout":NaN}', encoding="utf-8")
            with self.assertRaises(CliError) as ctx:
                read_json_object(str(path))
        self.assertEqual(ctx.exception.error_type, "validation_error")
        self.assertIn("non-finite JSON number", ctx.exception.message)

    def test_json_output_rejects_non_finite_numbers(self) -> None:
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                emit_json({"value": float("nan")})

    def test_json_output_has_one_terminal_newline(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            emit_json({"ok": True})
        self.assertEqual(json.loads(stdout.getvalue()), {"ok": True})
        self.assertTrue(stdout.getvalue().endswith("\n"))
        self.assertFalse(stdout.getvalue().endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
