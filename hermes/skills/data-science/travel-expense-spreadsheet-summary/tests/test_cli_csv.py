from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_csv_smoke(tmp_path: Path):
    csv_path = tmp_path / "report.csv"
    csv_path.write_text(
        "Дата покупки;Поставщик;Описание;Стоимость\n"
        "01.03.2025;Аэрофлот;01.03.2025 Москва-Сочи;10000\n"
        "02.03.2025;РЖД;02.03.2025 Москва-Казань поезд;2000\n"
        "03.03.2025;Яндекс;03.03-04.03.2025 Казань, Амакс Сафар;5000\n"
        ";;ИТОГО:;17000\n",
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "travel_expense_summary.py"
    completed = subprocess.run(
        [sys.executable, str(script), str(csv_path), "--format", "json"],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)
    assert result["verification"]["booking_rows"] == 3
    assert result["verification"]["source_total_sum_matches"] is True
