#!/usr/bin/env python3
"""
Quick end-to-end validation for the Korra → OpenClaw connection.
Run this on pve2 before starting the full pipeline.

Usage:
    cd /home/yeti/Korra
    venv/bin/python scripts/test_brain.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# ── checklist helpers ─────────────────────────────────────────────────────────

_results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    _results.append((status, label, detail))
    print(f"  [{status}] {label}" + (f"  →  {detail}" if detail else ""))

# ── run checks ────────────────────────────────────────────────────────────────

print("\nKorra → OpenClaw connection check\n" + "─" * 40)

# 1. Token loaded
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
token = os.environ.get("KORRA_OPENCLAW_TOKEN", "")
check("dedicated token loaded", bool(token), "(value hidden)" if token else "KORRA_OPENCLAW_TOKEN not set")

url = os.environ.get("KORRA_OPENCLAW_URL", "http://pve1:18789/").rstrip("/")
check("target URL", True, url)

if not token:
    print("\nCannot continue without KORRA_OPENCLAW_TOKEN. Add it to .env and retry.")
    sys.exit(1)

# 2. X-Client header present in request
import requests as _req
import json as _json

_headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type":  "application/json",
    "X-Client":      "korra",
}
check("X-Client header set", _headers.get("X-Client") == "korra", "korra")

# 3. SSE stream — send a short test prompt and confirm first chunk arrives
print("\nSending test stream request to OpenClaw...")
first_chunk = None
full_response = ""

try:
    resp = _req.post(
        f"{url}/v1/chat/completions",
        headers=_headers,
        json={
            "model":      "openai-codex/gpt-5.3-codex",
            "stream":     True,
            "max_tokens": 60,
            "messages": [
                {"role": "system",  "content": "You are Korra, a voice assistant. Reply in one short sentence."},
                {"role": "user",    "content": "Say hello and confirm you are online."},
            ],
        },
        stream=True,
        timeout=30,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        if line.startswith(b"data: "):
            data = line[6:]
            if data == b"[DONE]":
                break
            try:
                delta = _json.loads(data)["choices"][0]["delta"].get("content", "")
                if delta:
                    if first_chunk is None:
                        first_chunk = delta
                    full_response += delta
            except (KeyError, _json.JSONDecodeError):
                continue

    check("SSE stream working", first_chunk is not None, f'first chunk: "{first_chunk}"')
    check("response content received", bool(full_response.strip()), full_response.strip()[:80])

except _req.exceptions.Timeout:
    check("SSE stream working", False, "timed out after 30s")
except _req.exceptions.ConnectionError as e:
    check("SSE stream working", False, f"connection error: {e}")
except Exception as e:
    check("SSE stream working", False, str(e))

# 4. Fallback path — simulate a timeout/error via brain module
print("\nTesting fallback path (simulated error)...")
from unittest.mock import patch

original_token = os.environ.get("KORRA_OPENCLAW_TOKEN")
with patch.dict(os.environ, {"KORRA_OPENCLAW_URL": "http://127.0.0.1:1/"}):
    # Re-import with bad URL
    import importlib
    import brain as _brain_mod
    old_url = _brain_mod.OPENCLAW_URL
    _brain_mod.OPENCLAW_URL = "http://127.0.0.1:1"
    result = _brain_mod.ask_openclaw("test")
    _brain_mod.OPENCLAW_URL = old_url
    check("fallback on connection error", result == _brain_mod.FALLBACK, f'got: "{result}"')

# ── summary ───────────────────────────────────────────────────────────────────

print("\n" + "─" * 40)
passed = sum(1 for s, _, _ in _results if s == "PASS")
total  = len(_results)
print(f"Result: {passed}/{total} checks passed\n")

if passed < total:
    sys.exit(1)
