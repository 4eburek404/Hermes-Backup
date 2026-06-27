"""Passenger display normalization for calendar summaries."""
from __future__ import annotations

import re


_MULTIGRAPH_MAP: tuple[tuple[str, str], ...] = (
    ("SHCH", "щ"),
    ("SCH", "щ"),
    ("YO", "ё"),
    ("ZH", "ж"),
    ("KH", "х"),
    ("TS", "ц"),
    ("CH", "ч"),
    ("SH", "ш"),
    ("YU", "ю"),
    ("YA", "я"),
    ("YE", "е"),
)

_LETTER_MAP = {
    "A": "а",
    "B": "б",
    "C": "к",
    "D": "д",
    "E": "е",
    "F": "ф",
    "G": "г",
    "H": "х",
    "I": "и",
    "J": "дж",
    "K": "к",
    "L": "л",
    "M": "м",
    "N": "н",
    "O": "о",
    "P": "п",
    "Q": "к",
    "R": "р",
    "S": "с",
    "T": "т",
    "U": "у",
    "V": "в",
    "W": "в",
    "X": "кс",
    "Y": "и",
    "Z": "з",
}


def _transliterate_word(word: str) -> str:
    if not re.search(r"[A-Za-z]", word):
        return word[:1].upper() + word[1:].lower() if word else word
    source = word.upper()
    out: list[str] = []
    index = 0
    while index < len(source):
        for latin, cyrillic in _MULTIGRAPH_MAP:
            if source.startswith(latin, index):
                out.append(cyrillic)
                index += len(latin)
                break
        else:
            char = source[index]
            out.append(_LETTER_MAP.get(char, char.lower()))
            index += 1
    text = "".join(out)
    return text[:1].upper() + text[1:]


def display_passenger_name(value: str) -> str:
    """Return a readable Russian-script passenger label for SUMMARY."""
    text = str(value or "").strip()
    if not text:
        return ""
    parts = re.split(r"([ '\-]+)", text)
    return "".join(_transliterate_word(part) if re.search(r"\w", part) else part for part in parts).strip()
