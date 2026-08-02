from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flights_cli.data.config_loader import load_yaml_mapping
from flights_cli.errors import CliError


class ConfigLoaderTests(unittest.TestCase):
    def write_file(self, text: str) -> Path:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = Path(tmp_dir.name) / "config.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_loads_mapping_and_treats_configured_empty_file_as_missing(self) -> None:
        path = self.write_file("schema_version: example.v1\nvalue: 2\n")
        empty = self.write_file("")

        self.assertEqual(
            load_yaml_mapping(path, source_name="example"),
            {"schema_version": "example.v1", "value": 2},
        )
        self.assertIsNone(
            load_yaml_mapping(
                empty,
                source_name="example",
                empty_is_missing=True,
            )
        )

    def test_missing_and_invalid_sources_use_one_configuration_error_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.yaml"
            self.assertIsNone(load_yaml_mapping(missing, source_name="example"))
            with self.assertRaises(CliError) as missing_error:
                load_yaml_mapping(missing, source_name="example", strict=True)

        invalid = self.write_file("broken line\n")
        with self.assertRaises(CliError) as invalid_error:
            load_yaml_mapping(invalid, source_name="example")

        self.assertEqual(missing_error.exception.error_type, "configuration_error")
        self.assertIn("example file not found", missing_error.exception.message)
        self.assertEqual(invalid_error.exception.error_type, "configuration_error")
        self.assertIn("invalid example YAML", invalid_error.exception.message)


if __name__ == "__main__":
    unittest.main()
