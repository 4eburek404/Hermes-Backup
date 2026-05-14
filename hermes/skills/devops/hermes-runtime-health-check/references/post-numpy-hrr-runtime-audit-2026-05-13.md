# Post-NumPy HRR Runtime Audit — 2026-05-13

## Context

A Hermes release candidate gained a durable core `numpy` dependency so holographic memory HRR algebra would not silently degrade to FTS fallback. The active production runtime was still on the previous release directory, so NumPy was hot-installed into the active venv, all memory vectors were rebuilt, and the gateway was restarted.

## What to verify after this class of change

1. **Process restart actually occurred**
   - Capture `systemctl --user show hermes-gateway -p MainPID -p ExecMainStartTimestamp -p ActiveState -p SubState -p ExecStart -p WorkingDirectory`.
   - If NumPy was installed after the process started, restart is required because `_HAS_NUMPY` may be cached false in the already-imported module.

2. **Active runtime vs durable release state**
   - `readlink -f ~/.hermes/hermes-agent` identifies the active release.
   - A venv hotfix can make runtime work while active `release_metadata.json` still lacks new fields such as `numpy_version` / `hrr_algebra_ok`.
   - Report this as “runtime hotfixed; durable in newer RC/source; active metadata blind spot” rather than a runtime failure.

3. **Dependency and import health**
   - Run active venv `python -m pip check`.
   - Import `numpy`, `telegram`, `pydantic`, `yaml`, `hermes_cli.main`, `plugins.memory.holographic.holographic`, `store`, and `retrieval` from the active venv.
   - Verify `hrr._HAS_NUMPY is True` and `len(hrr.encode_text('health check hrr algebra', 32)) == 32`.

4. **Memory DB health**
   - Open `~/.hermes/memory_store.db` read-only (`file:...?mode=ro`).
   - Check `PRAGMA integrity_check == ok`.
   - Check `SELECT COUNT(*), SUM(hrr_vector IS NOT NULL) FROM facts`; all facts should have HRR vectors after rebuild.

5. **fact_store HRR vs FTS fallback**
   - Do not accept `probe`, `related`, or `reason` merely returning rows as proof of HRR.
   - Fallback path calls FTS `search()` and includes `fts_rank` in result shape.
   - HRR direct paths compute scores from vectors and return facts without `fts_rank`.
   - Also check source path if needed: retrieval code gates on `_HAS_NUMPY`, DB vector availability, and banks.

6. **Fresh logs only**
   - `tail -5000 agent.log` can still show old tracebacks from days earlier.
   - Use the gateway restart timestamp as cutoff and count only log lines whose parsed timestamp is newer.
   - Treat unparsed traceback continuation lines only as part of a fresh issue when attached to a fresh matching error header.

7. **CLI smoke checks**
   - Non-mutating commands that proved healthy in this session:
     - `hermes --version`
     - `hermes gateway status`
     - `hermes skills list`
     - `hermes tools list`
     - `hermes cron status`
     - `hermes memory status`
     - `hermes mcp list`
     - `hermes sessions stats`
     - `hermes doctor`

## Findings from the case

- Gateway was active/running after restart.
- Active venv had `numpy==2.4.4` and `pip check` returned no broken requirements.
- HRR import probe succeeded: `_HAS_NUMPY=True`, encode dimension 32.
- `memory_store.db` was healthy and all `126/126` facts had HRR vectors.
- `fact_store probe/related/reason` returned HRR-shaped results without `fts_rank`.
- No fresh post-restart critical errors were found in journald, agent.log, or gateway.log after timestamp filtering.

## Important non-HRR issues found

- **Doctor false positive:** `hermes doctor` reported “Venv entry point not found” even though `~/.hermes/hermes-agent/venv/bin/hermes` existed and `~/.local/bin/hermes` pointed to it. Root cause: doctor uses `PROJECT_ROOT = Path(__file__).parent.parent.resolve()`, which resolves to `.../venv/lib/python3.11/site-packages` in release-dir installs and then looks for `site-packages/venv/bin/hermes`.
- **Browser tooling unavailable:** browser/browser-cdp were enabled/listed but `agent-browser` was not installed, so browser automation should be considered degraded until installed or disabled.
- **Disk pressure:** free disk was ~8.8% (~3.24 GB). Historical logs had `No space left on device`; low disk is a reliability risk for state/log/session writes.

## Reporting pattern

Separate:

- **Broken now:** fresh critical errors, failed imports, DB corruption, gateway inactive.
- **Degraded/latent:** browser toolset enabled but dependency missing, low disk, config version outdated.
- **Audit blind spot:** active runtime hotfixed while active release metadata predates the new preflight fields.
- **Historical noise:** old errors in log tails before the restart/change timestamp.
