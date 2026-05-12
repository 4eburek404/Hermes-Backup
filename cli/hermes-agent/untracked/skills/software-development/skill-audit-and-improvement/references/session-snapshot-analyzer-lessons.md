# Session-snapshot analyzer lessons

Use this as a compact knowledge bank for read-only analyzers that summarize Hermes sessions or system prompts.

## Provenance first

Before trusting a transcript summary or earlier note, re-check live state:

```bash
pwd
git status --short --branch --untracked-files=all
git diff --stat
git diff --name-only
```

If the task is read-only analysis, verify the actual working tree and generated outputs before concluding that the baseline is unchanged.

## Scope discipline

For session-overhead analyzers:

- read only `session_*.json` from the selected sessions directory;
- do not widen scope to `jsonl`, `state.db`, or `request_dump` unless the task explicitly asks for it;
- extract only the fields the report needs, and treat everything else as out-of-scope.

## Parser pitfall

When splitting `system_prompt` content into sections, validate against the real fixture text, not just the intended marker list.

A regex that looks safe in code can still miss a heading when punctuation is involved. For example, `## Skills (mandatory)` should be tested literally from the fixture; avoid relying on a trailing word-boundary assumption to capture it.

## Report shape that proved useful

For this class of analyzer, keep the output split into:

- markdown summary for humans;
- JSON for downstream consumption;
- per-section totals for the system prompt;
- top sessions ranked by estimated prompt tokens.

That keeps the tool useful for both baseline review and future regression checks.