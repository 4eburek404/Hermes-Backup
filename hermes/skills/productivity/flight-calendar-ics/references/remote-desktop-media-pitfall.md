# Remote Desktop MEDIA Delivery Pitfall

Diagnosed 2026-06-14. When the agent runs on a remote backend (VPS) and the user
connects via Hermes Desktop (Electron on Mac/PC), non-image `MEDIA:` files
(e.g. `.ics`, `.pdf`, `.txt`) in chat are **silent dead ends** — the user sees
a link, clicks it, nothing happens.

## Root Cause

Desktop's `MediaAttachment` component (`markdown-text.tsx`) classifies media by
extension. Files not matching image/audio/video extensions fall through to a
fallback that opens `mediaExternalUrl(path)` → `file://<absolute-path>`. In
remote-gateway mode that `file://` URL points to the **backend** filesystem, not
the client's local disk. The Electron shell silently fails to open it.

Images work because `mediaSrc()` routes them through `gatewayMediaDataUrl()`
which calls `GET /api/media` on the gateway. Audio/video streams via the
`hermes-media://` custom protocol. The file-kind fallback has **no remote
path**.

## Known GitHub Issues

- **#44523** — "Desktop remote mode: chat file links are silent dead ends"
- **#44748** — "Remote Desktop inline MEDIA audio/video renders but does not play"
- **PR #44538** — Fix (routes file-kind fallback through `/api/fs/read-data-url`);
  status: **Open, not merged** as of 2026-06-14.

## Workarounds

1. **Deliver via Telegram** — `send_message` with `MEDIA:` works because
   Telegram uploads the file from the backend. The .ics reaches the user as
   a native Telegram document attachment.
2. **SCP** — User runs `scp <host>:<path> ~/` to copy the file from the
   backend to their local machine.
3. **Cherry-pick PR #44538** into a local Desktop build if the user builds
   from source.

## Agent Guidance

When running on a remote backend and the user asks to "send the file here"
(meaning Desktop chat), **Telegram delivery is the only working path**.
Do NOT attempt to deliver .ics or other non-image files inline in Desktop
chat — they will appear as dead links. Use `send_message` to a Telegram
target instead, and tell the user the Desktop limitation explicitly.