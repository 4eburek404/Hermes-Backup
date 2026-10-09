from __future__ import annotations

from pathlib import Path
from typing import Any

from .skill_source import materialize_skill_source


class SkillSourceContractSubject:
    def materialize(
        self,
        repo_root: Path,
        skill_path: Path,
        source: dict[str, Any],
        destination: Path,
    ) -> dict[str, Any]:
        return materialize_skill_source(
            repo_root,
            skill_path,
            source,
            destination,
        )
