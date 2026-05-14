#!/usr/bin/env python3
"""Inventory active local skills that are not in upstream Hermes Agent distribution.

Run from the hermes-agent git checkout. Compares active `skills/**/SKILL.md`
against `upstream/main:{skills,optional-skills}` by frontmatter `name` and reports
which local skills have an owning `cli/` directory.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def frontmatter_name(text: str) -> str | None:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        fm = text[3:end] if end != -1 else text[:1000]
    else:
        fm = text[:1000]
    match = re.search(r"(?m)^name:\s*[\"']?([^\"'\n#]+)", fm)
    return match.group(1).strip() if match else None


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True)


def skill_category(rel: str) -> tuple[str, str, str]:
    parts = Path(rel).parts
    base = parts[0]
    skill_dir = parts[-2]
    category = "/".join(parts[1:-2])
    return base, category, skill_dir


def local_active_skills(root: Path):
    for path in sorted((root / "skills").rglob("SKILL.md")):
        rel = path.relative_to(root).as_posix()
        if any(part == ".archive" for part in Path(rel).parts):
            continue
        text = path.read_text(errors="replace")
        name = frontmatter_name(text) or path.parent.name
        _, category, skill_dir = skill_category(rel)
        cli_dir = path.parent / "cli"
        cli_files = 0
        if cli_dir.is_dir():
            cli_files = sum(
                1
                for q in cli_dir.rglob("*")
                if q.is_file() and "__pycache__" not in q.parts
            )
        yield {
            "name": name,
            "category": category,
            "dir": skill_dir,
            "path": rel,
            "cli": cli_dir.is_dir(),
            "cli_files": cli_files,
        }


def upstream_distribution_names(ref: str) -> set[str]:
    try:
        out = run_git(["ls-tree", "-r", "--name-only", ref, "--", "skills", "optional-skills"])
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Unable to read {ref}. Run: git fetch upstream main --prune --no-tags"
        ) from exc
    names: set[str] = set()
    for rel in out.splitlines():
        if not rel.endswith("/SKILL.md"):
            continue
        try:
            text = run_git(["show", f"{ref}:{rel}"])
        except subprocess.CalledProcessError:
            text = ""
        names.add(frontmatter_name(text) or Path(rel).parent.name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="upstream/main", help="upstream distribution ref")
    parser.add_argument("--repo", default=".", help="hermes-agent checkout path")
    parser.add_argument("--tsv", action="store_true", help="machine-readable TSV output")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    if not (root / ".git").exists():
        print(f"Not a git checkout: {root}", file=sys.stderr)
        return 2

    upstream_names = upstream_distribution_names(args.ref)
    local = list(local_active_skills(root))
    custom = [row for row in local if row["name"] not in upstream_names]

    if args.tsv:
        print("name\tcategory\tpath\tcli\tcli_files")
        for row in custom:
            print(
                f"{row['name']}\t{row['category']}\t{row['path']}\t"
                f"{str(row['cli']).lower()}\t{row['cli_files']}"
            )
    else:
        print(f"local_active_skills={len(local)}")
        print(f"upstream_distribution_names={len(upstream_names)} ({args.ref}: skills + optional-skills)")
        print(f"custom_not_in_distribution={len(custom)}")
        print("\nCustom skills:")
        for row in custom:
            cli = f"cli yes ({row['cli_files']} files)" if row["cli"] else "cli no"
            print(f"- {row['name']} — {row['path']} — {cli}")
        print("\nCustom skills with CLI:")
        for row in custom:
            if row["cli"]:
                print(f"- {row['name']} — {row['path']} — {row['cli_files']} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
