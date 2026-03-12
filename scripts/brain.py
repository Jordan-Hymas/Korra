import json
import os
import sys
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ── config ────────────────────────────────────────────────────────────────────

OPENCLAW_URL   = os.environ.get("KORRA_OPENCLAW_URL",   "http://100.68.10.1:18793").rstrip("/")
OPENCLAW_TOKEN = os.environ.get("KORRA_OPENCLAW_TOKEN", "")
OPENCLAW_MODEL = os.environ.get("KORRA_MODEL",          "openai-codex/gpt-5.3-codex")
MAX_TOKENS     = int(os.environ.get("KORRA_MAX_TOKENS",      "600"))
TIMEOUT        = int(os.environ.get("KORRA_TIMEOUT_SECONDS", "30"))

if not OPENCLAW_TOKEN:
    print("[brain] FATAL: KORRA_OPENCLAW_TOKEN is not set.")
    sys.exit(1)

print(f"[brain] OpenClaw target : {OPENCLAW_URL}")
print(f"[brain] Model           : {OPENCLAW_MODEL}")
print(f"[brain] Korra token mode: enabled (X-Client: korra)")

# ── system prompt (kept short — every token costs latency) ───────────────────

SYSTEM_PROMPT = (
    "You are Korra, a local voice assistant. "
    "Respond naturally and conversationally in 2-3 spoken sentences. "
    "No markdown, bullet points, lists, symbols, or emojis. "
    "Get to the answer immediately — no filler openers like 'Sure' or 'Great question'."
)

FALLBACK = "I'm having trouble reaching my main system right now."

# ── streaming ─────────────────────────────────────────────────────────────────

def stream_openclaw(text: str, stop_event=None):
    """
    Yield text chunks from OpenClaw via SSE streaming.
    stop_event: threading.Event — when set, exits the stream immediately.
    Logs first-token and total latency per request.
    """
    req_id  = uuid.uuid4().hex[:8]
    t_start = time.monotonic()
    t_first = None
    fallback_used = False

    try:
        response = requests.post(
            f"{OPENCLAW_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENCLAW_TOKEN}",
                "Content-Type":  "application/json",
                "X-Client":      "korra",
                "X-Request-Id":  req_id,
            },
            json={
                "model":              OPENCLAW_MODEL,
                "stream":             True,
                "max_tokens":         MAX_TOKENS,
                "temperature":        0.7,
                "top_p":              0.95,
                "presence_penalty":   0.0,
                "frequency_penalty":  0.1,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": text},
                ],
            },
            stream=True,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if stop_event and stop_event.is_set():
                break
            if not line:
                continue
            if line.startswith(b"data: "):
                data = line[6:]
                if data == b"[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content", "")
                    if delta:
                        if t_first is None:
                            t_first = time.monotonic()
                        yield delta
                except (KeyError, json.JSONDecodeError):
                    continue

    except requests.exceptions.Timeout:
        print(f"[brain:{req_id}] timed out after {TIMEOUT}s — falling back.")
        fallback_used = True
        yield FALLBACK
    except requests.exceptions.ConnectionError:
        print(f"[brain:{req_id}] unreachable — falling back.")
        fallback_used = True
        yield FALLBACK
    except Exception as e:
        print(f"[brain:{req_id}] error: {e}")
        fallback_used = True
        yield FALLBACK
    finally:
        t_end     = time.monotonic()
        first_ms  = round((t_first - t_start) * 1000) if t_first else -1
        total_ms  = round((t_end   - t_start) * 1000)
        print(f"[brain:{req_id}] first-token {first_ms}ms | total {total_ms}ms | fallback={fallback_used}")


def ask_openclaw(text: str) -> str:
    return "".join(stream_openclaw(text))
