from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from flights_cli.data.config_loader import load_yaml_mapping
from flights_cli.domain.gateway_priors import DEFAULT_GATEWAY_PRIORS_PATH
from flights_cli.domain.route_access_profiles import (
    DEFAULT_ROUTE_ACCESS_PROFILES_PATH,
)
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
        whitespace = self.write_file(" \n\t\n")

        self.assertEqual(
            load_yaml_mapping(path, source_name="example"),
            {"schema_version": "example.v1", "value": 2},
        )
        self.assertEqual(load_yaml_mapping(empty, source_name="example"), {})
        self.assertIsNone(
            load_yaml_mapping(
                empty,
                source_name="example",
                empty_is_missing=True,
            )
        )
        self.assertIsNone(
            load_yaml_mapping(
                whitespace,
                source_name="example",
                empty_is_missing=True,
            )
        )

    def test_comment_only_yaml_loads_as_empty_mapping(self) -> None:
        path = self.write_file("# comment\n  # indented comment\n")

        self.assertEqual(
            load_yaml_mapping(
                path,
                source_name="example",
                empty_is_missing=True,
            ),
            {},
        )

    def test_rejects_non_mapping_top_level_values(self) -> None:
        for text in ("null\n", "value\n", "- value\n"):
            with self.subTest(text=text):
                path = self.write_file(text)
                with self.assertRaises(CliError) as caught:
                    load_yaml_mapping(path, source_name="example")

                self.assertEqual(caught.exception.error_type, "configuration_error")
                self.assertIn("invalid example YAML", caught.exception.message)
                self.assertIn(str(path), caught.exception.message)
                self.assertIn(
                    "top-level value must be a mapping",
                    caught.exception.message,
                )

    def test_packaged_yaml_resources_preserve_expected_data(self) -> None:
        resources = {
            DEFAULT_GATEWAY_PRIORS_PATH: (
                "gateway priors",
                "91e919b07008d095c9f197ecd4ecfb22588e1997a6a06aa3f763d80176c82ded",
            ),
            DEFAULT_ROUTE_ACCESS_PROFILES_PATH: (
                "route access profiles",
                "89940ef6ae79f04592443ecbe39408ac93fa93ea20fff6edeb9d8c38f75c26cc",
            ),
        }

        loaded_resources: dict[Path, dict[str, Any]] = {}
        for path, (source_name, expected_hash) in resources.items():
            with self.subTest(path=path):
                loaded = load_yaml_mapping(path, source_name=source_name, strict=True)
                self.assertIsNotNone(loaded)
                assert loaded is not None
                loaded_resources[path] = loaded
                canonical_json = json.dumps(
                    loaded,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.assertEqual(
                    hashlib.sha256(canonical_json).hexdigest(),
                    expected_hash,
                )

        route_access = loaded_resources[DEFAULT_ROUTE_ACCESS_PROFILES_PATH]
        norway = route_access["region_groups"]["eea"][-1]
        self.assertEqual(norway, "NO")
        self.assertIsInstance(norway, str)

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
        self.assertIn(str(invalid), invalid_error.exception.message)


if __name__ == "__main__":
    unittest.main()
