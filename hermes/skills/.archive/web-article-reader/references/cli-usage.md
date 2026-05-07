# Web article reader CLI usage

Executable examples for the local `article` CLI. Kept outside `SKILL.md` so the skill core remains workflow/instructions only.

```bash
# Human-readable Markdown (default)
article read '<URL>'

# JSON envelope for programmatic parsing
article --json read '<URL>'

# Bounded extraction for summarization
article summary-input '<URL>' --max-chars 12000

# Raw read-only request (inspect what server returned)
article --json request get '<URL>' --preview-chars 4000

# Quick reachability check before full extraction
article --json doctor --check-url '<URL>'
```
