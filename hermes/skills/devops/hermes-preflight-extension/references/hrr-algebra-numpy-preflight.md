# HRR algebra + numpy release preflight

## When this applies

Use this note when fact_store/holographic memory `probe`, `reason`, or `related` silently degrades to keyword/FTS behavior because `numpy` is missing or because the long-running gateway imported HRR before numpy was installed.

## Durable release fix pattern

1. Add `numpy` as a **base** `[project].dependencies` entry, not an optional extra:

```toml
# Holographic memory / fact_store HRR algebra (probe/reason/related).
"numpy>=1.24.0,<3",
```

2. Extend `scripts/hermes_release_preflight.py` to validate both package presence and actual HRR operation:
   - `import numpy as np`
   - `python -m pip show numpy`
   - `from plugins.memory.holographic import holographic as hrr`
   - assert `hrr._HAS_NUMPY`
   - run `hrr.encode_text('release preflight hrr check', 32)` and verify dim 32

3. Add metadata/report fields so the release artifact records the state:
   - `numpy_version`
   - `hrr_algebra_ok`
   - `hrr_algebra_probe`
   - report labels like `K2. numpy version`, `K3. HRR algebra`

4. Add structural regression tests in `tests/test_hermes_release_preflight.py`:
   - base dependencies include numpy before optional dependencies
   - preflight source imports numpy, checks `pip show numpy`, checks `_HAS_NUMPY`, and calls `hrr.encode_text`
   - metadata includes numpy/HRR fields

5. Update `docs/hermes-release-preflight.md` so future maintainers know the check exists and that vector rebuild is an operational task, not something preflight mutates.

## Active runtime repair pattern

For an already-running production runtime:

1. Install numpy into the active Hermes venv:

```bash
/home/konstantin/.hermes/hermes-agent/venv/bin/python -m pip install 'numpy>=1.24.0,<3'
```

2. Rebuild vectors if any facts lack `hrr_vector`:

```python
from pathlib import Path
from plugins.memory.holographic.store import MemoryStore
MemoryStore(db_path=Path('/home/konstantin/.hermes/memory_store.db')).rebuild_all_vectors()
```

3. Restart gateway or start a fresh process. If `plugins.memory.holographic.holographic` was imported before numpy existed, `_HAS_NUMPY=False` can be cached in the long-running process.

4. Verify after restart:
   - `hrr._HAS_NUMPY is True`
   - `numpy.__version__` is visible from active venv
   - `facts_with_hrr_vector == facts_total`
   - `FactRetriever(...).hrr_weight > 0`
   - `probe`, `related`, and `reason` return results without `fts_rank`

## Why `fts_rank` matters

In this implementation, fallback paths call `search()`, which returns FTS/Jaccard results that include `fts_rank`. HRR-only branches (`probe`, `related`, `reason`) score directly against `hrr_vector` and do not include `fts_rank`. So for a smoke test, `has_fts_rank=false` in `probe`/`related`/`reason` results is a useful runtime marker that the call did not go through the FTS fallback.

## Pitfalls

- Installing numpy is not enough for already-running gateway processes; restart/fresh session may be required because `_HAS_NUMPY` is computed at module import time.
- A DB can be healthy but partially unvectorized. Check both `PRAGMA integrity_check` and `COUNT(*) WHERE hrr_vector IS NOT NULL`.
- Preflight must be read-only: it can check DB integrity/counts and HRR imports in the RC venv, but must not rebuild or mutate `memory_store.db`.
- Run pytest with `-o 'addopts='` in this repo when system pytest lacks xdist.
