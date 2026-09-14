"""Head pose (pitch/yaw/roll) estimation from 68-point facial landmarks.

Uses a generic 3D face model + solvePnP - the standard approach for
webcam head pose estimation without any depth sensor.
"""

import cv2
import numpy as np

# Generic 3D face landmark positions (arbitrary units, not millimeters of a
# real face - only relative geometry matters for solvePnP).
_MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),           # Nose tip        -> landmark 30
    (0.0, -330.0, -65.0),      # Chin            -> landmark 8
    (-225.0, 170.0, -135.0),   # Left eye corner -> landmark 36
    (225.0, 170.0, -135.0),    # Right eye corner-> landmark 45
    (-150.0, -150.0, -125.0),  # Left mouth corner  -> landmark 48
    (150.0, -150.0, -125.0),   # Right mouth corner -> landmark 54
], dtype=np.float64)

_LANDMARK_INDICES = [30, 8, 36, 45, 48, 54]


def estimate_pose(landmarks, frame_shape):
    """Return (pitch, yaw, roll) in degrees, or None if pose can't be solved.

    landmarks: (68, 2) array of 2D points from Facemark LBF.
    frame_shape: shape of the frame the landmarks were detected in.
    """
    h, w = frame_shape[:2]
    image_points = np.array([landmarks[i] for i in _LANDMARK_INDICES], dtype=np.float64)

    focal_length = w
    center = (w / 2, h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1],
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))

    ok, rotation_vec, translation_vec = cv2.solvePnP(
        _MODEL_POINTS, image_points, camera_matrix, dist_coeffs
    )
    if not ok:
        return None

    rotation_mat, _ = cv2.Rodrigues(rotation_vec)
    pose_mat = cv2.hconcat((rotation_mat, translation_vec))
    _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)
    pitch, yaw, roll = euler_angles.flatten()
    pitch, yaw, roll = float(pitch), float(yaw), float(roll)

    # decomposeProjectionMatrix can report pitch on the wrong side of +-90;
    # this is the standard correction used in most head-pose tutorials.
    if pitch < -90:
        pitch = -(180 + pitch)
    elif pitch > 90:
        pitch = 180 - pitch

    return pitch, yaw, roll
