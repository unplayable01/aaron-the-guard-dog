"""
Shared voice engine: offline speech-to-text (Vosk) to detect the wake
phrase, plus actual speaker verification (Resemblyzer voice embeddings) to
confirm it's specifically YOUR voice saying it - not just anyone. Same
"enrolled examples + similarity threshold" pattern used for faces and
gestures elsewhere in this project, just for voice.

Audio never leaves the machine - Vosk is a fully offline model.
"""

import json
import os
import numpy as np
import sounddevice as sd
import vosk

# Match by name, not index - device indices shift around when Bluetooth
# devices connect/disconnect, but the name stays stable.
INPUT_DEVICE_NAME = "Microphone Array"


def find_input_device(name_substring=INPUT_DEVICE_NAME):
    for i, d in enumerate(sd.query_devices()):
        if name_substring.lower() in d["name"].lower() and d["max_input_channels"] > 0:
            return i
    return None  # fall back to system default if not found

import paths

VOSK_MODEL_PATH = paths.misc("vosk-model-small-en-us-0.15")
VOICE_PROFILE_PATH = paths.private("voice_profile.json")

SAMPLE_RATE = 16000

# Cosine similarity between voice embeddings: higher = more similar.
# Starting guess, like every other threshold in this project - tune based
# on what you see logged during real testing.
DEFAULT_SPEAKER_THRESHOLD = 0.75

vosk.SetLogLevel(-1)  # silence Vosk's own console spam


def load_vosk_model():
    return vosk.Model(VOSK_MODEL_PATH)


def create_recognizer(model):
    recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
    recognizer.SetWords(False)
    return recognizer


def create_voice_encoder():
    from resemblyzer import VoiceEncoder
    return VoiceEncoder()


def audio_bytes_to_float(raw_bytes):
    """int16 PCM bytes -> float32 waveform in [-1, 1], what resemblyzer expects."""
    return np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def compute_embedding(encoder, raw_audio_bytes):
    from resemblyzer import preprocess_wav
    wav = audio_bytes_to_float(raw_audio_bytes)
    processed = preprocess_wav(wav, source_sr=SAMPLE_RATE)
    if len(processed) == 0:
        return None
    return encoder.embed_utterance(processed)


def cosine_similarity(a, b):
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-9:
        return 0.0
    return float(np.dot(a, b) / denom)


def best_speaker_similarity(embedding, profile_embeddings):
    if embedding is None or not profile_embeddings:
        return 0.0
    return max(cosine_similarity(embedding, ref) for ref in profile_embeddings)


def load_voice_profile(path=VOICE_PROFILE_PATH):
    with open(path) as f:
        raw = json.load(f)
    return [np.array(v, dtype=np.float32) for v in raw]


def save_voice_profile(embeddings, path=VOICE_PROFILE_PATH):
    with open(path, "w") as f:
        json.dump([e.tolist() for e in embeddings], f)


def phrase_matches(text, wake_words):
    """Fuzzy match: Vosk's small model can mishear a name/word here and
    there, so require most (not all) of the wake phrase's words to appear,
    rather than an exact string match."""
    text = text.lower()
    heard = text.split()
    hits = sum(1 for w in wake_words if w in heard)
    return hits >= max(1, len(wake_words) - 1)
