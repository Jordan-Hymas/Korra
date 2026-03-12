# Korra
**K.O.R.R.A** — Knowledge-Oriented Responsive Resource Assistant

Korra is a local voice assistant running on a Proxmox home server (pve2). It handles wake word detection, speech-to-text, and text-to-speech entirely on-device, and routes all queries to OpenClaw (pve1) as its AI brain over HTTP.

---

## Architecture

```
[User speaks]
     |
     v
pve2 — Korra (voice edge node)
  Wake word detection  →  Porcupine ("Hey Korra")
  Mic capture          →  PvRecorder + energy-based VAD
  Speech-to-text       →  Faster-Whisper (base, int8, CPU)
  HTTP POST            →  OpenClaw on pve1
     |
     v
pve1 — OpenClaw (AI brain)
  Receives transcript → generates response → streams SSE tokens back
     |
     v
pve2 — Korra (continued)
  SSE stream parsed    →  sentence-buffered chunking
  Text-to-speech       →  Piper TTS (piped directly to aplay)
  Audio playback       →  speaker output
```

---

## Features

- Wake word detection via **Picovoice Porcupine**
- VAD-based recording with hysteresis — stops on genuine silence, not inter-word pauses
- Noise floor auto-calibration at startup
- Speech-to-text via **Faster-Whisper** (beam_size=1, language=en, int8 CPU)
- Streaming HTTP to **OpenClaw** (`/v1/chat/completions`, SSE, `stream: true`)
- Sentence-chunked TTS streaming — first sentence spoken before full response arrives
- **Piper TTS** piped directly to aplay — no temp file, minimal latency
- Interrupt/stop: say "Hey Korra stop" mid-response to kill playback instantly
- Acoustic echo suppression — waits for room to go quiet after stopping before recording
- Markdown and emoji stripping before TTS
- Filler opener removal ("Sure!", "Of course!", etc.)
- Unit/abbreviation expansion (3GB → 3 gigabytes, 99% → 99 percent)
- Dedicated Korra bearer token + `X-Client: korra` header on every OpenClaw request
- Per-request latency logging (first-token ms, total ms)
- Graceful fallback if OpenClaw is unreachable

---

## Project Structure

```
Korra/
├── scripts/
│   ├── test_pipeline.py      # Main voice pipeline
│   ├── brain.py              # OpenClaw HTTP client (streaming)
│   └── test_brain.py         # Connection validation script
│
├── tts/
│   ├── piper_runtime/        # Piper binary + libs (not in git)
│   └── voices/               # TTS model files (not in git)
│
├── wakeword/                 # Wake word model (not in git)
├── stt/                      # STT models if added later
│
├── .env                      # Local secrets (not in git)
├── .env.example              # Template — copy to .env
├── KORRA_CODE_RULES.md       # Code-side enforcement checklist (from OpenClaw)
├── OPENCLAW_SYSTEM_PROMPT.md # System prompt + integration guide for OpenClaw
├── LICENSE.txt
└── README.md
```

---

## Setup

### 1. Clone and create venv

```bash
git clone <repo>
cd Korra
python3 -m venv venv
venv/bin/pip install pvporcupine pvrecorder faster-whisper requests python-dotenv setuptools
```

### 2. Download models (not in git — too large)

- **Piper binary**: place compiled binary + libs in `tts/piper_runtime/`
- **Piper voice model**: place `.onnx` and `.onnx.json` in `tts/voices/`
- **Wake word model**: place `.ppn` file in `wakeword/`

### 3. Configure environment

```bash
cp .env.example .env
nano .env   # fill in KORRA_OPENCLAW_TOKEN
```

`.env` values:
```
KORRA_OPENCLAW_URL=http://100.68.10.1:18793
KORRA_OPENCLAW_TOKEN=your_token_here

# Optional overrides
# KORRA_MODEL=openai-codex/gpt-5.3-codex
# KORRA_MAX_TOKENS=600
# KORRA_TIMEOUT_SECONDS=30
```

### 4. Validate OpenClaw connection

```bash
cd /home/yeti/Korra && venv/bin/python scripts/test_brain.py
```

### 5. Run

```bash
cd /home/yeti/Korra && venv/bin/python scripts/test_pipeline.py
```

---

## Hardware

- **pve2** — Proxmox node running Korra (CPU only, no GPU)
- **pve1** — Proxmox node running OpenClaw (AI brain, port 18793)
- Microphone device index: `3`
- Speaker device: `plughw:2,0`

---

## Tuning

| Variable | File | Default | Notes |
|---|---|---|---|
| `SILENCE_DURATION` | test_pipeline.py | 1.0s | Quiet time before recording stops |
| `ECHO_QUIET_SECS` | test_pipeline.py | 0.6s | Echo clear time after TTS kill |
| `MAX_RECORD_SECONDS` | test_pipeline.py | 30s | Hard cap on recording length |
| `MAX_SENTENCES` | test_pipeline.py | 10 | Max TTS sentences per response |
| `KORRA_MAX_TOKENS` | .env | 600 | OpenClaw response token cap |
| `ENERGY_THRESHOLD` | auto-calibrated | — | Set at startup from noise floor |

---

## OpenClaw Integration

See `OPENCLAW_SYSTEM_PROMPT.md` for the full system prompt and integration guide.
See `KORRA_CODE_RULES.md` for the code-side enforcement checklist.

Korra identifies itself to OpenClaw via:
- `Authorization: Bearer <KORRA_OPENCLAW_TOKEN>`
- `X-Client: korra`
- `X-Request-Id: <uuid>` (per request, for log tracing)

---

## Status

Active development. Core pipeline is functional and integrated with OpenClaw.

---

## License

See `LICENSE.txt`.
