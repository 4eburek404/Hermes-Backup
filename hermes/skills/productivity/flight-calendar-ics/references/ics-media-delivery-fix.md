# .ics Media Delivery Fix (v0.16.0)

## Symptom

`send_message(action='send', message='MEDIA:/home/user/flights.ics', target='telegram:…')` delivers the path as literal text ("MEDIA:/home/user/flights.ics") instead of a native file attachment on Telegram.

## Root Cause

`gateway/platforms/base.py` defines `MEDIA_DELIVERY_EXTS` — the tuple of file extensions that `extract_media()` recognises as deliverable media. The `MEDIA_TAG_CLEANUP_RE` regex is built from this tuple. If `.ics` is absent, the regex never matches `MEDIA:*.ics`, so the tag is not extracted and the entire string is sent as plain text.

In v0.16.0 (commit 4e6d05c6), `.ics` and `.ical` are NOT in `MEDIA_DELIVERY_EXTS`.

## Fix

Add `".ics", ".ical"` to `MEDIA_DELIVERY_EXTS` in `gateway/platforms/base.py` (~line 1199):

```python
    # Calendar
    ".ics", ".ical",
    # Archives
    ".zip", ...
```

Then clear Python bytecode cache and restart the gateway:
```bash
find <src_dir> -name "*.pyc" -path "*/gateway/platforms/*" -delete
find <src_dir> -name "__pycache__" -path "*/gateway/platforms/*" -exec rm -rf {} +
hermes gateway restart
```

**Why cache cleanup is required:** `send_message_tool.py` uses a lazy import (`from gateway.platforms.base import BasePlatformAdapter` at line 359) inside its function body. Python's `sys.modules` cache and `__pycache__/*.pyc` files can serve stale bytecode even after the source `.py` is patched. Without cache cleanup, the gateway process may still use the old `MEDIA_DELIVERY_EXTS` (without `.ics`) after restart. Verify with:

```bash
python3 -c "from gateway.platforms.base import MEDIA_DELIVERY_EXTS; print('.ics' in MEDIA_DELIVERY_EXTS)"
```

## Verification Bypass: `hermes send` CLI

If the tool call via gateway still delivers text after patching, use the CLI as a verification bypass:

```bash
hermes send --to "telegram:<chat_id>:<thread_id>" "MEDIA:/home/user/flights.ics"
```

The CLI runs in a fresh process with no stale `sys.modules` cache, so it always uses the current source. If the CLI succeeds but the tool call fails, the in-process cache is stale — restart gateway after cache cleanup.

## Path Validation: Non-Strict Mode

`validate_media_delivery_path()` in `base.py` (line 1028) has two modes:

- **Non-strict (default):** Accepts any existing regular file NOT under the denylist (`/etc`, `/proc`, `~/.ssh`, `~/.aws`, etc.). `/home/konstantin/flights.ics` passes.
- **Strict (opt-in via `gateway.strict` in config.yaml or `HERMES_MEDIA_DELIVERY_STRICT=1`):** File must be under a Hermes cache dir, operator-allowlisted root (`HERMES_MEDIA_ALLOW_DIRS`), or freshly produced within the recency window (600s default).

So in the default (non-strict) configuration, files under `$HOME` are accepted — the path validation is NOT the blocker for `.ics`.

## Related GitHub Issues

- **#44523** — Desktop remote mode: chat file links are silent dead ends (`file://` fallback in remote mode)
- **#44538 / PR #44538** — Fix: remote-mode chat file links download via fs bridge (open, not merged as of v0.16.0)
- **#44748** — Remote Desktop inline MEDIA audio/video renders but does not play

## Additional Context: Remote Desktop .ics Delivery

Even with `.ics` in `MEDIA_DELIVERY_EXTS`, Hermes Desktop in remote-gateway mode (Mac client → VPS backend) cannot deliver `.ics` files inline. The `MediaAttachment` component falls back to `file://` URLs which point to the VPS filesystem, not the Mac. This is the #44523 bug. Workaround: deliver via Telegram (which works) or SCP the file to the Mac.

## Diagnostic Chain

1. `send_message` calls `BasePlatformAdapter.extract_media(message)` (lazy import, line 359 of send_message_tool.py)
2. `extract_media` uses `MEDIA_TAG_CLEANUP_RE` to find MEDIA: tags
3. `MEDIA_TAG_CLEANUP_RE` is built from `MEDIA_DELIVERY_EXTS` extensions
4. `.ics` not in extensions → regex doesn't match → tag not extracted → path sent as text
5. `filter_media_delivery_paths` calls `validate_media_delivery_path` — in non-strict mode, most `$HOME` paths pass
6. `_send_telegram` routes `.ics` to `bot.send_document()` (line 1108) — but only if `media_files` is non-empty
7. Fix: add `.ics` to `MEDIA_DELIVERY_EXTS` → regex matches → `extract_media` returns path → `_send_telegram` routes to `bot.send_document()`
8. **Stale cache gotcha:** after patching, `__pycache__/*.pyc` and `sys.modules` may serve old code. Clear cache + restart to force fresh import.