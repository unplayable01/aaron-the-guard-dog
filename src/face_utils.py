"""Shared face preprocessing so capture, training, and recognition all treat images identically."""

import cv2

FACE_SIZE = (200, 200)


def preprocess_face(gray_face):
    """Resize + histogram-equalize a grayscale face crop.

    Equalization normalizes lighting/contrast, which LBPH is sensitive to -
    without it, the same face under different lighting can look like a
    different person to the recognizer.
    """
    face = cv2.resize(gray_face, FACE_SIZE)
    face = cv2.equalizeHist(face)
    return face
