from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class YamlSubsetError(ValueError):
    path: Path
    line_no: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line_no}: {self.reason}"


@dataclass(frozen=True, slots=True)
class _Line:
    number: int
    indent: int
    text: str


def parse_yaml_subset(text: str, path: Path) -> dict[str, Any]:
    """Parse the small mapping/list/scalar YAML subset used by flight data files."""

    lines = _logical_lines(text, path)
    if not lines:
        return {}
    if lines[0].indent != 0:
        raise YamlSubsetError(
            path, lines[0].number, "top-level keys must not be indented"
        )
    value, next_index = _parse_block(lines, 0, 0, path)
    if next_index != len(lines):
        line = lines[next_index]
        raise YamlSubsetError(
            path, line.number, f"unsupported indentation level {line.indent}"
        )
    if not isinstance(value, dict):
        raise YamlSubsetError(
            path, lines[0].number, "top-level value must be a mapping"
        )
    return value


def _logical_lines(text: str, path: Path) -> list[_Line]:
    result: list[_Line] = []
    for line_no, raw_line in enumerate(text.splitlines(), 1):
        leading = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        if "\t" in leading:
            raise YamlSubsetError(path, line_no, "tabs are not supported")
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        result.append(
            _Line(
                number=line_no,
                indent=len(raw_line) - len(raw_line.lstrip(" ")),
                text=stripped,
            )
        )
    return result


def _parse_block(
    lines: list[_Line], index: int, indent: int, path: Path
) -> tuple[dict[str, Any] | list[Any], int]:
    if lines[index].indent != indent:
        raise YamlSubsetError(
            path,
            lines[index].number,
            f"unsupported indentation level {lines[index].indent}",
        )
    if lines[index].text.startswith("- "):
        return _parse_list(lines, index, indent, path)
    return _parse_mapping(lines, index, indent, path)


def _parse_mapping(
    lines: list[_Line], index: int, indent: int, path: Path
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise YamlSubsetError(
                path, line.number, f"unsupported indentation level {line.indent}"
            )
        if line.text.startswith("- "):
            break
        key, raw_value = _key_value(line.text, path, line.number)
        if raw_value:
            result[key] = _scalar_or_inline_list(raw_value, path, line.number)
            index += 1
            continue
        index += 1
        if index >= len(lines) or lines[index].indent <= indent:
            result[key] = {}
            continue
        child_indent = lines[index].indent
        child, index = _parse_block(lines, index, child_indent, path)
        result[key] = child
    return result, index


def _parse_list(
    lines: list[_Line], index: int, indent: int, path: Path
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise YamlSubsetError(
                path, line.number, f"unsupported indentation level {line.indent}"
            )
        if not line.text.startswith("- "):
            break
        item_text = line.text[2:].strip()
        if not item_text:
            raise YamlSubsetError(path, line.number, "list item value is required")
        if ":" not in item_text:
            if index + 1 < len(lines) and lines[index + 1].indent > indent:
                raise YamlSubsetError(path, line.number, "expected key: value")
            result.append(_scalar_or_inline_list(item_text, path, line.number))
            index += 1
            continue

        key, raw_value = _key_value(item_text, path, line.number)
        item: dict[str, Any] = {
            key: _scalar_or_inline_list(raw_value, path, line.number)
            if raw_value
            else {}
        }
        index += 1
        if index < len(lines) and lines[index].indent > indent:
            child_indent = lines[index].indent
            child, index = _parse_mapping(lines, index, child_indent, path)
            item.update(child)
        result.append(item)
    return result, index


def _key_value(text: str, path: Path, line_no: int) -> tuple[str, str]:
    if ":" not in text:
        raise YamlSubsetError(path, line_no, "expected key: value")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        raise YamlSubsetError(path, line_no, "key is required")
    return key, value.strip()


def _scalar_or_inline_list(value: str, path: Path, line_no: int) -> Any:
    text = value.strip()
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlSubsetError(path, line_no, "unterminated inline list")
        body = text[1:-1].strip()
        if not body:
            return []
        return [
            _scalar(part.strip(), path, line_no)
            for part in body.split(",")
            if part.strip()
        ]
    return _scalar(text, path, line_no)


def _scalar(value: str, path: Path, line_no: int) -> Any:
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise YamlSubsetError(path, line_no, "unterminated quoted string")
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


__all__ = ["YamlSubsetError", "parse_yaml_subset"]
