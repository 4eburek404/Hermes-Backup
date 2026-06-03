# Auto Route Dispatch

Use this reference when changing the CLI/skill contract from agent-selected routes (`build aeroflot`) to true one-command dispatch (`build auto --url-file ...`).

## Goal

The happy path should let the agent run one CLI command and then deliver the returned `.ics` path. The CLI should own route selection, artifact naming, private bundle creation, and verification.

```bash
python scripts/flight_calendar_ics.py --json build auto --url-file /private/source-url.txt
```

`doctor` remains a machine-readable runbook for ambiguity, failures, and explicit diagnostics — not a required step for obvious generation or routine evaluation.

## Route inference boundary

Inference must be local and deterministic before any carrier network fetch. Do not probe carriers sequentially until one works.

Inputs:
- `--input`: canonical itinerary JSON -> `make` when schema/source shape matches.
- `--url-file` / `--url`: parse privately; never echo full URL.
- explicit credential args: field-set matching can infer route when unambiguous.

Output evidence must be safe: route, confidence, host category, and field names only. Never include full URLs, PNR keys, locators, passenger names, access keys, ticket/payment/contact data, or generated booking deep-links.

## Host-first deterministic dispatch

Do not use global score racing. The cheap and safe decision order is:

1. Explicit non-auto route: bypass inference and validate that selected route only.
2. Canonical itinerary JSON (`--input`): route `make`.
3. Known carrier host: lock the carrier namespace before looking at fields.
4. No known host: accept only unique hard signatures; generic overlaps return ambiguity.
5. Insufficient/ambiguous/unknown input: return a safe `ok=false` envelope before any carrier network fetch.

Known-host rule: if a URL contains `utair.ru`, field names may prove or disprove Utair sufficiency, but they must never dispatch Ural. Likewise `uralairlines.ru` must never dispatch Utair. Host-only is not enough to fetch; return `route_input_insufficient` if required route-specific credentials are absent.

No-host rule: `pnr + lastName` is generic and must return `route_ambiguous` with safe candidates such as `["ural", "utair"]`; `rloc + last_name`, `pnrNumber + surname`, Aeroflot `pnrKey + pnrLocator`, and Red Wings `#/find/...` may be unique hard signatures when no known host is present.

Tracking wrappers: unwrap URL-valued query params locally. If exactly one known carrier host is found, use it. If multiple different known carrier hosts are found, return `route_ambiguous` with safe candidates.

## Carrier fingerprints

### Aeroflot

Hard signals:
- host contains `aeroflot.ru`; and
- query or SPA fragment contains `pnrKey` + `pnrLocator`, or `pnr_key` + `pnr_locator`; or
- explicit `--pnr-key` + `--pnr-locator`.

### Ural Airlines

Hard signals:
- host or redirect target contains `uralairlines.ru` / `service.uralairlines.ru`; and
- query contains `pnr`/`pnrNumber` plus `lastName`/`surname`.

Also handle tracking wrappers where query `u=`/`url=` points to the service domain.

### Utair

Hard signals:
- host contains `utair.ru`; and
- query contains `rloc`/`RLOC`/`pnr` plus `last_name`/`lastName`/`surname`; or
- explicit `--rloc` + `--last-name`.

### Red Wings

Hard signals:
- direct Websky/Red Wings find link shaped `#/find/<PNR>/<ACCESS_KEY>/Submit`; or
- explicit `--pnr` + `--access-key`.

Anti-path: `#/booking/<ORDER_ID>/order` is insufficient and must return a controlled `route_input_insufficient` error asking for the direct find link. Do not infer access keys from surname, PNR, ticket, or order-page IDs.

## Envelope shape

Successful auto dispatch should expose only safe detection metadata:

```json
{
  "ok": true,
  "command": "build",
  "data": {
    "route": "aeroflot",
    "route_detection": {
      "mode": "auto",
      "route": "aeroflot",
      "confidence": 1.0,
      "evidence": ["host:aeroflot.ru", "query_field:pnrKey", "query_field:pnrLocator"]
    },
    "verification": {"ok": true}
  }
}
```

## Agent behavior after `build auto`

The agent should verify only envelope booleans/paths/modes and then deliver `MEDIA:/absolute/path/flights.ics`. Do not read source files, carrier references, CLI source, or generated `.ics` content on a successful happy path.
