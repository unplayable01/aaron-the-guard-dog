"""
Always-on voice-activated wake for Aaron. Say "Wake up Aaron" (or whatever
WAKE_WORDS is set to) and, if it's actually your voice (verified against
voice_profile.json via Resemblyzer speaker embeddings, not just anyone
saying the phrase), starts guard_watch.py - same as sending /wake.

Setup: run enroll_voice.py first to build your voice profile.

All audio processing is local/offline (Vosk) - nothing is sent anywhere
except the one Telegram confirmation message after a successful wake.

Meant to be launched via pythonw.exe (no console window). See
run_voice_wake_hidden.vbs and stop_voice_wake.bat.
"""

import json
import os
import queue
import time
from datetime import datetime
import sounddevice as sd
import requests

from aaron_listener import GuardHandle, load_telegram_config
from voice_engine import (
    load_vosk_model, create_recognizer, create_voice_encoder, load_voice_profile,
    compute_embedding, best_speaker_similarity, phrase_matches, find_input_device,
    SAMPLE_RATE, VOICE_PROFILE_PATH,
)

import paths

LOG_PATH = paths.log_file("voice_wake.log")

WAKE_WORDS = ["wake", "up", "aaron"]
# Live-measured: a genuine attempt scored as low as 0.582 (rejected under
# the old 0.75 default) while another scored 0.795 - real variance from
# background noise/mic distance/voice tone. 0.55 sits comfortably below the
# lowest genuine sample seen so far. If a re-enrollment with cleaner
# samples tightens the observed range, this can come back up.
SPEAKER_THRESHOLD = 0.55

# Don't act on another wake phrase this soon after the last one, successful
# or not - avoids double-triggering on echoes/repeated attempts.
WAKE_COOLDOWN_SECONDS = 5


def log(message):
    line = f"{datetime.now().isoformat(timespec='seconds')} [voice_wake] {message}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def send_telegram_message(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
        if not resp.ok:
            log(f"Telegram send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram send error: {e}")


def main():
    log("Voice wake starting.")

    try:
        bot_token, chat_id, _friends = load_telegram_config()
    except (FileNotFoundError, RuntimeError) as e:
        log(str(e))
        return

    try:
        profile = load_voice_profile(VOICE_PROFILE_PATH)
    except FileNotFoundError:
        log("voice_profile.json not found - run enroll_voice.py first.")
        return

    log("Loading speech model...")
    model = load_vosk_model()
    recognizer = create_recognizer(model)
    log("Loading voice encoder...")
    encoder = create_voice_encoder()

    guard = GuardHandle()
    audio_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_queue.put(bytes(indata))

    device = find_input_device()
    log(f"Using input device: {sd.query_devices(device)['name'] if device is not None else 'system default'}")
    log(f'Listening for "{" ".join(WAKE_WORDS)}" ({len(profile)} enrolled voice samples).')

    utterance_audio = bytearray()
    last_wake_time = 0.0

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype='int16',
                            channels=1, device=device, callback=callback):
        while True:
            data = audio_queue.get()
            utterance_audio.extend(data)

            if not recognizer.AcceptWaveform(bytes(data)):
                continue

            result = json.loads(recognizer.Result())
            text = result.get("text", "")
            audio = bytes(utterance_audio)
            utterance_audio = bytearray()

            if not text.strip():
                continue

            if not phrase_matches(text, WAKE_WORDS):
                log(f'Heard "{text}" - not the wake phrase, ignoring.')
                continue

            now = time.time()
            if now - last_wake_time < WAKE_COOLDOWN_SECONDS:
                log(f'Heard "{text}" (phrase match) but within cooldown, ignoring.')
                continue

            embedding = compute_embedding(encoder, audio)
            similarity = best_speaker_similarity(embedding, profile)
            log(f'Heard "{text}" (phrase match) - speaker similarity={similarity:.3f} '
                f"(threshold={SPEAKER_THRESHOLD})")

            if similarity < SPEAKER_THRESHOLD:
                log("Voice didn't match your profile - not waking.")
                continue

            last_wake_time = now
            if guard.start():
                log("Voice-activated wake successful - starting Aaron.")
                send_telegram_message(bot_token, chat_id, "🐕 Aaron heard your voice and is waking up.")
            else:
                log("Voice matched, but Aaron was already running.")


if __name__ == "__main__":
    main()
