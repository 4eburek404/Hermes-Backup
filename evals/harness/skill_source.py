from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


def _run_git(
    repo_root: Path,
    *args: str,
    text: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=text,
    )


def _hash_entry(hasher: Any, root: Path, path: Path) -> None:
    rel = path.relative_to(root).as_posix() if path != root else "."
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        kind = b"symlink"
        payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
        executable = b"0"
    elif stat.S_ISREG(mode):
        kind = b"file"
        payload = path.read_bytes()
        executable = b"1" if mode & stat.S_IXUSR else b"0"
    else:
        return

    hasher.update(rel.encode("utf-8", errors="surrogateescape"))
    hasher.update(b"\0")
    hasher.update(kind)
    hasher.update(b"\0")
    hasher.update(executable)
    hasher.update(b"\0")
    hasher.update(hashlib.sha256(payload).digest())
    hasher.update(b"\0")


def content_sha256(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        raise FileNotFoundError(path)

    hasher = hashlib.sha256()
    if path.is_dir() and not path.is_symlink():
        for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
            _hash_entry(hasher, path, child)
    else:
        _hash_entry(hasher, path, path)
    return hasher.hexdigest()


def _copy_working_tree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)


def _materialize_git_tree(
    repo_root: Path,
    skill_path: Path,
    commit: str,
    destination: Path,
) -> None:
    prefix = PurePosixPath(skill_path.as_posix())
    proc = _run_git(
        repo_root,
        "ls-tree",
        "-r",
        "-z",
        commit,
        "--",
        prefix.as_posix(),
        text=False,
    )
    records = [record for record in proc.stdout.split(b"\0") if record]
    if not records:
        raise FileNotFoundError(
            f"skill path not found at {commit}: {prefix.as_posix()}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=False)

    for record in records:
        meta, raw_path = record.split(b"\t", 1)
        mode, object_type, object_sha = meta.decode("ascii").split(" ", 2)
        if object_type != "blob":
            raise ValueError(
                f"unsupported git object type for skill source: {object_type}"
            )

        repo_path = PurePosixPath(
            raw_path.decode("utf-8", errors="surrogateescape")
        )
        try:
            relative = repo_path.relative_to(prefix)
        except ValueError as exc:
            raise RuntimeError(
                f"git returned path outside requested skill: {repo_path}"
            ) from exc

        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        blob = _run_git(
            repo_root,
            "cat-file",
            "blob",
            object_sha,
            text=False,
        ).stdout

        if mode == "120000":
            target.symlink_to(
                blob.decode("utf-8", errors="surrogateescape")
            )
            continue
        if mode not in {"100644", "100755"}:
            raise ValueError(f"unsupported git mode for skill source: {mode}")

        target.write_bytes(blob)
        if mode == "100755":
            target.chmod(
                target.stat().st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )


def materialize_skill_source(
    repo_root: Path,
    skill_path: Path,
    source: dict[str, Any],
    destination: Path,
) -> dict[str, Any]:
    """Materialize a complete skill without mutating the source checkout."""
    repo_root = repo_root.resolve()
    skill_path = Path(skill_path)

    if skill_path.is_absolute() or ".." in skill_path.parts:
        raise ValueError("skill_path must be repository-relative")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)

    kind = source.get("source")
    head = _run_git(repo_root, "rev-parse", "HEAD").stdout.strip()

    if kind == "working_tree":
        source_path = repo_root / skill_path
        if not source_path.exists() and not source_path.is_symlink():
            raise FileNotFoundError(
                f"working-tree skill path not found: {skill_path.as_posix()}"
            )
        status = _run_git(
            repo_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            skill_path.as_posix(),
        ).stdout
        _copy_working_tree(source_path, destination)
        return {
            "source": "working_tree",
            "requested_ref": None,
            "resolved_commit": head,
            "content_sha256": content_sha256(destination),
            "working_tree_dirty": bool(status.strip()),
            "skill_path": skill_path.as_posix(),
        }

    if kind == "git":
        requested_ref = source.get("ref")
        if not isinstance(requested_ref, str) or not requested_ref.strip():
            raise ValueError("git skill source requires non-empty ref")

        resolved = _run_git(
            repo_root,
            "rev-parse",
            "--verify",
            f"{requested_ref}^{{commit}}",
        ).stdout.strip()
        _materialize_git_tree(
            repo_root,
            skill_path,
            resolved,
            destination,
        )
        return {
            "source": "git",
            "requested_ref": requested_ref,
            "resolved_commit": resolved,
            "content_sha256": content_sha256(destination),
            "working_tree_dirty": None,
            "skill_path": skill_path.as_posix(),
        }

    raise ValueError(f"unsupported skill source: {kind!r}")
