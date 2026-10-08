from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Mapping, Sequence


def _signal_process_tree(process: subprocess.Popen[bytes], signum: int) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass
    elif signum == signal.SIGTERM:
        process.terminate()
    else:
        process.kill()


def _decode_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def run_with_timeout(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: float,
    cleanup_grace_seconds: float = 0.25,
) -> tuple[subprocess.CompletedProcess[str], bool]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    command = list(args)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name == "posix"),
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as deadline_error:
        timed_out = True
        _signal_process_tree(process, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=cleanup_grace_seconds)
        except subprocess.TimeoutExpired as terminate_error:
            _signal_process_tree(process, signal.SIGKILL)
            try:
                stdout, stderr = process.communicate(timeout=cleanup_grace_seconds)
            except subprocess.TimeoutExpired as kill_error:
                stdout = kill_error.output or terminate_error.output or deadline_error.output or b""
                stderr = kill_error.stderr or terminate_error.stderr or deadline_error.stderr or b""
                process.kill()
                try:
                    process.wait(timeout=cleanup_grace_seconds)
                except subprocess.TimeoutExpired:
                    pass
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()

    return (
        subprocess.CompletedProcess(
            command,
            process.returncode if process.returncode is not None else -signal.SIGKILL,
            _decode_output(stdout),
            _decode_output(stderr),
        ),
        timed_out,
    )
