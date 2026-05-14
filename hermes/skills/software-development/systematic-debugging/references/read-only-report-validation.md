# Read-only report validation checklist

Use this when debugging or extending a read-only analyzer / report generator.

## What to verify
- Re-check live repo state before trusting a transcript or summary:
  - `git status --short --branch --untracked-files=all`
  - `git diff --stat`
  - `git diff --name-only`
- Run the targeted test file first, then the report CLI against:
  - a small deterministic fixture set
  - the live data path, if the task explicitly requires it
- Confirm both output formats, not just one:
  - markdown contains the new section header
  - JSON contains the new top-level keys / fields

## Read-only analyzer pitfall
- When the task says "extend the analyzer" and the source of truth is session snapshots, only read the new field(s) needed for the feature.
- Avoid broadening the parser to unrelated payloads unless the task explicitly asks for it.
- Do not read live runtime state, transcripts, or database files if the analyzer is intended to stay read-only.

## Tool-schema overhead pattern used in one session
- For each tool object, normalize the tool name with this fallback chain:
  - `tool["name"]`
  - `tool["function"]["name"]`
  - `tool["tool_name"]`
  - `<unknown>`
- Estimate per-tool schema overhead as:
  - `ceil(len(json.dumps(tool, ensure_ascii=False, sort_keys=True)) / 4)`
- Report both totals and rankings:
  - total tool count
  - total estimated schema tokens
  - average per tool
  - top N largest tools
  - top sessions by tool-schema tokens
