"""
Shared face detection + recognition engine used by capture/train/recognize/
guard scripts. Replaces the old Haar cascade + LBPH pipeline with OpenCV's
YuNet (detector) + SFace (recognizer) - modern embedding-based models that
generalize far better across distance, lighting, and angle than LBPH's
texture-histogram matching did.

Cosine similarity is used for matching: HIGHER score = more similar
(opposite of LBPH's "distance", which was lower = better - keep this in
mind when reading any code migrated from the old pipeline).
"""

import os
import cv2
import numpy as np

import paths

DETECTOR_MODEL_PATH = paths.misc("face_detection_yunet_2023mar.onnx")
RECOGNIZER_MODEL_PATH = paths.misc("face_recognition_sface_2021dec.onnx")

# OpenCV's documented recommended threshold for SFace cosine similarity.
# Higher score = more similar. Tune if you get false accepts/rejects.
DEFAULT_COSINE_THRESHOLD = 0.363

DETECT_SCORE_THRESHOLD = 0.7


def create_detector(frame_size=(320, 320)):
    return cv2.FaceDetectorYN_create(
        DETECTOR_MODEL_PATH, "", frame_size, score_threshold=DETECT_SCORE_THRESHOLD,
    )


def create_recognizer():
    return cv2.FaceRecognizerSF_create(RECOGNIZER_MODEL_PATH, "")


def detect_largest_face(detector, frame):
    """Returns YuNet's raw face row (box + 5 landmarks + score), or None."""
    h, w = frame.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(frame)
    if faces is None or len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def get_embedding(recognizer, frame, face):
    aligned = recognizer.alignCrop(frame, face)
    return recognizer.feature(aligned), aligned


def cosine_score(recognizer, feature_a, feature_b):
    return recognizer.match(feature_a, feature_b, cv2.FaceRecognizerSF_FR_COSINE)


def best_match(recognizer, feature, known_embeddings):
    """known_embeddings: {name: [np.ndarray(1,128), ...]}
    Returns (best_name, best_score) - best_score is -1 if nothing known."""
    best_name, best_score = None, -1.0
    for name, embeddings in known_embeddings.items():
        for ref in embeddings:
            score = cosine_score(recognizer, feature, ref)
            if score > best_score:
                best_name, best_score = name, score
    return best_name, best_score


def load_embeddings(path):
    """Loads model_embeddings.json into {name: [np.ndarray(1,128), ...]}."""
    import json
    with open(path) as f:
        raw = json.load(f)
    return {
        name: [np.array(vec, dtype=np.float32).reshape(1, -1) for vec in vectors]
        for name, vectors in raw.items()
    }
