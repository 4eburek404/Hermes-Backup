#!/usr/bin/env python3
"""Patch a Hermes Agent checkout so .ics files deliver as documents.

The script is intentionally narrow and idempotent:
* add .ics to gateway.platforms.base.SUPPORTED_DOCUMENT_TYPES
* add .ics to gateway.platforms.base.MEDIA_DELIVERY_EXTS
* add a focused gateway regression test
* run that test unless --no-test is passed
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path


DOC_ENTRY = '    ".ics": "text/calendar",\n'
MEDIA_DOCUMENT_LINE = (
    '    ".pdf", ".docx", ".doc", ".odt", ".rtf", ".txt", ".md", ".epub",'
)
MEDIA_DOCUMENT_LINE_WITH_ICS = (
    '    ".pdf", ".docx", ".doc", ".odt", ".rtf", ".txt", ".md", ".ics", ".epub",'
)

TEST_RELATIVE_PATH = Path("tests/gateway/test_gateway_ics_delivery_contract.py")
TEST_CONTENT = """\
from gateway.platforms.base import (
    BasePlatformAdapter,
    MEDIA_DELIVERY_EXTS,
    SUPPORTED_DOCUMENT_TYPES,
)


def test_ics_is_supported_document_type():
    assert SUPPORTED_DOCUMENT_TYPES[".ics"] == "text/calendar"


def test_ics_is_in_media_delivery_allowlist():
    assert ".ics" in MEDIA_DELIVERY_EXTS


def test_media_tag_extracts_ics_attachment():
    media, cleaned = BasePlatformAdapter.extract_media(
        "Calendar file attached.\\nMEDIA:/tmp/hermes-flight.ics\\nDone."
    )

    assert media == [("/tmp/hermes-flight.ics", False)]
    assert "MEDIA:" not in cleaned
    assert "hermes-flight.ics" not in cleaned
    assert "Calendar file attached." in cleaned
"""


class PatchError(RuntimeError):
    pass


def _default_hermes_root() -> Path:
    env_root = os.environ.get("HERMES_AGENT_ROOT")
    if env_root:
        return Path(env_root).expanduser()

    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    return hermes_home / "hermes-agent"


def patch_gateway_base(base_path: Path) -> bool:
    text = base_path.read_text(encoding="utf-8")
    original = text

    doc_start_marker = "SUPPORTED_DOCUMENT_TYPES = {\n"
    doc_end_marker = "\n}\n\n\n# ---------------------------------------------------------------------------\n# Text-injection"
    doc_start = text.find(doc_start_marker)
    if doc_start == -1:
        raise PatchError("Could not find SUPPORTED_DOCUMENT_TYPES")
    doc_end = text.find(doc_end_marker, doc_start)
    if doc_end == -1:
        raise PatchError("Could not find end of SUPPORTED_DOCUMENT_TYPES")
    doc_block = text[doc_start:doc_end]
    if '".ics": "text/calendar"' not in doc_block:
        anchor = '    ".txt": "text/plain",\n'
        if anchor not in doc_block:
            raise PatchError("Could not find .txt document MIME anchor")
        doc_block = doc_block.replace(anchor, anchor + DOC_ENTRY, 1)
        text = text[:doc_start] + doc_block + text[doc_end:]

    media_start_marker = "MEDIA_DELIVERY_EXTS: Tuple[str, ...] = (\n"
    media_end_marker = "\n)\n\n# Regex alternation"
    media_start = text.find(media_start_marker)
    if media_start == -1:
        raise PatchError("Could not find MEDIA_DELIVERY_EXTS")
    media_end = text.find(media_end_marker, media_start)
    if media_end == -1:
        raise PatchError("Could not find end of MEDIA_DELIVERY_EXTS")
    media_block = text[media_start:media_end]
    if '".ics"' not in media_block:
        if MEDIA_DOCUMENT_LINE not in media_block:
            raise PatchError("Could not find document delivery extension anchor")
        media_block = media_block.replace(
            MEDIA_DOCUMENT_LINE,
            MEDIA_DOCUMENT_LINE_WITH_ICS,
            1,
        )
        text = text[:media_start] + media_block + text[media_end:]

    if text != original:
        base_path.write_text(text, encoding="utf-8")
        return True
    return False


def write_regression_test(root: Path) -> bool:
    test_path = root / TEST_RELATIVE_PATH
    current = test_path.read_text(encoding="utf-8") if test_path.exists() else None
    if current == TEST_CONTENT:
        return False
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(TEST_CONTENT, encoding="utf-8")
    return True


def hermes_python(root: Path) -> Path:
    python = root / "venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)
    return python


def run_regression_test(root: Path) -> None:
    python = hermes_python(root)
    cmd = [str(python), "-m", "pytest", str(TEST_RELATIVE_PATH)]
    subprocess.run(cmd, cwd=root, check=True)


def verify(root: Path) -> None:
    code = textwrap.dedent(
        """
        from gateway.platforms.base import (
            BasePlatformAdapter,
            MEDIA_DELIVERY_EXTS,
            SUPPORTED_DOCUMENT_TYPES,
        )

        if SUPPORTED_DOCUMENT_TYPES.get(".ics") != "text/calendar":
            raise SystemExit(".ics is missing from SUPPORTED_DOCUMENT_TYPES")
        if ".ics" not in MEDIA_DELIVERY_EXTS:
            raise SystemExit(".ics is missing from MEDIA_DELIVERY_EXTS")
        media, cleaned = BasePlatformAdapter.extract_media("MEDIA:/tmp/flight.ics")
        if media != [("/tmp/flight.ics", False)] or "MEDIA:" in cleaned:
            raise SystemExit("extract_media does not deliver .ics MEDIA tags")
        """
    )
    subprocess.run([str(hermes_python(root)), "-c", code], cwd=root, check=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add Hermes gateway .ics document delivery support and tests.",
    )
    parser.add_argument(
        "--hermes-root",
        type=Path,
        default=_default_hermes_root(),
        help="Hermes Agent checkout root. Defaults to $HERMES_AGENT_ROOT or ~/.hermes/hermes-agent.",
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Patch and verify imports, but do not run pytest.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.hermes_root.expanduser().resolve()
    base_path = root / "gateway" / "platforms" / "base.py"
    if not base_path.exists():
        raise SystemExit(f"Hermes gateway base.py not found: {base_path}")

    changed_base = patch_gateway_base(base_path)
    changed_test = write_regression_test(root)
    verify(root)
    if not args.no_test:
        run_regression_test(root)

    print(
        "Hermes .ics delivery patch ready: "
        f"base_changed={changed_base} test_changed={changed_test}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
