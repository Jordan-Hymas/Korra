# Korra Code-Side Enforcement Checklist
Target runtime: pve2
Primary files: brain.py, test_pipeline.py
Source: OpenClaw (pve1) — generated 2026-03-11

==================================================
A) REQUEST IDENTITY AND ROUTING
==================================================

[ ] brain.py sends these headers on every OpenClaw request:
    - Authorization: Bearer <KORRA_OPENCLAW_TOKEN>
    - Content-Type: application/json
    - X-Client: korra

[ ] brain.py reads endpoint + token from env:
    - KORRA_OPENCLAW_URL (default: http://100.68.10.1:18793)
    - KORRA_OPENCLAW_TOKEN (required; fail fast if missing)

[ ] brain.py always posts to:
    - {KORRA_OPENCLAW_URL}/v1/chat/completions

[ ] test_pipeline.py has a test that asserts X-Client: korra is actually sent.

==================================================
B) MODEL + REQUEST SHAPE
==================================================

[ ] brain.py uses model:
    - openai-codex/gpt-5.3-codex
    (or a single configurable env value, defaulting to this)

[ ] request payload remains OpenAI-compatible:
    - model
    - stream: true
    - messages: [system, user]

[ ] include max_tokens cap in request if supported:
    - max_tokens: 120

[ ] test_pipeline.py validates request body shape and model name.

==================================================
C) LATENCY AND STREAMING BEHAVIOR
==================================================

[ ] brain.py keeps stream=true and processes SSE incrementally (no full-buffer wait).

[ ] brain.py measures:
    - request start timestamp
    - first token timestamp
    - total completion timestamp

[ ] brain.py logs first-token latency for every turn.

[ ] SSE stream is cancellable mid-stream when user interrupts.

==================================================
D) SENTENCE-BASED TTS CHUNKING
==================================================

[ ] speak_stream buffers token text and emits to TTS only on sentence boundary:
    - ., !, ? followed by whitespace or end-of-stream
    - also splits on , ; after buffer >= 45 chars (clause-early flush)

[ ] speak_stream never sends mid-sentence fragments unless interrupted.

[ ] speak_stream flushes final partial sentence at stream end:
    - if unpunctuated tail, append period before queuing

[ ] sentence count guard: stop queuing after 3 sentences.

==================================================
E) RESPONSE STYLE ENFORCEMENT
==================================================

[ ] brain.py sends compact system prompt:
    - direct answer first
    - 2-3 sentences total
    - ~80-120 tokens
    - no markdown, no emojis, no filler openers

[ ] clean_for_tts strips:
    - markdown markers (**, *, #, backticks, list prefixes)
    - URLs
    - emoji/symbol noise
    - whitespace normalization

[ ] opener guard:
    - strip filler sentence starters (Sure, Of course, Great question, etc.)

==================================================
F) NUMBER / ABBREVIATION SPEECH NORMALIZATION
==================================================

[ ] clean_for_tts normalizes units before TTS:
    - 3GB -> 3 gigabytes
    - 10min -> 10 minutes
    - 99% -> 99 percent
    - $99 -> 99 dollars
    - etc.

==================================================
G) INTERRUPTION + STOP HANDLING
==================================================

[ ] wake-word fires during response → immediately stops aplay.

[ ] stop_speaking() also cancels active SSE stream (stop event signal).

[ ] speak_stream exits cleanly on stop event.

[ ] if user says stop intent → no new OpenClaw request sent.

[ ] response pipeline runs in background thread so main loop
    stays live for wake-word detection during SSE reception.

==================================================
H) FAILSAFE / FALLBACK
==================================================

[ ] request timeout: 30 seconds (configurable via KORRA_TIMEOUT_SECONDS).

[ ] on timeout, non-2xx, or network error:
    - speak: "I'm having trouble reaching my main system right now."
    - return to wake-word listening
    - do not retry

==================================================
I) OBSERVABILITY
==================================================

[ ] brain.py logs one line per request:
    - request id
    - first-token latency ms
    - total latency ms
    - fallback used yes/no

[ ] X-Request-Id: <uuid> header sent on every request.

==================================================
J) CONFIG / ENV CHECKLIST
==================================================

[ ] .env contains:
    - KORRA_OPENCLAW_URL=http://100.68.10.1:18793
    - KORRA_OPENCLAW_TOKEN=<secret>
    - optional: KORRA_MODEL=openai-codex/gpt-5.3-codex
    - optional: KORRA_MAX_TOKENS=120
    - optional: KORRA_TIMEOUT_SECONDS=30

[ ] .env.example contains placeholders only (no real token).

[ ] startup validation fails clearly if token is empty or URL invalid.

==================================================
K) QUICK VERIFICATION COMMAND
==================================================

source .env && curl -N -sS "$KORRA_OPENCLAW_URL/v1/chat/completions" \
  -H "Authorization: Bearer $KORRA_OPENCLAW_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Client: korra" \
  -d '{"model":"openai-codex/gpt-5.3-codex","stream":true,"max_tokens":120,
       "messages":[{"role":"system","content":"You are Korra. Reply in two short spoken sentences. No markdown."},
                   {"role":"user","content":"Say one sentence confirming the Korra pipeline is healthy."}]}'

Expected: HTTP 200, SSE data chunks, data: [DONE]

==================================================
L) DEFINITION OF DONE
==================================================

1) Korra request includes X-Client header and dedicated token.
2) SSE stream starts quickly and first sentence is spoken within ~2s.
3) Output is consistently 2-3 clean spoken sentences.
4) Fallback behavior works on failure.
5) Response pipeline runs in background — wake word always live.
