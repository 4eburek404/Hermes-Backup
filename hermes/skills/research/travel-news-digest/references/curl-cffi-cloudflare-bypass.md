# curl_cffi — Cloudflare/Akamai TLS-Fingerprint Bypass

`curl_cffi` (v0.15.0, installed in Hermes venv) makes HTTP requests with a real browser TLS fingerprint (JA3/JA4). Cloudflare/Akamai cannot distinguish it from Safari/Chrome. Standard `curl` and `httpx` are fingerprinted as bots and get 403.

## When to use

- Site returns 403 to `curl`/`httpx` but works in browser → Cloudflare/Akamai protection
- archive.org fallback is too slow or returns stale content
- Need live, real-time content from a protected site

## Basic usage

```python
from curl_cffi import requests as cffi_requests

# impersonate='safari' — BEST for Cloudflare (chrome often still 403)
r = cffi_requests.get("https://www.travelweekly.com/Travel-News", impersonate="safari", timeout=15)
print(r.status_code, len(r.text))  # 200, 91829
```

## impersonate values (tested 2026-08-12)

| Value | Cloudflare bypass | Notes |
|-------|-------------------|-------|
| `safari` | ✅ Best | Works on most Cloudflare-protected sites |
| `chrome` | ⚠️ Inconsistent | Sometimes 200, sometimes 403 on same site |
| `safari15_5` | ⚠️ Site-dependent | Some sites 200, some 403 |
| `firefox` | ❌ Often 403 | |
| `safari17` | ❌ Not supported | |

**Always use `impersonate='safari'` first.** If 403, try `safari15_5` as fallback.

## Sites unlocked by curl_cffi+safari

| Site | curl status | curl_cffi safari |
|------|------------|-----------------|
| Travel Weekly | 403 | ✅ 200 |
| BTN (Business Travel News) | 403 | ✅ 200 |
| PhocusWire | 403 | ✅ 200 |
| Hotel News Now (Akamai) | 403 | ✅ 200 |
| Hotel Management | 403 | ✅ 200 |
| Travel Daily News | 403 | ✅ 200 |
| Travel Pulse | 403 | ✅ 200 |
| LoyaltyLobby | 403 | ✅ 200 |

## Sites NOT unlocked

| Site | Issue | Workaround |
|------|-------|------------|
| Hospitality Net | 403 even with safari | archive.org |
| TTG Media | 403 even with safari | archive.org |
| TASS | 200 but anti-bot stub (servicepipe.tech) | browser_navigate |
| S7 Airlines | 200 but anti-bot stub | browser_navigate |
| РБК | Connection timeout | browser_navigate |

## Retry pattern

curl_cffi+safari is **unstable** — some sites return 403 intermittently. Use 3 retries with exponential backoff:

```python
RETRY_DELAYS = [1, 2, 4]

for attempt in range(3):
    try:
        r = cffi_requests.get(url, impersonate="safari", timeout=15)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    if attempt < 2:
        time.sleep(RETRY_DELAYS[attempt])
return None
```

## vs archive.org

| | curl_cffi+safari | archive.org |
|--|-------------------|-------------|
| Speed | ~1s per site | ~3-5s per site |
| Freshness | Live content | Cached (days/weeks old) |
| Reliability | ~80% (intermittent 403) | ~90% (if archived) |

**Prefer curl_cffi+safari** for live content. Fall back to archive.org only when curl_cffi also returns 403.