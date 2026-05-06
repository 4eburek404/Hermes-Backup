# article CLI

Fetch and extract clean article text as Markdown, text, or JSON.

The CLI replaces ad hoc `curl | python` article extraction with a reusable
command for agent workflows. It does not save anything to docs, memory, or
fact_store.

## Install

```bash
make install-local
command -v article
article --help
article --json doctor
```

This project uses only the Python standard library.

## JSON Policy

With `--json`, stdout is always an envelope:

```json
{
  "ok": true,
  "command": "read",
  "data": {}
}
```

Errors are emitted to stderr:

```json
{
  "ok": false,
  "error": {
    "type": "network_error",
    "message": "Network request failed",
    "status": null,
    "details": "..."
  }
}
```

Auth is not used. Sensitive headers such as cookies are redacted from raw
request metadata.

## Commands

Runtime check:

```bash
article --json doctor
article --json doctor --check-url https://example.com
```

Extract an article:

```bash
article read https://example.com/article
article --json read https://example.com/article
article read ./saved-page.html --format text
```

Force a container:

```bash
article --json read ./page.html --selector body
```

Prepare bounded input for summarization:

```bash
article summary-input https://example.com/article --max-chars 12000
article --json summary-input ./saved-page.html --max-chars 8000
```

Raw read-only escape hatch:

```bash
article --json request get https://example.com/article --preview-chars 2000
```

## Source Forms

Commands accept:

- `https://...` or `http://...`
- local file paths
- `file://...`
- `-` for stdin

## Notes

- Extraction tries `<article>`, then `<main>`, then `<body>`.
- Heavy JavaScript sites may return little useful content. Use the raw request
  preview to confirm what the server returned.
- Use `--json` for agent parsing; use default Markdown output for reading.
