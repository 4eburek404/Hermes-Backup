from pathlib import Path


TRAVEL_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = (
    "flight-calendar-ics",
    "flight-search",
    "flight-status",
    "travel-expense-spreadsheet-summary",
    "travel-news-digest",
)
INTERPRETER = '"${HERMES_SKILLS_PYTHON:-python3}"'


def test_all_travel_skills_use_portable_python_interpreter() -> None:
    skill_files = sorted(TRAVEL_ROOT.glob("*/SKILL.md"))
    assert tuple(path.parent.name for path in skill_files) == EXPECTED_SKILLS

    missing = [
        path.parent.name
        for path in skill_files
        if INTERPRETER not in path.read_text(encoding="utf-8")
    ]
    assert missing == []
