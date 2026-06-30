# Provider Failover and Output Extraction

When FLI MCP is unreachable or degraded, force KupiBilet-only search and extract full results programmatically.

## FLI down — force KupiBilet only

Add to the request JSON:

```json
{
  "provider_policy": "kupibilet",
  "route_options": {
    "use_gateway_discovery_for_fallback_hubs": true
  }
}
```

`provider_policy: "kupibilet"` prevents all segment probes from dispatching to FLI. `use_gateway_discovery_for_fallback_hubs: true` disables the hardcoded IST→FLI imperative in `RoutePlanBuilder`, so IST and other bridge gateways appear through gateway discovery data instead of the legacy `ist_direct` / `ist_shared_destination` route families that route to FLI by default.

### Symptom

CLI output contains:
- `failed_controls` with `FLI MCP request failed: URLError: <urlopen error [WinError 10061]>`
- `answer_readiness: "answerable_with_caveats"` with `blocking_evidence: ["failed_controls", "provider_failures"]`
- `ranked_candidates: []` despite `primary_offer_results[0].top_offers` having offers

### After fix

- `answer_readiness: "answerable"` or `"answerable_with_caveats"`
- `blocking_evidence: []` or `["not_executed_controls"]` (budget-limited, not provider-failed)
- `primary_offer_results[0].top_offers` still populated by KupiBilet aggregate

## Hub-list strategy for controlled 1-stop search

When the default `ru-priority` strategy doesn't find 1-stop options, switch to explicit hub-list:

```json
{
  "route_options": {
    "routing_strategy": "hub-list",
    "hubs": ["IST", "SVO", "AYT", "EVN", "TBS", "GYD", "CDG", "MUC", "MOW"],
    "max_connections": 1,
    "tier2_max_connections": 0,
    "coverage_mode": "full",
    "coverage_control_limit": 30
  },
  "evidence": {
    "outbound_second_leg_day_offsets": [0, 1],
    "no_live_cache": true,
    "timeout": 90,
    "max_segment_searches": 50
  }
}
```

`hub-list` with explicit `hubs` tests each hub's origin→hub and hub→destination legs independently through KupiBilet. `outbound_second_leg_day_offsets: [0, 1]` tells the CLI to also search hub→destination on the next day.

## Cross-day assembly limitation

The assembler may find both legs (e.g. TLS→IST on July 10, IST→SVX on July 11) but fail to pair them into a ranked candidate. Symptoms:

- `segment_searches` shows `offer_count > 0` for both legs
- `ranked_candidates: []`
- `rejected_pairs` contains only same-day pairs with `invalid_time_order`
- `stop_policy_diagnostics.candidate_generation_mode: "none"`

In this case, extract individual leg prices from `rejected_pairs[].first_offer` and `second_offer`, or from `evidence.segment_searches`, and manually report:

> TK1806: TLS 18:50 → IST 23:25 (July 10) — price from first_offer.price
> IST→SVX: July 11 — price from segment_searches/probe-005 offer detail
> Total: sum of leg prices (separate tickets, unverified connection)

## Manual leg-by-leg assembly via `diagnose kb-search`

When the user specifies an exact routing (e.g. "TLS→CDG→IST→SVX") and the main `search` command doesn't assemble it, use `diagnose kb-search` to probe each leg independently, then manually combine the offers. This bypasses the CLI's assembler entirely and is the most reliable way to answer "find flights via X→Y→Z".

### Steps

1. **Probe each leg** with `diagnose kb-search ORIGIN DEST --depart-date YYYY-MM-DD --limit 50`:

```python
def run_kb_search(origin, dest, date, limit=50):
    cmd = (
        f"python3 -m flights_cli --json diagnose kb-search {origin} {dest} "
        f"--depart-date {date} --limit {limit}"
    ).split()
    result = subprocess.run(cmd, cwd=cli_dir, capture_output=True, text=True, timeout=60,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return json.loads(result.stdout)
```

2. **Extract offers** from `data.offers[]` for each leg. Key fields: `price` (int), `departure_at`, `arrival_at`, `flight_numbers`, `number_of_changes`, `segments[]`.

3. **Search next-day legs** when the inbound leg arrives too late for same-day connections. E.g. if CDG→IST arrives 11 July 03:30, search IST→SVX on both 10 July and 11 July.

4. **Filter and assemble** in Python:
   - Parse `departure_at` / `arrival_at` as timezone-aware `datetime` objects with `datetime.fromisoformat()`.
   - Apply user constraints (e.g. departure after 14:00).
   - Enforce minimum connection time (≥90 min) and maximum (≤24h) between legs.
   - **Check terminals** at connection hubs: if `arrival_terminal` of leg N differs from `departure_terminal` of leg N+1, increase minimum connection time to ≥3h (inter-terminal transfer). A 2h20m connection at CDG with different terminals is not safe.
   - Sum prices across legs for total cost.
   - Sort by total price.

5. **Present to user** with each leg as a separate row, connection times, and total price. Label as separate tickets (not single PNR) unless proven otherwise.

### Pitfalls

- **KupiBilet API coverage gap for foreign carriers**: The API can be missing entire flights that exist on the KupiBilet website and other aggregators. This is not data drift (wrong times) — the flight is simply absent from the API response. Confirmed case: AF7405 TLS→CDG 14:30 on 2026-07-10 — exists on the website, absent (or showing 10:30) in the API. When the user reports a flight the CLI didn't find, trust the user's observation; do not insist on API data over user-observed evidence. See `references/source-boundaries.md` → "KupiBilet coverage gap for foreign carriers".
- **Self-transfer legs appear as "0 stops" in `number_of_changes`**: A TLS→NCE→CDG itinerary shows `number_of_changes: 0` because it's one KupiBilet offer, but it has 2 segments in `segments[]`. Check `len(segments)` for actual segment count, not `number_of_changes`.
- **Airport mismatch**: Some CDG→IST results actually route via BSL, ZRH, OTP, BEG etc. Filter by exact airports if the user specified them.
- **IST vs SAW**: Istanbul has two airports — IST (new) and SAW (Sabiha Gökçen). `diagnose kb-search CDG IST` returns both IST and SAW results. Filter `segments[-1]["destination"]` if exact airport matters.
- **Price is int, not dict**: In `diagnose kb-search` output, `price` is a plain integer. In `search` output, it's also an int (not a dict as in older versions).
- **Raw API `flight_number` is None — use `number`/`transport_number`**: The KupiBilet raw `flights` map has no `flight_number` key. Flight number is in `number` (int) and `transport_number` (string). The CLI's `kupibilet_flight_number()` synthesizes `carrier + number` (e.g. `AF7405`). When inspecting raw API responses, search by `number` field, not `flight_number`.
- **API schedule drift vs website**: The API `departure_datetime` can differ from the KupiBilet website for the same flight/date. This is provider-side data drift, not a parser bug. See `references/source-boundaries.md` → "API vs website schedule discrepancy" and `references/debug-playbook.md` → "API vs website mismatch".

### Connection time validation

```python
from datetime import datetime

def parse_dt(s):
    return datetime.fromisoformat(s)

# Enforce: leg2 departure >= leg1 arrival + 90 min, <= 24h
conn_min = (dep2 - arr1).total_seconds() / 60
if conn_min < 90 or conn_min > 24 * 60:
    continue  # skip this pair
```

## Output extraction patterns

### Pattern 1: execute_code with subprocess

```python
import json, subprocess, os
home = os.path.expanduser("~")
hermes_home = os.environ.get("HERMES_HOME", os.path.join(home, ".hermes"))
cli_dir = os.path.join(hermes_home, "skills", "productivity", "flight-search", "cli")
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
cmd = ["python3", "-m", "flights_cli", "--json", "search", "--request", req_path]
proc = subprocess.run(cmd, cwd=cli_dir, capture_output=True, text=True, timeout=180, env=env)
data = json.loads(proc.stdout)

# Current structure (route_result):
primary = data["data"]["route_result"]["live_search"]["primary_offer_results"][0]
offers = primary["top_offers"]

# Fallback (flat agent_report structure):
# primary = data["data"]["agent_report"]["evidence"]["primary_offer_results"][0]
# offers = primary["top_offers"]
```

**Windows note:** on some Windows hosts `python3` is not found in bash; use `py -3` or `python` only after confirming it resolves to Python 3.11+.

### Pattern 2: background terminal + file

When `execute_code` or foreground `terminal` times out (CLI can take 60-120s with many hubs and no cache), run in background:

```bash
cd "$HERMES_HOME/skills/productivity/flight-search/cli"
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request "$HOME/req.json" > "$HOME/result.json" 2>&1
```

Then parse the result file with `read_file` (offset/limit for specific sections) or `search_files` (regex for specific fields like `"connection_count": 1`).

### Key JSON paths

**Current `route_result` structure** (observed 2026-06):

| Path | Content |
|------|---------|
| `data.route_result.live_search.primary_offer_results[0].top_offers` | Ranked offers: `price` (int), `segments[]`, `carriers`, `change_count`, `stop_tier`, `duration_min` |
| `data.route_result.live_search.segment_searches` | Per-leg: origin, destination, date, offer_count, status, provider, cache info |
| `data.route_result.live_search.offer_candidates` | Dict: `candidates` (list of journey objects), `coverage`, `rejected` |
| `data.route_result.candidates` / `.ranked_candidates` | Assembled candidates (may be `[]` even when `top_offers` has 10+ offers) |
| `data.route_result.rejected_pairs` | Pairs tried but rejected — shows `rejection_reason`, `first_offer`, `second_offer` |
| `data.route_result.live_search.decision_frontier.options` | All candidates including gateway-assembled |
| `data.route_result.live_search.gateway_leg_results` | Per-gateway leg probe results |
| `data.route_result.live_search.probe_ledger` | Provider probe audit trail |
| `data.route_result.agent_report.user_answer.rendered_text` | Canonical rendered answer (may say "Не нашёл" even when offers exist) |

**Segment shape inside `top_offers[]`:**

```json
{
  "price": 48520,
  "currency": "RUB",
  "change_count": 2,
  "duration_min": 535,
  "stop_tier": "T2_TWO_STOP",
  "carriers": ["3F", "EC", "W4"],
  "segments": [
    {
      "origin": "TLS", "destination": "MXP",
      "carrier": "EC", "flight_number": "U23820",
      "marketing_carrier": "U2", "operating_carrier": "EC",
      "departure_at": "2026-07-10T15:50:00+02:00",
      "arrival_at": "2026-07-10T17:15:00+02:00",
      "departure_terminal": null, "arrival_terminal": null
    }
  ]
}
```

**`diagnose kb-search` output shape** (different from `search`):

```json
{
  "data": {
    "offers": [
      {
        "price": 50976,
        "currency": "RUB",
        "number_of_changes": 0,
        "duration": "...",
        "departure_at": "2026-07-10T20:30:00+02:00",
        "arrival_at": "2026-07-10T22:00:00+02:00",
        "origin": "TLS", "destination": "CDG",
        "flight_numbers": ["AF7419"],
        "marketing_carriers": ["AF"],
        "operating_carriers": ["AF"],
        "segments": [...]
      }
    ]
  }
}
```

Key differences from `search`: `price` is a plain int (not dict), `number_of_changes` instead of `change_count`, top-level `departure_at`/`arrival_at` instead of per-segment only.

**Pitfall — `rendered_text` false negative:** The rendered text can say "Не нашёл пригодных вариантов" even when `primary_offer_results[0].top_offers` has 10+ offers with prices. This happens when the CLI's assembler/ranker doesn't promote offers to `candidates`/`ranked_candidates` (e.g. all offers are 2-stop `T2_TWO_STOP` and the stop-policy tier doesn't promote them). Always cross-check `top_offers` before reporting absence to the user.

**Pitfall — `offer_candidates` is a dict, not a list:** `data.route_result.live_search.offer_candidates` is a dict with keys `candidates`, `coverage`, `rejected`, `schema_version`. Slicing it as a list raises `TypeError: unhashable type: 'slice'`. Access `.get("candidates", [])` first.
