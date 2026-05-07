# flight-skill-guard

Ensures the flight-search skill workflow is followed by blocking direct calls
to `travelpayouts_flight_search` until `skill_view('flight-search')` has been
called in the current session.

## Problem

LLM agents frequently call `travelpayouts_flight_search` directly, ignoring
the skill's instruction to use `flights_cli route live-assemble` first. This
produces unranked, unvalidated cached results instead of live-assembled route
intelligence with hub viability, connection validation, and risk scoring.

Prompt-only constraints ("Do not call X, use Y") achieve ~70-85% compliance
because the tool appears in the tool list and the model selects the "convenient"
option. This plugin achieves 95%+ compliance through runtime enforcement.

## How it works

1. **pre_tool_call hook**: When the model calls `travelpayouts_flight_search`,
   the hook returns `{"action": "block", "message": "..."}` with an actionable
   error telling the model to call `skill_view('flight-search')` first.

2. **post_tool_call hook**: When the model calls `skill_view('flight-search')`,
   the hook records that the skill is loaded for this session.

3. **After skill loaded**: Subsequent calls to `travelpayouts_flight_search`
   are allowed (for debug/validation fallback per the skill's instructions).

## Session scoping

The guard is per-session: the skill must be loaded each session. This ensures
the model sees the skill's instructions (which may change between sessions).

## Configuration

```yaml
# config.yaml (optional)
plugins:
  flight_skill_guard:
    enabled: true
    guarded_tools:
      - travelpayouts_flight_search
```

## Guarded tools

- `travelpayouts_flight_search` — cached Travelpayouts API prices

Extend via config to guard additional tools.