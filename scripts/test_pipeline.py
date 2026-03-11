import subprocess
import wave
import time
import array

import pvporcupine
from pvrecorder import PvRecorder
from faster_whisper import WhisperModel

WAKEWORD = "/home/yeti/Korra/wakeword/hey-Kora_en_linux_v4_0_0.ppn"
PIPER_BIN = "/home/yeti/Korra/tts/piper_runtime/piper"
PIPER_MODEL = "/home/yeti/Korra/tts/voices/en_US-libritts_r-medium.onnx"

INPUT_WAV = "/home/yeti/Korra/input.wav"
OUTPUT_WAV = "/home/yeti/Korra/response.wav"

MIC_INDEX = 3
SPEAKER_DEVICE = "plughw:2,0"

RECORD_SECONDS = 7
SAMPLE_RATE = 16000

ACCESS_KEY = "/7NfDHFeMtng0mL02IQlPazBHec5ssoQk71+iIZrNbyQVpZEx4bblg=="


def save_wav(path, pcm, sample_rate=16000):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        audio = array.array("h", pcm)
        wf.writeframes(audio.tobytes())


def speak(text):
    print("Korra:", text)

    subprocess.run(
        f'echo "{text}" | {PIPER_BIN} --model {PIPER_MODEL} --output_file {OUTPUT_WAV}',
        shell=True,
        check=True,
    )

    subprocess.run(
        f"aplay -D {SPEAKER_DEVICE} {OUTPUT_WAV}",
        shell=True,
        check=True,
    )


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

print("Listening for 'Hey Korra'...")

try:
    while True:
        pcm = recorder.read()
        keyword_index = porcupine.process(pcm)

        if keyword_index >= 0:
            print("Wake word detected!")

            subprocess.run("play -n synth 0.1 sine 1000", shell=True)
            time.sleep(0.5)

            print("Recording command...")

            audio_frames = []
            total_frames = int((SAMPLE_RATE * RECORD_SECONDS) / porcupine.frame_length)

            for _ in range(total_frames):
                audio_frames.extend(recorder.read())

            save_wav(INPUT_WAV, audio_frames, SAMPLE_RATE)

            print("Transcribing...")

            segments, _ = model.transcribe(
                INPUT_WAV,
                vad_filter=True,
                beam_size=5,
            )

            text = " ".join(segment.text.strip() for segment in segments).strip()

            print("You said:", text)

            if not text:
                speak("I did not hear anything.")
            else:
                speak(f"You said {text}")

            print("Listening for 'Hey Korra' again...")

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    recorder.stop()
    recorder.delete()
    porcupine.delete()
