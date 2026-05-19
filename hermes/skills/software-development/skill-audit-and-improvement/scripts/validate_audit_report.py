#!/usr/bin/env python3
"""Validate audit_skill.py JSON reports against the stable report contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REQUIRED = ["schema_version", "tool", "repo", "target", "summary", "findings", "checks", "evidence_manifest"]


def manual_validate(report: Dict[str, Any]) -> Optional[str]:
    for key in REQUIRED:
        if key not in report:
            return f"missing required key: {key}"
    if report.get("schema_version") != "1.0.0":
        return "schema_version must be 1.0.0"
    if report.get("tool", {}).get("name") != "audit_skill":
        return "tool.name must be audit_skill"
    if not isinstance(report.get("findings"), list):
        return "findings must be a list"
    checks = report.get("checks")
    if not isinstance(checks, (list, dict)):
        return "checks must be a list or object"
    if isinstance(checks, dict):
        for key in ("cli_contract", "schema_contract"):
            section = checks.get(key)
            if section is not None and not isinstance(section, dict):
                return f"checks.{key} must be an object"
    if not isinstance(report.get("evidence_manifest"), list):
        return "evidence_manifest must be a list"
    for index, finding in enumerate(report.get("findings", [])):
        for key in ["rule_id", "severity", "category", "message", "location", "fingerprint"]:
            if key not in finding:
                return f"finding[{index}] missing key: {key}"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_audit_report.py REPORT.json", file=sys.stderr)
        return 2
    report_path = Path(argv[1])
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        return 1

    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "audit-report.schema.json"
    try:
        import jsonschema  # type: ignore
    except ImportError:
        error = manual_validate(report)
    else:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(report, schema)
            error = None
        except Exception as exc:
            error = str(exc)

    if error:
        print(f"audit report schema invalid: {error}", file=sys.stderr)
        return 1
    print("schema_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
