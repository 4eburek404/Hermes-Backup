# Skills inspect resolution logic audit (2026-05-12)

## Problem

`hermes skills inspect productivity/flight-search` resolves to the ClawHub remote
skill (source=clawhub, trust=community) instead of the local bundled/installed skill
(source=builtin). Meanwhile, `hermes skills list` correctly shows it as
`flight-search | productivity | builtin | builtin | enabled`.

## Architecture

Two fully separate code paths for skill metadata:

### Runtime path (agent tools: `skill_view`, `skills_list`)

- `tools/skills_tool.py` → `_find_all_skills()` → `agent/skill_utils.iter_skill_index_files()`
- Scans `~/.hermes/skills/` (state dir) — reads local SKILL.md files
- Correctly identifies local/bundled/hub via `HubLockFile`

### Hub/CLI path (`hermes skills inspect`, `hermes skills search/install`)

- `hermes_cli/skills_hub.py` → `do_inspect()` → `create_source_router()` from `tools/skills_hub.py`
- Returns a list of remote registry sources — **no local/installed source**:

| # | Source | source_id | What it scans |
|---|--------|-----------|---------------|
| 1 | OptionalSkillSource | official | `optional-skills/` from repo (NOT `~/.hermes/skills/`) |
| 2 | HermesIndexSource | hermes-index | Cached JSON catalog from docs site |
| 3 | SkillsShSource | skills-sh | skills.sh GitHub API |
| 4 | WellKnownSkillSource | well-known | Well-known agent skill endpoints |
| 5 | UrlSource | — | Direct HTTP(S) URL to SKILL.md |
| 6 | GitHubSource | github | GitHub with taps |
| 7 | ClawHubSource | clawhub | ClawHub API (`clawhub.ai/api/v1/skills/{slug}`) |
| 8 | ClaudeMarketplaceSource | claude-marketplace | Claude marketplace |
| 9 | LobeHubSource | lobehub | LobeHub registry |

None of these scan `~/.hermes/skills/`.

## Resolution flow for `productivity/flight-search`

1. `_resolve_short_name` skipped (identifier contains `/`)
2. `_resolve_source_meta_and_bundle` iterates sources in order
3. OptionalSkillSource: `skill_name = "flight-search"` → scans `optional-skills/` → **not found** (flight-search is bundled, not optional)
4. HermesIndexSource: searches JSON index → **not found** (flight-search missing from index)
5. ClawHubSource: `slug = "flight-search"` (strips prefix) → API `GET /skills/flight-search` → **found** → returns meta with `source="clawhub"`, `trust_level="community"`
6. Result: ClawHub skill overrides local builtin

For bare `flight-search` (no `/`): `_resolve_short_name` calls `unified_search`.
When HermesIndexSource is available, `parallel_search_sources` **skips** api_source_ids
(github, skills-sh, clawhub, etc.) because the index already has their data.
Since the index doesn't contain `flight-search`, nothing is found → **error**:
"No skill named 'flight-search' found in any source."

## `do_list` vs `do_inspect` inconsistency

| Command | Code path | Scans local? | Shows flight-search as |
|---------|-----------|-------------|----------------------|
| `hermes skills list` | `do_list` → `_find_all_skills()` | **Yes** | `builtin` |
| `hermes skills inspect productivity/flight-search` | `do_inspect` → `create_source_router()` | **No** | `clawhub`/`community` |
| `hermes skills inspect flight-search` | `_resolve_short_name` → `unified_search` | **No** | **Error** (not found) |
| `hermes skills search flight-search` | `unified_search` | **No** | Error (not found with `--source all`) |
| `hermes skills search flight-search --source clawhub` | `unified_search` | **No** | ClawHub result |

## No local-only/local-first config option

Checked:
- `hermes skills inspect --help` — no `--source` flag
- `config.yaml` — no `source_order`, `source_priority`, `disable_hub`, `local_first`
- `.env` — no `HERMES_HUB*`, `NO_HUB`, `SKIP_HUB`, `LOCAL_SKILL*`
- `create_source_router()` — no parameters for excluding/reordering sources
- `do_inspect()` / `inspect_skill()` — no `source_filter` parameter
- `_resolve_source_meta_and_bundle()` — no local-first logic

Only `hermes skills search` and `hermes skills list` accept `--source`.

## Key files

- `hermes_cli/skills_hub.py:627` — `do_inspect()`
- `hermes_cli/skills_hub.py:723` — `inspect_skill()`
- `hermes_cli/skills_hub.py:109` — `_resolve_source_meta_and_bundle()`
- `hermes_cli/skills_hub.py:34` — `_resolve_short_name()`
- `tools/skills_hub.py:3092` — `create_source_router()`
- `tools/skills_hub.py:2324` — `OptionalSkillSource` (repo `optional-skills/`, NOT `~/.hermes/skills/`)
- `tools/skills_hub.py:2936` — `HermesIndexSource`
- `tools/skills_hub.py:1580` — `ClawHubSource`
- `tools/skills_hub.py:3209` — `unified_search()`
- `tools/skills_tool.py:541` — `_find_all_skills()` (scans `~/.hermes/skills/`)
- `hermes_constants.py:302` — `get_skills_state_dir()` → `~/.hermes/skills/`

## Implication for agents using `skill_view`

The runtime `skill_view()` tool in `tools/skills_tool.py` correctly reads from
`~/.hermes/skills/` (local state dir). So when the agent loads flight-search,
it sees the correct local SKILL.md. The collision only affects the CLI hub
commands (`inspect`, `search`, `install`).

## Minimal fix direction (no code written)

Option A: Add `LocalInstalledSource(SkillSource)` with `source_id = "local"`,
`trust_level = "builtin"`, scanning `SKILLS_DIR` via `iter_skill_index_files`.
Place it first in `create_source_router()`. This makes `hermes skills inspect`
look at installed/bundled skills before remote registries.

Option B: Add `--source` flag to `hermes skills inspect` (like `search --source`).
User could then `hermes skills inspect --source local productivity/flight-search`.
Still requires `LocalInstalledSource`.

Both options require adding a new SkillSource subclass — no config-only workaround exists.