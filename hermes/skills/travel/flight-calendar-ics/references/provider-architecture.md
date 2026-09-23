# Provider Architecture

The executable routing contract is `specs/provider_routing_spec.py`.

The booking-URL runtime has three responsibilities:

- **Orchestration/router** — `scripts/flight_calendar/parser.py` accepts the
  original booking URL and asks `route_detection.py` which supported carrier
  owns that source. Routing is explicit. The router selects a provider; it does
  not turn the source into another URL.
- **Provider** — one module under `scripts/flight_calendar/carriers/` owns all
  source forms and protocol details specific to that carrier: direct links,
  carrier mail links, wrapper decoding, redirects, credential extraction,
  canonical booking URL construction, API/web requests, authentication,
  recovery/cache, response interpretation, and conversion to the common
  itinerary dictionary.
- **Shared transport** — `scripts/flight_calendar/carrier_http.py` owns generic
  HTTP mechanics: the concrete engine, browser-like headers, one-shot and
  session requests, timeout, retries/backoff, generic redirect mechanics,
  response decoding, HTTP/network failures, and redaction-safe transport
  errors. It does not decide which carrier a URL belongs to.

There is no source-normalization stage in the target flow.

## Booking URL flow

```text
raw user URL
    ↓
route_detection: which carrier owns this source?
    ↓
same raw URL, unchanged
    ↓
selected carrier adapter
    ↓
carrier-specific unwrap / redirect / parse / canonicalize / fetch
    ↓
common itinerary validation
    ↓
ICS
```

The router answers only **"which provider receives this source?"**.

The provider answers **"what does this carrier require us to do with this
source?"**.

## Router boundary

The router may use trusted, source-visible carrier evidence such as exact HTTPS
host/path combinations:

- `www.aeroflot.ru` → Aeroflot;
- `service.uralairlines.ru` → Ural Airlines;
- `www.utair.ru` and `click.mail.utair.io` → Utair;
- `flyredwings.com` → Red Wings;
- `myb.s7.ru` → S7 Airlines.

The router must:

1. Select a supported carrier from the original URL.
2. Reject unknown or untrusted source shapes with `route_unknown`.
3. Pass the original URL to the selected provider unchanged.
4. Perform no network requests.
5. Not extract booking credentials for provider use.
6. Not follow redirects, canonicalize URLs, or strip tracking parameters.

A wrapper whose own host does not identify the airline may require minimal
inspection solely to identify the carrier. The observed Ural
`tn-hgl.mckx.ru` form is such a case: its single `u` value contains a
destination URL. Routing may inspect that destination host/path to decide that
the provider is Ural Airlines, but it still passes the original
`tn-hgl.mckx.ru` URL unchanged to the Ural adapter.

This exception is routing, not normalization: the router learns **who owns the
source**, not **what replacement URL should be executed**.

## Provider boundary

A provider owns every supported source form for its carrier.

A provider should:

1. Validate that the routed source is one of its supported forms.
2. Resolve or unwrap carrier-specific mail links when required.
3. Extract and validate carrier-specific booking credentials.
4. Build a canonical booking URL when the carrier has one.
5. Construct carrier-specific endpoints, methods, headers, query/body, and
   authentication.
6. Execute carrier-specific multi-request protocols and recovery rules.
7. Interpret carrier response status/business fields and validate response
   shape.
8. Convert the accepted response to the common itinerary contract.
9. Keep carrier-specific cache/state when the protocol requires it.

Examples:

- **Aeroflot** — parses its direct booking URL and uses `pnr_locator` plus
  `pnr_key` for the PNR API.
- **Ural Airlines** — accepts either the direct
  `service.uralairlines.ru` booking URL or its supported mail wrapper. The
  adapter unwraps `u`, validates the direct destination, extracts PNR and
  surname, builds the canonical booking URL, and performs the Reservation
  protocol.
- **Utair** — accepts either direct `www.utair.ru/order-manage` or the opaque
  `click.mail.utair.io` mail link. The adapter performs the required redirect
  lookup for the opaque link, validates the resulting Utair booking URL,
  extracts locator and surname, canonicalizes it, then performs OAuth and the
  orders lookup.
- **Red Wings** — accepts the original email/manage
  `#/find/<PNR>/<ACCESS_KEY>/Submit` source and uses those credentials for
  `FindOrder`. A browser may later replace the fragment with
  `#/booking/<ORDER_ID>/order`; that browser state is not a reason for the CLI
  to follow the browser transition.
- **S7 Airlines** — accepts its manage-order URL and owns the GET, possible
  auto-submit form POST, same-session behavior, and `__r_airs_data` extraction.

A provider should not import `curl_cffi`, `requests`, `httpx`, `urllib3`,
or another concrete HTTP engine. Use the shared transport functions. The
provider still decides when a redirect or session sequence is required because
that decision is carrier-specific.

## Shared transport boundary

Shared transport implements mechanics, not carrier policy.

For example, a generic `resolve_redirect_url(...)` helper may exist in
`carrier_http.py`. Calling it for an opaque Utair mail link is an Utair
provider decision. The shared transport does not know that
`click.mail.utair.io` belongs to Utair.

## Errors and privacy

Transport failures may expose only a caller-provided safe label, HTTP status or
content type, retry exhaustion, and exception class. Providers must not place
booking URLs, query credentials, PNRs, surnames, access keys, OAuth tokens, API
keys, raw private responses, or private paths in errors, logs, or CLI output.
Carrier business failures should use stable, redaction-safe messages.

An identified carrier with an insufficient carrier-specific source should fail
from that provider with an appropriate carrier/source error. An unknown source
should fail at routing with `route_unknown`.

## Executable specification

`specs/provider_routing_spec.py` protects the architecture boundary:

- supported direct URLs select their carrier;
- known carrier mail sources select their carrier before carrier-specific
  transformation;
- the original Ural wrapper reaches the Ural adapter unchanged;
- the original Utair mail-click URL reaches the Utair adapter before redirect
  resolution.

Carrier-specific specs then protect each provider's own source transformations
and protocol.

## Tests and fixtures

A provider needs:

- source-contract tests for all supported source forms and credentials;
- a provider protocol spec with sanitized fixtures that checks endpoint,
  method, required headers, request body/query shape, response validation, and
  conversion;
- recovery/cache tests when the carrier protocol has those behaviors;
- a redaction check through the public CLI boundary;
- a full URL-to-ICS process case when applicable.

Replace only unavoidable external I/O in deterministic tests. Keep routing,
provider source handling, response handling, itinerary validation, and
rendering real.

## Add-a-carrier checklist

- [ ] Confirm the trusted source host/path or other minimal source-visible
      evidence needed to select the carrier.
- [ ] Add that carrier selection to the router.
- [ ] Pass the original source unchanged to the provider.
- [ ] Put all carrier-specific direct/wrapper/redirect handling in the provider.
- [ ] Use shared transport mechanics without moving carrier policy into shared
      transport.
- [ ] Add sanitized source/protocol/conversion specs.
- [ ] Add recovery/cache and public redaction checks if applicable.
- [ ] Run `specs/provider_routing_spec.py`, targeted carrier specs, all
      standalone specs, the full pytest suite, and `git diff --check`.
