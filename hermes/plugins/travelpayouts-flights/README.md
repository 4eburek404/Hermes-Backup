# travelpayouts-flights Hermes plugin

Self-contained Hermes user-plugin for informational flight search through the
Travelpayouts GraphQL Data API.

- Tool: `travelpayouts_flight_search`
- Secret: `TRAVELPAYOUTS_TOKEN` in `~/.hermes/.env`
- Optional marker: `TRAVELPAYOUTS_MARKER` in `~/.hermes/.env`
- Auth: `X-Access-Token` header only; never URL query `token=`
- Search/advisory only: no booking, no purchase

Enable only after explicit user decision:

```bash
hermes plugins enable travelpayouts-flights
# then restart gateway/new session
```

Prices are cached upstream and must be rechecked before purchase.
