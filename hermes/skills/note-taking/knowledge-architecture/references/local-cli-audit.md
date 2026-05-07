# Local CLI Audit Workflow

Session-derived reference for auditing Konstantin's local agent-facing CLIs without changing durable state.

## Scope

Default local CLI source tree:

```text
/home/konstantin/code/clis/
```

Known local CLI projects:

- `article` — article/HTML extraction to Markdown/text/JSON.
- `flights` — offline-first Travelpayouts flight routing and route validation.
- `hh-ru` — hh.ru public API wrapper.
- `knowledge` — read-only knowledge-architecture evidence collector.

Related external CLI:

- `fli` — pip package `flights` (`0.8.4` in live check on 2026-05-03), installed in the Hermes venv, not in `/home/konstantin/code/clis/`.

## Read-only audit sequence

Use this when the user asks to "check CLIs", audit local CLI tools, or review the skill↔CLI layer.

1. Gather durable context first:
   - `fact_store search` for `CLI`, `clis`, and tool names.
   - `session_search` for recent CLI creation/update work if provenance matters.
   - Read the relevant plan if present, especially `/home/konstantin/docs/plans/2026-05-01-hermes-skills-cli-candidates.md`.
2. Inventory live files:
   ```bash
   python3 - <<'PY'
   from pathlib import Path
   base = Path('/home/konstantin/code/clis')
   print([p.name for p in base.iterdir() if p.is_dir()])
   for cmd in ['article', 'flights', 'hh-ru', 'knowledge']:
       p = Path('/home/konstantin/.local/bin') / cmd
       print(cmd, p.exists(), p.resolve() if p.exists() else None)
   PY
   ```
3. Run safe help/doctor checks only. Avoid live writes and broad external calls:
   ```bash
   article --json doctor
   flights --json doctor
   hh-ru --json doctor
   knowledge --json doctor
   knowledge --json skill companion
   ```
4. Run offline tests and syntax checks:
   ```bash
   cd /home/konstantin/code/clis/<name> && make test
   python3 -m compileall -q .
   ```
5. Run small smoke checks that do not mutate external state:
   - `article`: local `/tmp/*.html` fixture with `article --json read`.
   - `flights`: `route plan` with explicit `--depart-date`; live API only with explicit user need.
   - `hh-ru`: reference endpoints like `roles` or `dictionaries`; avoid repeated `/vacancies` calls because unauthenticated searches can hit `403 forbidden` / IP-ban.
   - `knowledge`: `report --all` and `skill companion` are read-only evidence, not permission to edit.
6. Check packaging drift:
   - compare `pyproject.toml` `project.version`, `*_cli/__init__.py __version__`, CLI `--version`, and `importlib.metadata.version()` if installed as a package.
7. Check output hygiene:
   - ensure request and response headers redact `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, and API-key-like headers.
   - never paste token/cookie values into the user-facing report.
8. If findings imply edits to docs/plans/skills/fact_store/config, report the expected changes and mutate only when the user explicitly asked for updates or the current task is skill-library maintenance.

## Findings from 2026-05-03 audit

Verified live:

- `article`, `flights`, `hh-ru`, and `knowledge` wrappers exist in `~/.local/bin/` and point to `/home/konstantin/code/clis/*` through bash wrappers.
- `fli` exists at `/home/konstantin/.hermes/hermes-agent/venv/bin/fli`.
- Tests passed: `article` 4, `flights` 12 before the fix / 13 after the fix, `hh-ru` 4 before the fix / 5 after the fix, `knowledge` 5.
- `python3 -m compileall -q .` passed for all four local CLI projects.
- `knowledge --json skill companion` returned `issue_count: 0` and all contract checks true.
- `hh-ru --json roles` returned HTTP 200 and originally exposed a `Set-Cookie` response header in the JSON envelope. The fix was to route successful response headers through `redact_headers(dict(resp.headers.items()))` and make `redact_headers()` case-insensitively mask `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, and `x-api-key` as `[REDACTED]` while preserving non-sensitive headers.
- `flights` had version drift: CLI runtime reported `0.7.0`, while `pyproject.toml` and package metadata reported `0.5.0`. The fix was to set `pyproject.toml` to `0.7.0`, add an offline test comparing `pyproject.toml` `project.version` with `flights_cli.__version__`, and reinstall editable metadata.
- `python3 -m pip install -e .` in `/home/konstantin/code/clis/flights` initially failed because setuptools discovered the extra top-level research directory `aeroflot_research*`. Add explicit package discovery to package only `flights_cli*` and exclude `aeroflot_research*`:
  ```toml
  [tool.setuptools.packages.find]
  include = ["flights_cli*"]
  exclude = ["aeroflot_research*"]
  ```
- The CLI candidates plan was closed and archived at `/home/konstantin/docs/plans/archive/2026/done/2026-05-01-hermes-skills-cli-candidates.md`; the root plan path should no longer exist.
- `knowledge --json plans audit` may exceed terminal tool output limits. If JSON parsing appears to fail around a truncation boundary, rerun via direct `subprocess.run(..., capture_output=True)` or another non-truncating path before calling it a CLI bug. In the 2026-05-03 check, direct subprocess returned valid JSON with `returncode: 0` and `finding_count: 9`.

## Pitfalls

- `hh-ru --version` is not implemented as of the audit; it exits with argparse error because a command is required. Use `hh-ru --json doctor` for version/status.
- `flights route plan` requires `--depart-date`; positional date arguments are invalid.
- `hh-ru areas get 113` is invalid; use `hh-ru --json areas tree --id 113` or `areas resolve`.
- `/vacancies` is the dangerous hh.ru endpoint for rate/IP bans; reference endpoints are safer for smoke tests.
- `search_files` can miss broad filesystem intent; use direct `Path.iterdir()`/`Path.rglob()` for inventories.
