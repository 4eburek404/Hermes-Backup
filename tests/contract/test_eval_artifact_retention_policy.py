from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_PREFIX_PARTS = {"runs", "experiments", "reassessments", "audit"}


def test_generated_eval_artifacts_are_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--", "evals"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    offenders = []
    for raw_path in result.stdout.splitlines():
        parts = Path(raw_path).parts
        if len(parts) < 3 or parts[0] != "evals":
            continue
        if any(part in FORBIDDEN_PREFIX_PARTS for part in parts[2:]):
            offenders.append(raw_path)

    assert offenders == [], (
        "generated eval evidence must stay out of the active source tree; "
        "promote only minimal stable regression fixtures:\n"
        + "\n".join(offenders)
    )
