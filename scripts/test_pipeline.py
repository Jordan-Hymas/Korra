import subprocess
import wave
import array
import sys
import os
import re
import queue
import threading

import pvporcupine
from pvrecorder import PvRecorder
from faster_whisper import WhisperModel

sys.path.insert(0, os.path.dirname(__file__))
from brain import stream_openclaw

# ── config ────────────────────────────────────────────────────────────────────

WAKEWORD    = "/home/yeti/Korra/wakeword/hey-Kora_en_linux_v4_0_0.ppn"
PIPER_BIN   = "/home/yeti/Korra/tts/piper_runtime/piper"
PIPER_MODEL = "/home/yeti/Korra/tts/voices/en_US-libritts_r-medium.onnx"
INPUT_WAV   = "/home/yeti/Korra/input.wav"

MIC_INDEX      = 3
SPEAKER_DEVICE = "plughw:2,0"
SAMPLE_RATE    = 16000
ACCESS_KEY     = "/7NfDHFeMtng0mL02IQlPazBHec5ssoQk71+iIZrNbyQVpZEx4bblg=="

SILENCE_DURATION   = 1.0   # seconds of genuine quiet before stopping
MAX_RECORD_SECONDS = 30    # hard cap for long prompts
ECHO_QUIET_SECS    = 0.6

# ── stop event (cancels active SSE stream + TTS queue on interruption) ────────

_stop_event = threading.Event()

# ── TTS queue ─────────────────────────────────────────────────────────────────

_tts_queue    = queue.Queue()
_current_play = None
_play_lock    = threading.Lock()
_speaking     = False


def _tts_worker():
    global _current_play, _speaking
    while True:
        text = _tts_queue.get()
        if text is None:
            break

        piper = subprocess.Popen(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output-raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        aplay = subprocess.Popen(
            ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-D", SPEAKER_DEVICE],
            stdin=piper.stdout,
            stderr=subprocess.DEVNULL,
        )

        with _play_lock:
            _current_play = aplay
            _speaking = True

        piper.stdin.write(text.encode())
        piper.stdin.close()
        piper.wait()
        aplay.wait()

        with _play_lock:
            _current_play = None

        if _tts_queue.empty():
            _speaking = False
            print("Listening for 'Hey Korra'...")


_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()


def stop_speaking():
    """Cancel active SSE stream, drain TTS queue, kill aplay."""
    global _speaking
    _stop_event.set()
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break
    with _play_lock:
        if _current_play and _current_play.poll() is None:
            _current_play.kill()
        _speaking = False


# ── text cleaning ─────────────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "]+",
    flags=re.UNICODE,
)

_FILLER_OPENER = re.compile(
    r'^(Sure|Of course|Certainly|Absolutely|Great question|Happy to help|'
    r'I\'d be happy to|I\'m happy to|Good question|Definitely|No problem|'
    r'Of course|Glad you asked|Great|Got it)[!,.]?\s*',
    re.IGNORECASE,
)

# Unit/abbreviation expansion — expand before TTS so Piper reads them naturally
_UNIT_SUBS = [
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*TB\b',  re.IGNORECASE), r'\1 terabytes'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*GB\b',  re.IGNORECASE), r'\1 gigabytes'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*MB\b',  re.IGNORECASE), r'\1 megabytes'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*KB\b',  re.IGNORECASE), r'\1 kilobytes'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*GHz\b', re.IGNORECASE), r'\1 gigahertz'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*MHz\b', re.IGNORECASE), r'\1 megahertz'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*Hz\b',  re.IGNORECASE), r'\1 hertz'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*ms\b',  re.IGNORECASE), r'\1 milliseconds'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*min\b', re.IGNORECASE), r'\1 minutes'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*sec\b', re.IGNORECASE), r'\1 seconds'),
    (re.compile(r'\b(\d+(?:\.\d+)?)\s*%'),                    r'\1 percent'),
    (re.compile(r'\$(\d+(?:\.\d+)?)'),                        r'\1 dollars'),
]


def clean_for_tts(text):
    # Strip markdown
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`]*`', ' ', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', text)
    text = re.sub(r'^\s*[-*+>]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[#*_~`|]', '', text)
    # Strip emojis
    text = _EMOJI_RE.sub('', text)
    # Strip filler opener
    text = _FILLER_OPENER.sub('', text)
    # Expand units
    for pattern, replacement in _UNIT_SUBS:
        text = pattern.sub(replacement, text)
    # Normalise whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ── sentence streaming ────────────────────────────────────────────────────────

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
_CLAUSE_END   = re.compile(r'(?<=[,;])\s+')
_CLAUSE_MIN   = 45
MAX_SENTENCES = 10  # soft guide — raise freely for longer responses


def _queue_sentence(sentence):
    sentence = clean_for_tts(sentence)
    if sentence:
        _tts_queue.put(sentence)


def speak(text):
    _queue_sentence(text)


def speak_stream(gen):
    """
    Buffer SSE chunks → flush on sentence/clause boundaries → queue for TTS.
    Stops after MAX_SENTENCES or when _stop_event is set.
    Appends a period to any unpunctuated trailing fragment.
    Runs in a background thread so the main loop stays live for wake word.
    """
    buf        = ""
    sent_count = 0

    for chunk in gen:
        if _stop_event.is_set():
            break
        buf += chunk

        while True:
            if sent_count >= MAX_SENTENCES:
                return

            m = _SENTENCE_END.search(buf)
            if m:
                _queue_sentence(buf[:m.start() + 1])
                buf = buf[m.end():]
                sent_count += 1
                continue

            if len(buf) >= _CLAUSE_MIN:
                m = _CLAUSE_END.search(buf)
                if m:
                    _queue_sentence(buf[:m.start() + 1])
                    buf = buf[m.end():]
                    sent_count += 1
                    continue
            break

    # Flush remaining buffer if not interrupted and under sentence cap
    if buf.strip() and not _stop_event.is_set() and sent_count < MAX_SENTENCES:
        tail = buf.strip()
        if tail and tail[-1] not in '.!?':
            tail += '.'
        _queue_sentence(tail)


def _response_worker(text):
    """Background thread: fetch OpenClaw stream and queue sentences."""
    speak_stream(stream_openclaw(text, stop_event=_stop_event))


def ask_and_speak(text):
    """Dispatch OpenClaw request to background thread; main loop stays live."""
    t = threading.Thread(target=_response_worker, args=(text,), daemon=True)
    t.start()


# ── stop-command detection ────────────────────────────────────────────────────

_STOP_WORDS = {"stop", "halt", "quiet", "enough", "shut up", "be quiet", "stop talking"}

_QUESTION_WORDS = {
    "what", "who", "where", "when", "why", "how", "is", "are", "can", "could",
    "will", "would", "do", "does", "tell", "explain", "show", "give", "list",
    "help", "find", "search", "check", "run", "open", "set", "get",
}


def is_stop_command(text, was_speaking):
    normalized = text.lower().strip().rstrip('.!?,')
    words = normalized.split()

    if normalized in _STOP_WORDS or (words and words[0] in _STOP_WORDS):
        return True

    if was_speaking and not any(w in _QUESTION_WORDS for w in words):
        return True

    return False


# ── audio helpers ─────────────────────────────────────────────────────────────

def save_wav(path, pcm):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(array.array("h", pcm).tobytes())


def rms(frame):
    if not frame:
        return 0
    return (sum(s * s for s in frame) / len(frame)) ** 0.5


def calibrate_noise_floor(recorder, frame_length, duration=1.5):
    print("Calibrating noise floor — please be quiet...")
    n = int(duration * SAMPLE_RATE / frame_length)
    values = [rms(recorder.read()) for _ in range(n)]
    ambient = sum(values) / len(values)
    threshold = max(200, ambient * 4)
    print(f"  ambient RMS: {ambient:.0f}  →  speech threshold: {threshold:.0f}")
    return threshold


def wait_for_quiet(recorder, frame_length, energy_threshold):
    frames_per_second = SAMPLE_RATE / frame_length
    quiet_needed = int(ECHO_QUIET_SECS * frames_per_second)
    max_wait     = int(3.0 * frames_per_second)
    quiet_count  = 0
    for _ in range(max_wait):
        frame = recorder.read()
        if rms(frame) < energy_threshold:
            quiet_count += 1
            if quiet_count >= quiet_needed:
                return
        else:
            quiet_count = 0


def record_until_silence(recorder, frame_length, energy_threshold):
    frames_per_second = SAMPLE_RATE / frame_length
    silence_needed    = int(SILENCE_DURATION * frames_per_second)
    max_frames        = int(MAX_RECORD_SECONDS * frames_per_second)

    # Hysteresis: speech starts above energy_threshold, but silence only
    # counts when energy drops well below it (50%). This prevents brief
    # inter-word pauses from triggering early stop.
    silence_floor = energy_threshold * 0.5

    all_samples   = []
    silence_count = 0
    speech_seen   = False

    for _ in range(max_frames):
        frame = recorder.read()
        all_samples.extend(frame)
        e = rms(frame)

        if e > energy_threshold:
            speech_seen   = True
            silence_count = 0
        elif speech_seen:
            if e < silence_floor:
                silence_count += 1
                if silence_count >= silence_needed:
                    break
            # energy between silence_floor and threshold = transitional
            # (end of word, breath, soft consonant) — don't count, don't reset

    return all_samples


# ── startup ───────────────────────────────────────────────────────────────────

print("Loading Whisper model...")
model = WhisperModel("base", device="cpu", compute_type="int8")

print("Loading wake word...")
porcupine = pvporcupine.create(
    access_key=ACCESS_KEY,
    keyword_paths=[WAKEWORD],
)

print("Opening microphone...")
recorder = PvRecorder(device_index=MIC_INDEX, frame_length=porcupine.frame_length)
recorder.start()

energy_threshold = calibrate_noise_floor(recorder, porcupine.frame_length)

print("Listening for 'Hey Korra'...")

# ── main loop ─────────────────────────────────────────────────────────────────

try:
    while True:
        pcm = recorder.read()
        if porcupine.process(pcm) < 0:
            continue

        was_speaking = _speaking
        if was_speaking:
            stop_speaking()
            wait_for_quiet(recorder, porcupine.frame_length, energy_threshold)

        subprocess.run(
            "play -n synth 0.1 sine 1000",
            shell=True, stderr=subprocess.DEVNULL,
        )

        audio = record_until_silence(recorder, porcupine.frame_length, energy_threshold)
        save_wav(INPUT_WAV, audio)

        print(f"Captured {len(audio)/SAMPLE_RATE:.1f}s — transcribing...")
        segments, _ = model.transcribe(INPUT_WAV, vad_filter=True, beam_size=1, language="en")
        text = " ".join(s.text.strip() for s in segments).strip()
        print("You said:", text)

        if not text or is_stop_command(text, was_speaking):
            if not text and not was_speaking:
                speak("I didn't catch that.")
            print("Listening for 'Hey Korra'...")
            continue

        print("Asking OpenClaw...")
        _stop_event.clear()   # clear before dispatch — ensures new stream isn't cancelled
        ask_and_speak(text)   # non-blocking — wake word detection resumes immediately

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    stop_speaking()
    _tts_queue.put(None)
    recorder.stop()
    recorder.delete()
    porcupine.delete()
