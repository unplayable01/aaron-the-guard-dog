"""
Enroll your voice for voice-activated wake.

Usage:
    python enroll_voice.py

Say the wake phrase ("Wake up Aaron") several times when prompted - each
one gets transcribed (to confirm it heard the phrase) and turned into a
voice embedding, saved to voice_profile.json. Run voice_wake.py afterward.
"""

import json
import queue
import sys
import sounddevice as sd

from voice_engine import (
    load_vosk_model, create_recognizer, create_voice_encoder,
    compute_embedding, save_voice_profile, find_input_device, SAMPLE_RATE,
)

NUM_SAMPLES = 6


def record_one_utterance(recognizer, audio_queue):
    """Blocks until Vosk detects a complete utterance (speech then silence).
    Returns (text, raw_audio_bytes)."""
    recognizer.Reset()
    utterance_audio = bytearray()
    while True:
        data = audio_queue.get()
        utterance_audio.extend(data)
        if recognizer.AcceptWaveform(bytes(data)):
            result = json.loads(recognizer.Result())
            return result.get("text", ""), bytes(utterance_audio)


def main():
    print("Loading speech model...")
    model = load_vosk_model()
    recognizer = create_recognizer(model)
    print("Loading voice encoder...")
    encoder = create_voice_encoder()

    audio_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_queue.put(bytes(indata))

    embeddings = []

    device = find_input_device()
    print(f"Using input device: {sd.query_devices(device)['name'] if device is not None else 'system default'}")
    print(f'\nSay "Wake up Aaron" clearly when you see "Listening..." - need {NUM_SAMPLES} good samples.')
    print("Speak, then pause - it detects the end of your sentence automatically.\n")

    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype='int16',
                                channels=1, device=device, callback=callback):
            while len(embeddings) < NUM_SAMPLES:
                print(f"[{len(embeddings)}/{NUM_SAMPLES}] Listening...")
                text, audio = record_one_utterance(recognizer, audio_queue)

                if not text.strip():
                    print("  (didn't catch anything, try again)")
                    continue

                print(f'  Heard: "{text}"')
                embedding = compute_embedding(encoder, audio)
                if embedding is None:
                    print("  (too quiet/short, try again)")
                    continue

                embeddings.append(embedding)
                print(f"  Saved sample {len(embeddings)}/{NUM_SAMPLES}\n")
    except KeyboardInterrupt:
        pass
    except sd.PortAudioError as e:
        print(f"Microphone error: {e}")
        sys.exit(1)

    if not embeddings:
        print("No samples captured.")
        return

    save_voice_profile(embeddings)
    print(f"Done. Saved {len(embeddings)} voice samples to voice_profile.json")


if __name__ == "__main__":
    main()
