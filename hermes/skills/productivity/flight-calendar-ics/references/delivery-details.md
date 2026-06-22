# Delivery Details: send_message tool for .ics

## How delivery works

The `flight-calendar-ics-delivery` Hermes plugin owns the automatic happy-path delivery: it observes `agent_handoff.ready=true`, sends `MEDIA:<path>` as a native file attachment, transforms the tool result to a delivered confirmation, and blocks later `.ics` read/edit attempts.

Manual `send_message` remains a fallback when that plugin is not installed or not enabled. The `send_message` tool sends `MEDIA:<path>` as a native file attachment through the in-process gateway.

## Known pitfalls

| Problem | Root cause | Fix |
|---|---|---|
| `.ics` arrives as literal text | `.ics` not in `MEDIA_DELIVERY_EXTS` in `gateway/platforms/base.py` | Add `".ics", ".ical"` to the tuple |
| Still text after patching | Stale `__pycache__/*.pyc` | Delete `__pycache__` under `gateway/platforms/`, restart gateway |
| Still text after restart | `sys.modules` import cache holds old definition | Gateway restart clears it; verify with `python3 -c "from gateway.platforms.base import MEDIA_DELIVERY_EXTS; print('.ics' in MEDIA_DELIVERY_EXTS)"` |

## Delivery target format

Always use numeric `telegram:<chat_id>:<thread_id>`. Bare `target="telegram"` delivers to the home channel, NOT the current DM topic. Use `send_message(action='list')` to discover the correct IDs.

## Remote Desktop limitation

When the agent runs on a remote VPS and the user connects via Hermes Desktop, non-image `MEDIA:` files (`.ics`, `.pdf`, `.txt`) appear as dead `file://` links — the path points to the backend, not the client. Deliver via Telegram instead.
