from __future__ import annotations

from .constants import CANON_AMOUNT, CANON_CARRIER, CANON_DATE, CANON_DETAILS
from .fingerprint import row_fingerprint
from .models import NormalizedRow, TableSchema
from .money import parse_amount
from .schema import get_cell
from .text import text_value


def normalize_row(row: list[object], *, source_row: int, schema: TableSchema) -> NormalizedRow:
    date = get_cell(row, schema, CANON_DATE)
    carrier = get_cell(row, schema, CANON_CARRIER)
    details = get_cell(row, schema, CANON_DETAILS)
    amount_cell = get_cell(row, schema, CANON_AMOUNT)
    amount = parse_amount(amount_cell)
    fingerprint = row_fingerprint(date, carrier, details, amount_cell)
    return NormalizedRow(
        source_row=source_row,
        fingerprint=fingerprint,
        date=text_value(date),
        carrier=text_value(carrier),
        details=text_value(details),
        amount_cell=amount_cell,
        amount=amount,
        raw_values=list(row),
    )
