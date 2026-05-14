# hh-ru CLI

Composable command-line wrapper for the public `https://api.hh.ru` API.

The CLI is designed for agent workflows: stable JSON envelopes, explicit
discovery/read commands, dry-run request inspection, and no hidden writes.

## Install

```bash
make install-local
command -v hh-ru
hh-ru --help
hh-ru --json doctor
```

This project uses only the Python standard library.

## Auth And Config

Auth precedence:

1. `--api-key` flag for one-off tests only
2. `HH_API_TOKEN`
3. `HH_RU_TOKEN`
4. `~/.hh-ru/config.json`

Initialize config:

```bash
hh-ru init
hh-ru init --user-agent 'hh-ru-cli/0.1 (contact: you@example.com)'
```

Store a token only if env vars are inconvenient:

```bash
hh-ru init --token '...'
```

`doctor` does not call the API unless `--check-api` is passed.

## JSON Policy

With `--json`, stdout is always an envelope:

```json
{
  "ok": true,
  "command": "vacancies search",
  "data": {}
}
```

Errors are emitted to stderr:

```json
{
  "ok": false,
  "error": {
    "type": "api_error",
    "message": "hh.ru API returned HTTP 403",
    "status": 403,
    "details": {}
  }
}
```

Tokens are never printed; `Authorization` is redacted in dry-run output.

## Common Commands

Offline config check:

```bash
hh-ru --json doctor
```

Inspect a request without calling hh.ru:

```bash
hh-ru --json vacancies search Python --area 1 --per-page 10 --dry-run
```

Search vacancies:

```bash
hh-ru --json vacancies search Python --area 1 --schedule remote --only-with-salary
```

Read vacancy detail:

```bash
hh-ru --json vacancies get 12345678
```

Find area IDs:

```bash
hh-ru --json areas resolve --name Ekaterinburg
hh-ru --json areas tree --id 113
```

Autocomplete:

```bash
hh-ru --json suggest areas kazan
hh-ru --json suggest professional-roles analyst
```

Reference data:

```bash
hh-ru --json roles
hh-ru --json dictionaries
hh-ru --json industries
hh-ru --json salary-dicts areas
```

Employer:

```bash
hh-ru --json employers get 3529
hh-ru --json employers vacancies 3529 --per-page 10
```

Raw read-only request:

```bash
hh-ru --json request get /vacancies --param text=Python --param area=1 --param per_page=5
```

## Notes

- hh.ru rejects unset or blacklisted `User-Agent` values.
- Unauthenticated `/vacancies` requests can hit severe rate limits.
- Use `/areas/113` or `areas resolve` before trusting city IDs.
- Salary statistics area IDs are not the same as vacancy area IDs.
- `request get` is read-only. Raw live POST/PUT/PATCH/DELETE are intentionally
  not exposed.

