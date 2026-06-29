from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def read_rows(path: Path, *, sheet: str | int | None = None) -> list[list[Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path)
    if suffix in {".xls", ".xlsx", ".xlsm"}:
        return _read_excel(path, sheet=sheet)
    raise ValueError(f"Неподдерживаемый формат файла: {path.suffix}")


def _read_csv(path: Path) -> list[list[Any]]:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [list(row) for row in csv.reader(fh, dialect=dialect)]


def _read_excel(path: Path, *, sheet: str | int | None = None) -> list[list[Any]]:
    try:
        import pandas as pd  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Для чтения Excel нужен pandas + openpyxl/xlrd. "
            "Установите в рабочем окружении Hermes: python -m pip install pandas openpyxl xlrd"
        ) from exc

    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    sheet_name: str | int = 0 if sheet is None else sheet
    dataframe = pd.read_excel(path, sheet_name=sheet_name, header=None, engine=engine)
    dataframe = dataframe.where(dataframe.notna(), None)
    return dataframe.values.tolist()
