"""
Custom hand-gesture matching by comparing normalized hand-landmark shapes -
a lightweight DIY alternative to MediaPipe's official gesture training tool
(Model Maker), which needs TensorFlow and has no Python 3.14 build yet.

A "shape" here is the 21 hand landmarks translated so the wrist is the
origin and scaled by wrist-to-middle-knuckle distance, so the same gesture
matches regardless of hand distance/position in frame. Matching is nearest-
neighbor: compare a live shape to every saved example of every gesture and
take the closest one (Euclidean distance - lower means more similar).
"""

import json
import numpy as np

WRIST = 0
MIDDLE_MCP = 9  # middle finger's base knuckle - used as the scale reference

DEFAULT_DISTANCE_THRESHOLD = 0.4  # starting guess - tune based on observed distances


def landmarks_to_vector(hand_landmarks):
    """hand_landmarks: MediaPipe's list of 21 landmarks (each with .x/.y/.z).
    Returns a flat, translation- and scale-normalized numpy vector.

    Deliberately drops z (depth) - MediaPipe's single-camera depth estimate
    is noisy frame-to-frame in a way that swamped the actual 2D hand shape,
    making even the same gesture look far from itself in distance terms."""
    pts = np.array([[lm.x, lm.y] for lm in hand_landmarks], dtype=np.float64)
    pts -= pts[WRIST]
    scale = np.linalg.norm(pts[MIDDLE_MCP])
    if scale < 1e-6:
        scale = 1e-6
    pts /= scale
    return pts.flatten()


def load_gesture_model(path):
    """Loads gesture_model.json into {name: [np.ndarray, ...]}."""
    with open(path) as f:
        raw = json.load(f)
    return {name: [np.array(v, dtype=np.float64) for v in vectors] for name, vectors in raw.items()}


def best_gesture_match(vector, gesture_model):
    """Returns (name, distance) of the closest saved example across all
    gestures, or (None, inf) if the model is empty."""
    best_name, best_dist = None, float("inf")
    for name, examples in gesture_model.items():
        for example in examples:
            dist = float(np.linalg.norm(vector - example))
            if dist < best_dist:
                best_name, best_dist = name, dist
    return best_name, best_dist
