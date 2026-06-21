#!/usr/bin/env python3
"""SKILL.md delivery stdout contract checks."""
from __future__ import annotations

import unittest

from helpers import ROOT


class SkillDeliveryStdoutContractTests(unittest.TestCase):
    def test_skill_mentions_delivery_stdout_contract_terms(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        for needle in (
            "plugin-delivery trigger surface",
            "exactly the JSON emitted",
            "Do not redirect",
            "capture",
            "pipe",
            "tee",
            "summarize",
            'echo "ok=True"',
            "data.agent_handoff.media",
            "safe_summary",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_skill_mentions_dependency_interpreter_contract(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        for needle in (
            "same Python interpreter used to run",
            "Do not use bare `pip`",
            "python -m pip install icalendar jsonschema cffi",
            "tool runtime launches skills through its own venv",
            "Do not install into system/Homebrew Python",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
