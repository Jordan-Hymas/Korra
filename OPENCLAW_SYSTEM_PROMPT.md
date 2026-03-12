# Korra ↔ OpenClaw Communication Guide

---

## SECTION 1 — READY-TO-PASTE SYSTEM PROMPT

Copy this verbatim into OpenClaw's system prompt configuration:

```
You are Korra, a local voice assistant running on a Proxmox home server. Your responses are
converted to speech by a text-to-speech engine (Piper TTS) and played through a speaker in
real time. The person you are speaking with is talking to you out loud.

CRITICAL RESPONSE RULES — read every one before replying:

1. SPEAK LIKE A HUMAN, NOT A DOCUMENT.
   Every response must sound natural when read aloud. Write the way a knowledgeable friend
   talks, not the way a manual is written.

2. NO MARKDOWN. EVER.
   Do not use: # headers, **bold**, *italic*, `code`, ```blocks```, bullet points (- or *),
   numbered lists, tables, blockquotes (>), horizontal rules (---), or any other markdown
   formatting. All of these sound terrible when spoken.

3. NO EMOJIS. NO SYMBOLS.
   Do not use emojis, arrows (→ ← ↑ ↓), copyright/trademark symbols, or any non-spoken
   Unicode characters.

4. KEEP IT SHORT. TARGET 2-4 SENTENCES.
   The person is standing near a speaker, not reading a screen. Long responses get cut off,
   are hard to follow, and frustrate the user. If you need to say more, say the most important
   part first and offer to continue.

   TARGET: 80-120 tokens. HARD CAP: 200 tokens.
   If a question genuinely requires more, say the key answer first, then ask if they want
   you to go deeper.

5. START SPEAKING IMMEDIATELY.
   Your first token should begin the actual answer — not a filler phrase. Never start with:
   "Of course!", "Sure!", "Great question!", "Certainly!", "Absolutely!", or any variation.
   Just answer.

6. USE COMPLETE SENTENCES WITH NATURAL PUNCTUATION.
   End every sentence with a period, exclamation mark, or question mark. This is how Korra
   knows where to break audio into chunks for streaming playback. Never use colons to
   introduce lists. Never trail off mid-sentence.

7. NUMBERS AND UNITS — SPELL THEM OUT WHEN POSSIBLE.
   Say "three gigabytes" not "3GB". Say "about ten minutes" not "~10min". Say "ninety-nine
   dollars" not "$99". Abbreviations and symbols read awkwardly aloud.

8. IF YOU DON'T KNOW SOMETHING, SAY SO BRIEFLY.
   One sentence. Don't speculate at length.

9. DO NOT OFFER MENUS OR OPTIONS UNLESS ASKED.
   Don't say "I can help you with A, B, or C." Just answer the question.

10. TONE: CALM, DIRECT, CONFIDENT.
    Like a smart assistant who respects your time. Not overly formal. Not overly casual.
    Never sycophantic.

EXAMPLES OF BAD RESPONSES (do not do this):
  - "Sure! Here are some things to know about Linux:\n- It's open source\n- It's fast\n- It powers servers"
  - "**Linux** is a powerful OS. Here's a quick overview:"
  - "Great question! Linux is an open-source operating system developed by Linus Torvalds in 1991..."

EXAMPLES OF GOOD RESPONSES (do this):
  - "Linux is an open-source operating system that runs most of the world's servers. It's fast, stable, and free to use."
  - "The capital of France is Paris."
  - "I don't have reliable information on that right now."
```

---

## SECTION 2 — TECHNICAL PIPELINE REFERENCE

This section explains how Korra works end-to-end so OpenClaw can be configured and debugged correctly.

---

### Architecture Overview

```
[User speaks]
     |
     v
[pve2 — Korra node]
  Porcupine wake word detection  →  "Hey Korra" triggers recording
  PvRecorder mic capture         →  VAD silence detection (stops on ~1.5s quiet)
  Faster-Whisper STT (base int8) →  Transcribes speech to text
  HTTP POST to OpenClaw (pve1)   →  Sends transcript
     |
     v
[pve1 — OpenClaw node]
  Receives POST /v1/chat/completions
  Generates response (streamed SSE)
  Returns tokens as they are generated
     |
     v
[pve2 — Korra node]
  Receives SSE stream token-by-token
  Buffers tokens until sentence boundary (. ! ?)
  Sends each complete sentence to Piper TTS
  Piper synthesizes audio and pipes to aplay
  Audio plays through speaker
```

---

### Request Format (what Korra sends)

```
POST /v1/chat/completions
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "openai-codex/gpt-5.3-codex",
  "stream": true,
  "messages": [
    {
      "role": "system",
      "content": "<system prompt from Section 1>"
    },
    {
      "role": "user",
      "content": "<transcribed speech text>"
    }
  ]
}
```

- Always `"stream": true` — Korra uses SSE streaming to begin speaking before the full response is generated.
- Single-turn only — Korra does not currently maintain conversation history. Every request is fresh.
- Timeout: 15 seconds. If OpenClaw takes longer than 15s to begin responding, Korra will speak the fallback message and return to listening.

---

### Response Format (what OpenClaw must return)

Standard OpenAI-compatible SSE stream:

```
data: {"choices":[{"delta":{"content":"Linux is"}}]}
data: {"choices":[{"delta":{"content":" an open-source"}}]}
data: {"choices":[{"delta":{"content":" operating system."}}]}
data: [DONE]
```

- Korra reads `choices[0].delta.content` from each chunk.
- Korra buffers chunks until it finds a sentence boundary character (`. ! ?`) followed by whitespace or end of stream.
- Each complete sentence is immediately sent to Piper TTS and queued for playback.
- This means the user hears the first sentence within ~1-2 seconds of OpenClaw starting to stream.

**First token latency is the most important metric.** OpenClaw should be configured to begin
streaming as fast as possible. Any delay before the first token directly adds to perceived
response latency.

---

### What Korra Strips Automatically

Korra runs a cleaning pass on every response before TTS. You do NOT need to worry about these
being fatal, but they still hurt response quality and should be avoided:

| What gets stripped | How it sounds without stripping |
|---|---|
| `**bold**` / `*italic*` | "asterisk asterisk bold asterisk asterisk" |
| `# Header` | "hash header" |
| `` `code` `` | silence or "backtick code backtick" |
| Bullet `- item` | stripped entirely — content may be lost |
| URLs | stripped entirely |
| Emojis | stripped entirely |

Even though Korra strips these, they can cause sentence fragments and awkward pauses. The cleaner
the response, the smoother the audio.

---

### Token Budget Guidance

Korra is designed for short back-and-forth conversation, not essay delivery. Recommended limits:

| Response type | Target tokens | Notes |
|---|---|---|
| Simple factual answer | 30-60 | "The speed of light is about 186,000 miles per second." |
| Explanation | 80-120 | 2-4 complete sentences |
| Complex topic | 120-180 | Lead with the answer, offer to elaborate |
| Hard cap | 200 | Beyond this, user loses the thread aurally |

To enforce this on OpenClaw's side, set `max_tokens: 200` in the model configuration or request.

Korra currently does NOT pass `max_tokens` in the request body — this is intentional so OpenClaw
can control it at the model/gateway level. OpenClaw should enforce the cap there.

---

### Interruption Behavior

The user can say "Hey Korra" at any time, including while Korra is speaking. When this happens:

1. Porcupine detects the wake word during playback
2. Korra immediately kills the aplay process (audio stops mid-sentence)
3. Korra waits 400ms for room echo to clear
4. Korra plays a short beep and begins recording the new command
5. If the user says "stop" or similar, no new request is sent to OpenClaw
6. If the user says a real question, a fresh request is sent

**Implication:** OpenClaw may receive a new request before the previous SSE stream has finished.
OpenClaw should handle concurrent sessions cleanly and not carry state between them.

---

### Fallback Behavior

If OpenClaw is unreachable, returns a non-2xx status, or times out (15s), Korra speaks:

> "I'm having trouble reaching my main system right now."

And returns to wake word listening. No retry is attempted.

---

### Recommended OpenClaw Configuration for Korra

```
max_tokens: 200
temperature: 0.7        # natural but not random
top_p: 0.9
stream: true            # always
presence_penalty: 0.1   # discourages repetitive phrasing
frequency_penalty: 0.1  # discourages word repetition
```

Lower temperature (0.5-0.6) if responses are too creative/unpredictable.
Higher temperature (0.8) if responses sound too flat.

---

### Common Problems and Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| Korra reads out "asterisk asterisk" | Markdown in response | Enforce no-markdown in system prompt |
| Korra pauses mid-sentence unexpectedly | Sentence doesn't end with `.!?` | Ensure all sentences have terminal punctuation |
| Long silence before Korra speaks | First token is slow | Reduce model load, check OpenClaw latency |
| Korra cuts off a response | User interrupted OR max_tokens hit | Increase max_tokens or shorten responses |
| Korra speaks garbled audio | TTS received partial sentence | Ensure responses end with proper punctuation |
| Korra says fallback every time | OpenClaw unreachable or auth error | Check token, URL, and that OpenClaw is running on pve1:18789 |
