"""
Hand gesture recognition via MediaPipe's pretrained GestureRecognizer.
Classifies: Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up,
Victory, ILoveYou, or None (no recognized gesture).
"""

import os
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

import paths

MODEL_PATH = paths.misc("gesture_recognizer.task")


def create_gesture_recognizer():
    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.GestureRecognizerOptions(base_options=base_options, num_hands=1)
    return vision.GestureRecognizer.create_from_options(options)


def recognize_full(recognizer, frame_bgr):
    """Runs the model once and returns the raw result - has BOTH the
    built-in gesture classification (result.gestures) and the raw 21-point
    hand landmarks (result.hand_landmarks), so callers needing both don't
    pay for two inference passes."""
    rgb = frame_bgr[:, :, ::-1]  # BGR -> RGB, no copy needed for read-only use
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    return recognizer.recognize(mp_image)


def top_gesture(result):
    """Returns (gesture_name, score) for the top built-in gesture, or (None, 0.0)."""
    if not result.gestures:
        return None, 0.0
    top = result.gestures[0][0]
    return top.category_name, top.score


def recognize_gesture(recognizer, frame_bgr):
    """Convenience one-shot version of recognize_full + top_gesture."""
    return top_gesture(recognize_full(recognizer, frame_bgr))
