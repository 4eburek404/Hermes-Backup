#!/usr/bin/env python3
"""
Distillation Worker — 2-tier ensemble for daily knowledge distillation.

Orchestrator / cron entrypoint (OpenAI Codex gpt-5.5) runs this via execute_code:
  1. Gather recent sessions via session_search
  2. Call 2 worker models in parallel via HTTP to Ollama
  3. Merge + dedup + vote counting
  4. Return merged candidates for curator (delegate_task)

Usage from Hermes execute_code:
    from hermes_tools import session_search, terminal
    exec(open("/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/scripts/distillation_worker.py").read())
    # Then call: result = run_distillation(session_snippets)
"""

import asyncio
import json
import re
import time
import aiohttp

# ── Configuration ──────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1/chat/completions"

WORKER_MODELS = {
    "glm-5.1:cloud": {
        "label": "glm",
        "max_tokens": 3000,
        "timeout": 200,
    },
    "gemma4:31b-cloud": {
        "label": "gemma",
        "max_tokens": 3000,
        "timeout": 200,
    },
}

# IMPORTANT: json_schema strict mode does NOT work through Ollama Cloud.
# Use json_object + explicit enum values in the system prompt.
# See references/json-schema-benchmark.md for root cause analysis.
RESPONSE_FORMAT = {"type": "json_object"}

# Enum constraints — MUST be in system prompt for compliance
ENUM_CATEGORIES = ["infrastructure", "preference", "project", "tool", "general"]
ENUM_DURABILITY = ["high", "medium", "low"]
ENUM_DESTINATIONS = ["user-context.md", "infrastructure.md", "runbooks.md", "fact_store", "memory", "skip"]
ENUM_ACTIONS = ["add", "update", "remove", "skip"]
ENUM_EVIDENCE_TYPES = [
    "direct_user_instruction", "repeated_correction",
    "verified_infrastructure", "verified_tool_result",
    "session_summary", "model_inference", "agent_mistake_lesson",
]

WORKER_SYSTEM_PROMPT = """You are a knowledge distillation worker. Extract factual claims from session snippets.

Return a JSON object with exactly this structure:
{
  "candidates": [
    {
      "claim": "<factual statement in Russian. One thought per entry.>",
      "evidence_type": "<MUST be one of: direct_user_instruction, repeated_correction, verified_infrastructure, verified_tool_result, session_summary, model_inference, agent_mistake_lesson>",
      "durability": "<MUST be one of: high, medium, low>",
      "destination": "<MUST be one of: user-context.md, infrastructure.md, runbooks.md, fact_store, memory, skip>",
      "action": "<MUST be one of: add, update, remove, skip>",
      "reason": "<Why worth saving. In Russian.>"
    }
  ]
}

CRITICAL RULES:
- "evidence_type" MUST be exactly one of: direct_user_instruction, repeated_correction, verified_infrastructure, verified_tool_result, session_summary, model_inference, agent_mistake_lesson
- "durability" MUST be exactly one of: high, medium, low
- "destination" MUST be exactly one of: user-context.md, infrastructure.md, runbooks.md, fact_store, memory, skip
- "action" MUST be exactly one of: add, update, remove, skip
- Do NOT use numeric durability values (0.95, 1.0 etc). Use only: high, medium, low.
- Do NOT invent new destination names or evidence types.
- Extract facts, not session summaries. Each claim must be a declarative statement.
- Mark claims derived only from session summaries as evidence_type=session_summary unless the snippet explicitly says a current tool/API/config check verified it.
- Mark interpretations that combine multiple snippets without direct verification as evidence_type=model_inference and action=skip unless the candidate is merely a proposed follow-up.
- Do NOT infer external-system permissions from API scopes or successful read operations. A script using calendar.readonly proves only that the script read safely; it does not prove the Google Calendar service account ACL is read-only.
- For Google Calendar, keep these separate: API/OAuth scope (calendar.readonly/calendar), Calendar ACL/share role (reader/writer/owner), and whether an insert/update/delete operation was actually tested.
- Do NOT collapse "not tested" into "not enabled". If write was not attempted, say "write not tested"; do not claim "write disabled".
- Operational claims about permissions, ACLs, scopes, cron schedules, model pinning, credentials, and write capability require current verification by the curator before writing; workers should prefer action=skip or destination=skip when evidence is ambiguous.
- Skip raw logs, model outputs, temporary task progress, secrets, credentials."""

# ── JSON Parsing ──────────────────────────────────────────────────────────────

def parse_json_response(content: str) -> dict | None:
    """
    3-level fallback parser for model output.
    
    Handles:
    - Direct JSON: {"candidates": [...]}
    - Codeblock wrapped: ```json\n{...}\n```
    - Embedded JSON: some text {"candidates": [...]} more text
    """
    if not content or not content.strip():
        return None
    
    text = content.strip()
    
    # Level 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Level 2: strip codeblock fences
    if text.startswith("```"):
        try:
            # Remove first line (```json or ```)
            inner = text.split("\n", 1)[1] if "\n" in text else ""
            # Remove closing fence
            inner = inner.rsplit("```", 1)[0].strip()
            return json.loads(inner)
        except (json.JSONDecodeError, IndexError):
            pass
    
    # Level 3: find first { ... } block
    brace_start = text.find("{")
    if brace_start >= 0:
        # Find matching closing brace
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start:i+1])
                    except json.JSONDecodeError:
                        break
    
    return None


def validate_candidates(data: dict) -> list[dict]:
    """Extract and validate candidates from parsed JSON."""
    if not data or "candidates" not in data:
        return []
    
    candidates = data["candidates"]
    if not isinstance(candidates, list):
        return []
    
    valid = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        # Check required fields
        required = ["claim", "evidence_type", "durability", "destination", "action", "reason"]
        if not all(k in c for k in required):
            continue
        # Check enum compliance
        if c["evidence_type"] not in ENUM_EVIDENCE_TYPES:
            continue
        if c["durability"] not in ENUM_DURABILITY:
            continue
        if c["destination"] not in ENUM_DESTINATIONS:
            continue
        if c["action"] not in ENUM_ACTIONS:
            continue
        valid.append(c)
    
    return valid


# ── Worker Call ────────────────────────────────────────────────────────────────

async def call_worker(session: aiohttp.ClientSession, model: str, config: dict, snippets: str) -> dict:
    """Call a single worker model and return parsed candidates."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": WORKER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Session snippets:\n{snippets}"},
        ],
        "max_tokens": config["max_tokens"],
        "temperature": 0.1,
        "response_format": RESPONSE_FORMAT,
    }
    
    label = config["label"]
    start = time.monotonic()
    
    try:
        async with session.post(
            OLLAMA_BASE_URL,
            json=body,
            timeout=aiohttp.ClientTimeout(total=config["timeout"]),
        ) as resp:
            elapsed = round(time.monotonic() - start, 1)
            
            if resp.status != 200:
                error_text = await resp.text()
                return {
                    "label": label,
                    "model": model,
                    "status": "http_error",
                    "http_code": resp.status,
                    "elapsed": elapsed,
                    "candidates": [],
                    "error": error_text[:200],
                }
            
            data = await resp.json()
            choice = data["choices"][0]
            message = choice.get("message", {})
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
            completion_tokens = data.get("usage", {}).get("completion_tokens", "?")
            finish_reason = choice.get("finish_reason", "?")
            
            parsed = parse_json_response(content)
            if parsed is None:
                return {
                    "label": label,
                    "model": model,
                    "status": "parse_error",
                    "elapsed": elapsed,
                    "finish_reason": finish_reason,
                    "completion_tokens": completion_tokens,
                    "content_chars": len(content),
                    "reasoning_chars": len(reasoning),
                    "candidates": [],
                    "error": "worker returned non-parseable JSON content",
                    "content_preview": content[:300],
                }
            
            candidates = validate_candidates(parsed)
            raw_candidates = parsed.get("candidates", []) if isinstance(parsed, dict) else []
            invalid_candidates = len(raw_candidates) - len(candidates) if isinstance(raw_candidates, list) else 0
            if invalid_candidates:
                return {
                    "label": label,
                    "model": model,
                    "status": "validation_error",
                    "elapsed": elapsed,
                    "finish_reason": finish_reason,
                    "completion_tokens": completion_tokens,
                    "content_chars": len(content),
                    "reasoning_chars": len(reasoning),
                    "raw_candidates": len(raw_candidates),
                    "valid_candidates": len(candidates),
                    "candidates": [],
                    "error": f"{invalid_candidates} candidate(s) failed enum/field validation",
                }
            
            return {
                "label": label,
                "model": model,
                "status": "ok",
                "elapsed": elapsed,
                "finish_reason": finish_reason,
                "completion_tokens": completion_tokens,
                "content_chars": len(content),
                "reasoning_chars": len(reasoning),
                "raw_candidates": len(raw_candidates) if isinstance(raw_candidates, list) else 0,
                "valid_candidates": len(candidates),
                "candidates": candidates,
            }
    
    except asyncio.TimeoutError:
        elapsed = round(time.monotonic() - start, 1)
        return {
            "label": label,
            "model": model,
            "status": "timeout",
            "elapsed": elapsed,
            "candidates": [],
        }
    
    except Exception as e:
        elapsed = round(time.monotonic() - start, 1)
        return {
            "label": label,
            "model": model,
            "status": "error",
            "elapsed": elapsed,
            "candidates": [],
            "error": str(e)[:200],
        }


# ── Merge + Dedup + Vote ──────────────────────────────────────────────────────

def normalize_claim(claim: str) -> str:
    """Normalize claim text for dedup comparison.
    Strips formatting, lowers case, removes common Russian function words
    that vary between model phrasings without changing meaning."""
    text = claim.lower().strip()
    # Remove punctuation
    text = re.sub(r'[^\w\s]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove common Russian function words that cause false-negatives in dedup
    stop_words = {
        'пользователь', 'пользователя', 'пользователю',  # user / user's
        'был', 'была', 'были', 'быть',  # was/were/be
        'что', 'это', 'не', 'на', 'в', 'с', 'из', 'к', 'по', 'для', 'от', 'о', 'об',
        'и', 'а', 'но', 'или', 'же', 'ли',  # conjunctions
        'очень', 'весь', 'вся', 'все',  # very/all
        'следует', 'необходимо',  # should/must (common filler)
    }
    words = text.split()
    words = [w for w in words if w not in stop_words]
    return ' '.join(words)


def merge_candidates(worker_results: list[dict]) -> dict:
    """
    Merge candidates from all workers with dedup and vote counting.
    
    Returns:
        {
            "merged": [...],           # sorted by confidence+votes
            "stats": {...},            # worker stats
            "skipped_low_low": int,    # auto-skipped: durability=low + single worker
        }
    """
    # Collect all candidates with source info
    claim_map = {}  # normalized_claim -> {claim, sources, votes, ...}
    
    for result in worker_results:
        if result["status"] != "ok":
            continue
        source = result["label"]
        for c in result["candidates"]:
            key = normalize_claim(c["claim"])
            if key not in claim_map:
                claim_map[key] = {
                    "claim": c["claim"],  # keep first (best if from ds_pro)
                    "evidence_type": c["evidence_type"],
                    "durability": c["durability"],
                    "destination": c["destination"],
                    "action": c["action"],
                    "reason": c["reason"],
                    "sources": [],
                    "votes": 0,
                }
            claim_map[key]["sources"].append(source)
            claim_map[key]["votes"] += 1
    
    # Compute confidence from votes
    merged = []
    skipped_low_low = 0
    
    for key, entry in claim_map.items():
        votes = entry["votes"]
        
        # Confidence from votes
        if votes >= 2:
            entry["confidence"] = "high"
        else:
            entry["confidence"] = "low"
        
        # Auto-skip: durability=low + confidence=low
        if entry["durability"] == "low" and entry["confidence"] == "low":
            skipped_low_low += 1
            continue
        
        # Auto-skip: action=skip
        if entry["action"] == "skip":
            continue
        
        merged.append(entry)
    
    # Sort: high confidence first, then high durability
    durability_order = {"high": 0, "medium": 1, "low": 2}
    confidence_order = {"high": 0, "low": 1}
    
    merged.sort(key=lambda x: (
        confidence_order.get(x["confidence"], 99),
        durability_order.get(x["durability"], 99),
        -x["votes"],
    ))
    
    # Stats
    stats = {
        "workers_ok": sum(1 for r in worker_results if r["status"] == "ok"),
        "workers_total": len(worker_results),
        "total_raw_candidates": sum(r.get("raw_candidates", 0) for r in worker_results if r["status"] == "ok"),
        "total_valid_candidates": sum(r.get("valid_candidates", 0) for r in worker_results if r["status"] == "ok"),
        "after_dedup": len(merged),
        "after_auto_skip": skipped_low_low,
    }
    for r in worker_results:
        stats[f"{r['label']}_status"] = r["status"]
        stats[f"{r['label']}_elapsed"] = r["elapsed"]
        stats[f"{r['label']}_tokens"] = r.get("completion_tokens", "?")
    
    return {
        "merged": merged,
        "stats": stats,
        "skipped_low_low": skipped_low_low,
    }


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def run_workers(snippets: str) -> dict:
    """
    Run all workers in parallel on the same session snippets.
    Returns merged candidate list + stats.
    """
    async with aiohttp.ClientSession() as session:
        tasks = []
        for model, config in WORKER_MODELS.items():
            tasks.append(call_worker(session, model, config, snippets))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle exceptions from gather
    processed = []
    for r in results:
        if isinstance(r, Exception):
            processed.append({
                "label": "unknown",
                "model": "unknown",
                "status": "error",
                "elapsed": 0,
                "candidates": [],
                "error": str(r)[:200],
            })
        else:
            processed.append(r)
    
    return merge_candidates(processed)


def run_distillation(session_snippets: str) -> dict:
    """
    Synchronous entry point for execute_code.
    
    Args:
        session_snippets: concatenated session text (8-12k chars recommended)
    
    Returns:
        {
            "merged": [...],    # candidates sorted by priority
            "stats": {...},     # worker statistics
        }
    """
    return asyncio.run(run_workers(session_snippets))


# ── Formatting for Curator ────────────────────────────────────────────────────

def format_for_curator(merge_result: dict) -> str:
    """Format merged candidates as compact text for curator input."""
    lines = ["## Merged candidates for curation\n"]
    
    for i, c in enumerate(merge_result["merged"], 1):
        lines.append(
            f"{i}. [{c['confidence']}/{c['votes']}] "
            f"{c['action']} → {c['destination']}: "
            f"{c['claim']}"
        )
        lines.append(f"   reason: {c['reason']}")
        lines.append(f"   source: {', '.join(c['sources'])} | durability: {c['durability']}")
    
    lines.append(f"\n---\nStats: {json.dumps(merge_result['stats'], ensure_ascii=False)}")
    if merge_result["skipped_low_low"]:
        lines.append(f"Auto-skipped (durability=low + single worker): {merge_result['skipped_low_low']}")
    
    return "\n".join(lines)


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick test with synthetic data
    test_snippets = """
    Session 1: User configured n8n in Docker on port 5678 with SQLite. 
    User prefers App Password over OAuth for Google services.
    Added gemma4:31b-cloud to the model pool.
    
    Session 2: User corrected: cron job for weather should use gemma4:31b-cloud, not gemma4:cloud.
    The correct Ollama cloud tag format is model:size-cloud.
    """
    
    result = run_distillation(test_snippets)
    print(format_for_curator(result))