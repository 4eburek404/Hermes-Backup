# Fact store HRR algebra: numpy release durability

Use this when `fact_store probe`, `reason`, or `related` work but appear to degrade to keyword/FTS fallback instead of holographic HRR algebra.

## Symptom

- `fact_store search/probe/reason/related` returns responses, but HRR algebra is not actually active.
- Active Hermes runtime reports something equivalent to `numpy_available=False` for `plugins.memory.holographic.holographic._HAS_NUMPY`.
- SQLite memory DB may be healthy (`integrity_check=ok`, WAL/write lock OK), so DB health alone does not prove HRR is active.

## Root cause pattern

The holographic memory module depends on NumPy. Without NumPy it silently falls back to non-HRR keyword/FTS-style retrieval. Therefore `probe/reason/related` being callable is insufficient; verify `_HAS_NUMPY` and an actual `encode_text()` call.

## Durable fix pattern

1. Make NumPy a base/core dependency in the release source `pyproject.toml`, not an optional extra, because fact_store HRR algebra is part of baseline memory behavior:

```toml
"numpy>=1.24.0,<3",
```

2. Install NumPy into the active runtime venv for immediate recovery:

```bash
/home/konstantin/.hermes/hermes-agent/venv/bin/python -m pip install 'numpy>=1.24.0,<3'
```

3. Rebuild HRR vectors after installing NumPy, because existing facts may have missing `hrr_vector` values:

```python
from pathlib import Path
from plugins.memory.holographic.store import MemoryStore
MemoryStore(db_path=Path('/home/konstantin/.hermes/memory_store.db')).rebuild_all_vectors()
```

4. If the gateway process was already running before NumPy was installed, restart or otherwise start a fresh process before trusting live tool behavior. `_HAS_NUMPY` is set at module import time and may be cached false in the long-lived process.

## Release preflight guardrail

Add preflight checks that validate both dependency visibility and real HRR execution in the release-candidate venv, with `cwd` set to the RC directory so the source checkout does not leak through `sys.path[0]`:

- `import numpy as np; print(np.__version__)`
- `python -m pip show numpy`
- `from plugins.memory.holographic import holographic as hrr`
- `assert hrr._HAS_NUMPY`
- `hrr.encode_text('release preflight hrr check', 32)`

Record metadata such as:

- `numpy_version`
- `hrr_algebra_ok`
- `hrr_algebra_probe`

## Upstream/release update check pitfall

When checking GitHub for a safer/newer Hermes version after an HRR/NumPy incident, distinguish four layers before recommending an update or production switch:

1. **Latest release tag** — use GitHub releases/API or `git ls-remote --tags --sort=-version:refname https://github.com/NousResearch/hermes-agent.git 'refs/tags/v*'`. A newer `main` does not mean a newer stable release exists.
2. **Upstream `main` delta** — compare latest tag to `main`, e.g. GitHub compare `vYYYY.M.D...main`, and summarize commit count + recent relevant commits.
3. **Dependency placement** — inspect `pyproject.toml` at both the latest tag and `main`. NumPy inside an optional extra such as `voice = [...]` does **not** protect release builds installed with `.[messaging]`; HRR needs NumPy as a base/core dependency or the release preflight must install it explicitly.
4. **Open upstream memory PRs/issues** — search for `holographic`, `HRR`, `fact_store`, and `numpy`. Open PRs like memory doctor/algebra fixes mean upstream may know about the issue but not have shipped it.

Also check the local fork/source repo before syncing: branch, HEAD, dirty count, `origin/<branch>...HEAD` ahead/behind, and whether the local HRR commits are only local. Do not advise `/update`, blind upstream merge, or production symlink switch when the durable local fix exists only in an unpushed/dirty fork state.

## Verification checklist

- Active venv imports NumPy and HRR reports `_HAS_NUMPY=True`.
- `memory_store.db` has `hrr_vector IS NOT NULL` for all facts, or the expected subset if deliberately partial.
- `memory_banks` exist with expected dimensions (typically 1024).
- `fact_store probe`, `reason`, and `related` are tested after any required gateway restart/fresh session.
- Release preflight reports NumPy version and HRR algebra probe, e.g. `hrr_numpy=True;dim=32`.
- Regression tests for preflight pass with project addopts disabled when local pytest-xdist is unavailable:

```bash
/usr/bin/pytest tests/test_hermes_release_preflight.py -q -o 'addopts='
```
