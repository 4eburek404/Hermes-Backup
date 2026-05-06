---
name: hermes-agent-skill-authoring
description: "Author in-repo SKILL.md: frontmatter, validator, structure."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [skills, authoring, hermes-agent, conventions, skill-md]
    related_skills: [writing-plans, requesting-code-review]
---

# Authoring Hermes-Agent Skills (in-repo)

## Overview

There are two places a SKILL.md can live:

1. **User-local:** `~/.hermes/skills/<maybe-category>/<name>/SKILL.md` — personal, not shared. Created via `skill_manage(action='create')`.
2. **In-repo (this skill is about this case):** `/home/bb/hermes-agent/skills/<category>/<name>/SKILL.md` — committed, shipped with the package. Use `write_file` + `git add`. `skill_manage(action='create')` does NOT target this tree.

## When to Use

- User asks you to add a skill "in this branch / repo / commit"
- User asks you to review a conversation/session and update the skill library, especially after a correction or newly discovered workflow
- You're committing a reusable workflow that should ship with hermes-agent
- You're editing an existing skill under `/home/bb/hermes-agent/skills/` (use `patch` for small edits, `write_file` for rewrites; `skill_manage` still works for patch on in-repo skills, but not for `create`)

## Required Frontmatter

Source of truth: `tools/skill_manager_tool.py::_validate_frontmatter`. Hard requirements:

- Starts with `---` as the first bytes (no leading blank line).
- Closes with `\n---\n` before the body.
- Parses as a YAML mapping.
- `name` field present.
- `description` field present, ≤ **1024 chars** (`MAX_DESCRIPTION_LENGTH`).
- Non-empty body after the closing `---`.

Peer-matched shape used by every skill under `skills/software-development/`:

```yaml
---
name: my-skill-name               # lowercase, hyphens, ≤64 chars (MAX_NAME_LENGTH)
description: Use when <trigger>. <one-line behavior>.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [short, descriptive, tags]
    related_skills: [other-skill, another-skill]
---
```

`version` / `author` / `license` / `metadata` are NOT enforced by the validator, but every peer has them — omit and your skill sticks out.

## Size Limits

- Description: ≤ 1024 chars (enforced).
- Full SKILL.md: ≤ 100,000 chars (enforced as `MAX_SKILL_CONTENT_CHARS`, ~36k tokens).
- Peer skills in `software-development/` sit at **8-14k chars**. Aim for that range. If you're pushing past 20k, split into `references/*.md` and reference them from SKILL.md.
- For user-local/runtime skills that run frequently (cron, memory curation, gateway workflows), keep SKILL.md as the runtime protocol. Move rare setup, maintenance, and benchmark procedures to runbooks or `references/*.md`; leave only a short pointer in the skill. This reduces context bloat without losing the procedure.

## Splitting an Oversized Skill

When a SKILL.md grows past ~20K chars, it degrades agent performance: LLM attention dilutes, important rules drown in details, and the skill wastes context on every invocation even when only 20% is needed. Symptoms: repeated pitfall violations despite the pitfall being documented, the agent missing rules buried deep in the file, or the user complaining the skill is "too large / мутно".

**Splitting pattern (flight-search-routing reduction from 47K → 4K core):**

1. **Identify what must stay in core:** rules, pitfalls, decision trees, quick-reference one-liners, verification checklists. These load on every invocation and must be compact (~4-8K target).
2. **Extract to `references/`**: detailed step-by-step workflows, CLI command tables with all flags, API endpoint documentation, per-site compatibility matrices with paragraphs, browser navigation instructions, reproduction recipes from past sessions.
3. **Extract to `references/` with one-line pointers in core**: duplication between SKILL.md and existing reference files (e.g., Aeroflot live search details already in `references/aeroflot-live-kupibilet-frontend-search.md`). Delete the duplicate from core, keep the reference.
4. **Consolidate closely related details**: if 3 sections each talk about browser workflows for different sites, merge into one `references/browser-headless-workflows.md`. If CLI docs for 3 tools are scattered, merge into one `references/cli-reference.md`.
5. **Keep pitfalls in core, NOT in references**: pitfalls are the #1 thing the agent needs to see on every invocation. They must be in SKILL.md, compact and prominent.
6. **Version bump**: splitting is a breaking structural change → bump version (1.0.0 → 2.0.0).

**What goes where:**

| Content type | Location | Loads when |
|---|---|---|
| Rules, pitfalls, decision trees, verification | SKILL.md core | Every invocation |
| CLI one-liners (command + what it does) | SKILL.md core | Every invocation |
| Full CLI docs (all flags, options, tables) | `references/cli-reference.md` | On demand |
| Browser step-by-step workflows | `references/browser-headless-workflows.md` | On demand |
| Per-site detailed notes + decision trees | `references/site-compatibility.md` | On demand |
| Session-specific verified results | `archive/<topic>-<date>.md` | Never auto-loaded |

**CLI self-documentation principle:** If the skill's CLI tools have `--help` that answers the question in <2 seconds, do NOT copy `--help` output into references. Store only what the CLI *cannot* tell you: pitfalls, strategic insights, API quirks, site-specific bugs, workflow sequences. A reference file that duplicates `--help` is dead weight that rots silently while the CLI stays current. Replace CLI docs with: *«For CLI syntax, call `tool <cmd> --help`»* and keep only unique insights (source comparison tables, optimal pipeline, sanctions rules, carrier semantics).

**Session-specific data → archive/:** Verified results for a specific date/route (prices, flight numbers, combinations) go into `archive/`, NOT `references/`. Archive files are not auto-listed in `linked_files` and should never be loaded proactively. If a user asks about the same route later, call the CLI live — the data will be fresher. Unique insights extracted from session data (ranking rules, bug patterns) go into core or references, not the raw results.

**Test after splitting:** `skill_view(name)` should show the core (~4-8K) plus `linked_files` listing all references. Invoke `skill_view(name, file_path='references/...')` to confirm each reference loads correctly.

## Peer-Matched Structure

Every in-repo skill follows roughly:

```
# <Title>

## Overview
One or two paragraphs: what and why.

## When to Use
- Bulleted triggers
- "Don't use for:" counter-triggers

## <Topic sections specific to the skill>
- Quick-reference tables are common
- Code blocks with exact commands
- Hermes-specific recipes (tests via scripts/run_tests.sh, ui-tui paths, etc.)

## Common Pitfalls
Numbered list of mistakes and their fixes.

## Verification Checklist
- [ ] Checkbox list of post-action verifications

## One-Shot Recipes (optional)
Named scenarios → concrete command sequences.
```

Not every section is mandatory, but `Overview` + `When to Use` + actionable body + pitfalls are the minimum for the skill to feel like a peer.

## Directory Placement

```
skills/<category>/<skill-name>/SKILL.md
```

Categories currently in repo (confirm with `ls skills/`): `autonomous-ai-agents`, `creative`, `data-science`, `devops`, `dogfood`, `email`, `gaming`, `github`, `leisure`, `mcp`, `media`, `mlops/*`, `note-taking`, `productivity`, `red-teaming`, `research`, `smart-home`, `social-media`, `software-development`.

Pick the closest existing category. Don't invent new top-level categories casually.

## Session Review and Skill Library Maintenance

When a user asks to review a conversation and update the skill library, treat it as an active curation task, not a passive audit. Most sessions with a user correction, workflow change, tricky fix, or reusable tool pattern should produce at least one targeted skill update.

Update priority:

1. **Patch a currently-loaded skill first** if it governs the task that produced the learning. A correction during a flight search belongs in the flight-search skill; a correction about skill authoring belongs here. The skill in play is usually the right behavior surface.
2. **Patch an existing class-level umbrella** before creating a new skill. The library should be a small set of rich class-level skills, not a flat list of one-session artifacts.
3. **Add support files when details are useful but too specific for core.** Use `references/` for session-specific evidence, repro notes, API excerpts, or condensed domain notes; `templates/` for copy-and-modify starters; `scripts/` for deterministic probes or verification helpers. Add a one-line pointer from `SKILL.md` to every new support file.
4. **Create a new skill only for a reusable class of work** that no existing umbrella covers. Names must describe the class, not today's PR, bug string, route, model, or incident.

What counts as a skill signal:

- User corrected style, tone, format, legibility, verbosity, or reporting structure.
- User corrected workflow, sequence, scope, or how a result should generalize.
- A non-trivial workaround, debugging path, CLI pattern, or provider/tool quirk emerged.
- A loaded skill was missing a step, too narrow, outdated, or produced a repeatable mistake.

Preference embedding rule: if the user complains about how a class of task was done, update the governing `SKILL.md` body, not only memory. Memory records who the user is; skills record how to execute the task class for that user. Abstract incidents into rules: specific cases should become examples or regression notes under `references/`, while the core skill carries the universal procedure.

## Workflow

1. **Survey peers** in the target category:
   ```
   ls skills/<category>/
   ```
   Read 2-3 peer SKILL.md files to match tone and structure.
2. **Check validator constraints** in `tools/skill_manager_tool.py` if unsure.
3. **Draft** with `write_file` to `skills/<category>/<name>/SKILL.md`.
4. **Validate locally**:
   ```python
   import yaml, re, pathlib
   content = pathlib.Path("skills/<category>/<name>/SKILL.md").read_text()
   assert content.startswith("---")
   m = re.search(r'\n---\s*\n', content[3:])
   fm = yaml.safe_load(content[3:m.start()+3])
   assert "name" in fm and "description" in fm
   assert len(fm["description"]) <= 1024
   assert len(content) <= 100_000
   ```
5. **Git add + commit** on the active branch.
6. **Note:** the CURRENT session's skill loader is cached — `skill_view` / `skills_list` will not see the new skill until a new session. This is expected, not a bug.

## Cross-Referencing Other Skills

`metadata.hermes.related_skills` unions both trees (`skills/` in-repo and `~/.hermes/skills/`) at load time. You CAN reference a user-local skill from an in-repo skill, but it won't resolve for other users who clone the repo fresh. Prefer referencing only in-repo skills from in-repo skills. If a frequently-referenced skill lives only in `~/.hermes/skills/`, consider promoting it to the repo.

## Editing Existing In-Repo Skills

- **Small fix (typo, added pitfall, tightened trigger):** `skill_manage(action='patch', name=..., old_string=..., new_string=...)` works fine on in-repo skills.
- **Major rewrite:** `write_file` the whole SKILL.md. `skill_manage(action='edit')` also works but requires supplying the full new content.
- **Adding supporting files:** `write_file` to `skills/<category>/<name>/references/<file>.md`, `templates/<file>`, or `scripts/<file>`. `skill_manage(action='write_file')` also works and enforces the references/templates/scripts/assets subdir allowlist.
- **Always commit** the edit — in-repo skills are source, not runtime state.

## CLI-Backed Companion Skills

When a skill is a companion for a local CLI, make the relationship bidirectional instead of only documenting commands in prose.

Recommended pattern:

1. **Skill starts with a self-check command** before broad usage, for example:
   ```bash
   command -v knowledge
   knowledge --json skill companion
   knowledge --json doctor
   ```
2. **CLI exposes a read-only contract command** such as `tool --json skill companion` / `tool skill companion --format md` that reports:
   - companion skill path and existence;
   - lightweight metadata (`name`, `description`, size, hash);
   - booleans for required contract clauses (self-check, broad audit command, mutation boundary, read-only boundary, live/API boundary);
   - issue/gap list;
   - recommended command sequence for agents.
3. **Do not dump the full SKILL.md body** from the CLI contract command. Return metadata/hash/booleans so agents can detect drift without wasting context or leaking unrelated details.
4. **Keep the mutation boundary explicit** in both places: CLI output is evidence, not permission to edit docs, memory, skills, config, cron, credentials, or external systems.
5. **Test the symbiosis** with at least one offline test that creates a temporary SKILL.md, runs the contract command, verifies expected booleans, and asserts that sensitive/full skill body text is not printed.

This is useful for local evidence-collector CLIs where the skill governs agent behavior and the CLI can machine-check that the companion skill has not drifted.

## Common Pitfalls

1. **Using `skill_manage(action='create')` for an in-repo skill.** It writes to `~/.hermes/skills/`, not the repo tree. Use `write_file` for in-repo creation.

2. **Leading whitespace before `---`.** The validator checks `content.startswith("---")`; any leading blank line or BOM fails validation.

3. **Description too generic.** Peer descriptions start with "Use when ..." and describe the *trigger class*, not the one task. "Use when debugging X" > "Debug X".

4. **Forgetting the author/license/metadata block.** Not validator-enforced, but every peer has it; omitting makes the skill look half-finished.

5. **Writing a skill that duplicates a peer.** Before creating, `ls skills/<category>/` and open 2-3 peers. Prefer extending an existing skill to creating a narrow sibling.

6. **Treating a session review as optional cleanup.** If the user asked to update the skill library after a correction, do not answer with “nothing to save” unless you verified there was genuinely no skill-level signal. Patch the governing skill, or explain exactly why no class-level skill applies.

7. **Encoding a one-off incident as the core rule.** Generalize the procedure in `SKILL.md`; keep concrete incident details in `references/` or `archive/` as regression examples.

8. **Stopping at an interruption summary instead of closeout.** If tool-call limits, context compression, or a user interruption stops a skill-library task after edits but before verification, treat the next turn as a resume point: reload the governing skill, finish validation/secret scan/generated-artifact cleanup, update todo/plan status, and archive/close the plan before reporting done. A summary of what remains is not a substitute for closeout.

9. **Expecting the current session to see the new skill.** It won't. The skill loader is initialized at session start. Verify in a fresh session or via `skill_view` using the exact path.

10. **Leaving generated bytecode in skill support dirs.** Running `python3 -m py_compile` or importing support scripts can create `scripts/__pycache__/*.pyc`; these binary artifacts then show up as linked skill files and waste context. Validate scripts, then remove generated `__pycache__/*.pyc` (or run validation outside the skill tree) before finalizing.

11. **Linking to skills that don't exist in-repo.** `related_skills: [some-user-local-skill]` works for you but breaks for other clones. Prefer only in-repo links.

## Verification Checklist

- [ ] File is at `skills/<category>/<name>/SKILL.md` (not in `~/.hermes/skills/`)
- [ ] Frontmatter starts at byte 0 with `---`, closes with `\n---\n`
- [ ] `name`, `description`, `version`, `author`, `license`, `metadata.hermes.{tags, related_skills}` all present
- [ ] Name ≤ 64 chars, lowercase + hyphens
- [ ] Description ≤ 1024 chars and starts with "Use when ..."
- [ ] Total file ≤ 100,000 chars (aim for 8-15k)
- [ ] Structure: `# Title` → `## Overview` → `## When to Use` → body → `## Common Pitfalls` → `## Verification Checklist`
- [ ] Session-review updates were applied to a currently-loaded or class-level umbrella skill before considering a new narrow skill
- [ ] If the work resumed after interruption/context compression/tool-call limit, outstanding verification, generated-artifact cleanup, todo updates, and plan closure/archive were completed before final report
- [ ] User corrections were embedded in the governing SKILL.md body as reusable task behavior, not only in memory
- [ ] Concrete session-specific details, if kept, live in `references/`/`archive/` with a one-line pointer from SKILL.md
- [ ] `related_skills` references resolve in-repo (or are explicitly OK to be user-local)
- [ ] Python/script validation did not leave `scripts/__pycache__/*.pyc` or other generated binary artifacts inside the skill directory
- [ ] `git add skills/<category>/<name>/ && git commit` completed on the intended branch
