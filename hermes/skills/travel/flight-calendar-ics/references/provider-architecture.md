# Provider Architecture

This skill has three runtime layers:

- **Orchestration/router** — `scripts/flight_calendar/parser.py` accepts the
  compact CLI sources, reads the URL, asks `route_detection.py` for a trusted
  source fingerprint, dispatches the selected provider, then applies the
  common itinerary contract and ICS renderer. Routing is explicit today: a
  new provider adds one trusted fingerprint and one dispatch branch. There is
  no registry or plugin framework.
- **Provider** — one module under `scripts/flight_calendar/carriers/` owns a
  carrier's URL shape, credential aliases and validation, endpoints, headers,
  query/body, authentication, multi-request protocol, recovery/cache, response
  semantics, extraction, and conversion to the common itinerary dictionary.
- **Shared transport** — `scripts/flight_calendar/carrier_http.py` owns the
  `curl_cffi` engine, browser-impersonating headers, one-shot and session
  request mechanics, generic timeout, retries/backoff, redirect mechanics,
  response text/JSON decoding, generic HTTP/network failures, and
  redaction-safe transport errors.

## Provider boundary

A provider should:

1. Parse and validate its supported booking URL and credentials.
2. Construct the carrier-specific endpoint, method, headers, query, and body.
3. Keep carrier-specific authentication and request sequences, including
   refresh or recovery rules.
4. Interpret carrier response status/business fields and validate the response
   shape before conversion.
5. Map the accepted response to the common itinerary contract.
6. Keep carrier-specific cache/state in the provider when the carrier protocol
   requires it. Ural's deployment configuration cache, generated `X-Api-Key`,
   server-clock correction, and one-time stale-configuration refresh are such
   state and remain in `carriers/ural.py`.

A provider should not import `curl_cffi`, `requests`, `httpx`, `urllib3`, or
another concrete HTTP engine. It should not create a concrete `Session` or
call an engine's `.get()`, `.post()`, or `.request()` methods. Use
`carrier_http.request_raw`, `request_text`, or `request_json` for ordinary
requests. For a protocol that needs one session across multiple requests, use
`carrier_http.open_session()` and `carrier_http.request_session_raw()`; use
`carrier_http.response_text()` for the generic HTTP-status check. The provider
still chooses the request sequence and interprets the returned response.

Carrier-specific HTTP protocol remains provider responsibility even when it is
complex:

- Aeroflot's PNR payload and anti-bot HTML handling;
- Ural deployment discovery, generated API key, clock synchronization, and
  cached-auth recovery;
- Utair OAuth followed by the orders lookup, plus the allowlisted Utair
  mail-click redirect;
- Red Wings' GraphQL operation and access-key payload;
- S7's auto-submit form, same-session POST, and `__r_airs_data` extraction.

The S7 session is shared transport mechanics; the form parsing, POST decision,
embedded-payload extraction, and response semantics are S7 protocol.

## Errors and privacy

Transport failures may expose only a caller-provided safe label, HTTP status or
content type, retry exhaustion, and exception class. Providers must not place
booking URLs, query credentials, PNRs, surnames, access keys, OAuth tokens,
API keys, raw private responses, or private paths in errors, logs, or CLI
output. Carrier business failures should use stable, redaction-safe messages.

## Tests and fixtures

A provider needs:

- source-contract tests for trusted URL shape, credential presence, aliases,
  and invalid values;
- a provider protocol spec with sanitized fixtures that checks endpoint,
  method, required headers, request body/query shape, response validation, and
  conversion to a valid common itinerary;
- recovery/cache tests when the carrier protocol has those behaviors;
- a redaction check through the public CLI boundary;
- a minimal-output test and, when applicable, a full URL-to-ICS process case.

Replace only unavoidable external I/O in deterministic tests. Keep route
selection, provider parsing, response handling, itinerary validation, and
rendering real. Run standalone specs with the offline guard as well as the
skill's full pytest suite.

## Add-a-carrier checklist

- [ ] Confirm a trusted source host/path and add the router fingerprint.
- [ ] Add one provider module with URL parsing, protocol, response validation,
      and common-itinerary conversion.
- [ ] Call shared transport only; do not import or instantiate an HTTP engine.
- [ ] Add sanitized fixtures and provider source/protocol/conversion specs.
- [ ] Add recovery/cache and public redaction checks if applicable.
- [ ] Add the explicit parser dispatch branch and update the carrier reference.
- [ ] Run targeted tests, every standalone spec, the full skill suite, and
      `git diff --check`.
