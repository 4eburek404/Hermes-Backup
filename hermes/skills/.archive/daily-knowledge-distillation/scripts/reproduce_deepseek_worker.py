#!/usr/bin/env python3
"""Reproduce DeepSeek as the daily-distillation worker.

Run from a Hermes host with Ollama API available. This intentionally uses HTTP API,
not `ollama run`, because cloud model CLI pulls can fill disk.
"""
import asyncio
import json
import pathlib
import time

import aiohttp

WORKER_PATH = pathlib.Path("/home/konstantin/.hermes/skills/.archive/daily-knowledge-distillation/scripts/distillation_worker.py")
DEFAULT_SNIPPET_SOURCE = pathlib.Path("/home/konstantin/.hermes/cron/output/62e7a25f4e15/2026-05-01_18-15-04.md")

ns = {}
exec(WORKER_PATH.read_text(encoding="utf-8"), ns)

async def main() -> None:
    if DEFAULT_SNIPPET_SOURCE.exists():
        snippets = DEFAULT_SNIPPET_SOURCE.read_text(encoding="utf-8", errors="replace")[:12000]
    else:
        snippets = "No cron output file found; replace this with a 8k-12k session snippet packet before trusting benchmark results."

    body = {
        "model": "deepseek-v4-pro:cloud",
        "messages": [
            {"role": "system", "content": ns["WORKER_SYSTEM_PROMPT"]},
            {"role": "user", "content": "Session snippets:\n" + snippets},
        ],
        "max_tokens": 3000,
        "temperature": 0.1,
        "response_format": ns["RESPONSE_FORMAT"],
    }

    start = time.monotonic()
    async with aiohttp.ClientSession() as session:
        async with session.post(ns["OLLAMA_BASE_URL"], json=body, timeout=aiohttp.ClientTimeout(total=200)) as resp:
            raw = await resp.text()
            elapsed = round(time.monotonic() - start, 1)

    result = {"http_status": resp.status, "elapsed": elapsed, "raw_chars": len(raw)}
    try:
        data = json.loads(raw)
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
        parsed = ns["parse_json_response"](content)
        result.update({
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage"),
            "content_chars": len(content),
            "reasoning_chars": len(reasoning),
            "parse_status": "ok" if parsed is not None else "parse_error",
            "content_preview": content[:500],
        })
    except Exception as exc:
        result.update({"decode_error": str(exc), "raw_preview": raw[:500]})

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
