# Dashboard Debugging and Performance

Notes on troubleshooting, optimizing, and interacting with the Hermes Dashboard.

## Authentication & API Access

The dashboard uses a session token generated at startup and injected into the HTML. To perform authenticated requests (e.g., from `curl` or a diagnostic script) without using the browser:

1. **Extract the token:**
   ```python
   import re, urllib.request
   html = urllib.request.urlopen("http://127.0.0.1:9119/").read().decode()
   token = re.search(r'window\.__HERMES_SESSION_TOKEN__\s*=\s*"([^"]+)"', html).group(1)
   ```

2. **Access endpoints:** Use the `X-Hermes-Session-Token` header or the `?token=` query parameter.
   ```bash
   curl -H "X-Hermes-Session-Token: <TOKEN>" http://127.0.0.1:9119/api/model/info
   ```

## Performance Optimization (GZip)

The dashboard serves a large (~1.2MB) JS bundle. In high-latency environments (e.g., Tailscale relays), transmission without compression feels slow.

**Fix:** Add `GZipMiddleware` to `hermes_cli/web_server.py`:
```python
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)
```
*Note: Ensure this is added AFTER CORSMiddleware.*

## Visual Debugging Fallback

If `vision_analyze` fails (e.g., model doesn't support images), use `pytesseract` for OCR:
1. Install: `sudo apt install tesseract-ocr-rus` and `pip install pytesseract`.
2. Script:
   ```python
   import pytesseract
   from PIL import Image
   text = pytesseract.image_to_string(Image.open('screenshot.jpg'), lang='rus+eng')
   ```

## Connectivity Checklist

- **Host Binding:** Use `--host 0.0.0.0 --insecure` to allow remote access (like iPhone/Mac via Tailscale).
- **Firewall:** Ensure the port (default `9119`) is open in UFW for the `tailscale0` interface.
- **Tailscale:** Verify `direct` vs `relay` connection via `tailscale status`. Relays significantly slow down the UI.
