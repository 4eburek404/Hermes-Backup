#!/usr/bin/env python3
"""SKILL.md delivery stdout contract checks."""
from __future__ import annotations

import unittest

from helpers import ROOT


class SkillDeliveryStdoutContractTests(unittest.TestCase):
    def test_skill_mentions_delivery_stdout_contract_terms(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        for needle in (
            "Stdout is the runtime delivery trigger",
            "Leave it exactly as the CLI prints it",
            "Never redirect",
            "capture",
            "pipe",
            "tee",
            "summarize",
            "`echo ok=...`",
            "After a successful build, run no more commands",
            "surfaced safe summary",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_skill_mentions_dependency_interpreter_contract(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        for needle in (
            "same Python interpreter used for the CLI",
            "python -m pip install icalendar jsonschema curl_cffi",
            "Use `python -m pip`, not bare `pip`",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
