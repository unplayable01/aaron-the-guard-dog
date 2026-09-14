"""
Step 1: Capture face images from the webcam for training.

Usage:
    python capture_faces.py <name>

Saves aligned face crops to dataset/<name>/*.jpg, ready for SFace embedding
extraction in train_model.py. Cycles through poses (straight/left/right/up/
down) and only saves a sample when your head pose - estimated from facial
landmarks - actually matches the current prompt. Press 'q' to stop early.
"""

import sys
import os
import cv2
import numpy as np

from face_engine import create_detector, create_recognizer, detect_largest_face, get_embedding
from head_pose import estimate_pose

import paths

LANDMARK_MODEL_PATH = paths.misc("lbfmodel.yaml")
DATASET_DIR = paths.private("dataset")

SAMPLES_PER_POSE = 30
SAVE_COOLDOWN = 5  # skip this many frames between saves to avoid near-duplicate/blurry captures

# yaw/pitch thresholds in degrees a pose must cross to count as "held".
# If LEFT/RIGHT or UP/DOWN feel backwards on your setup, flip the sign in
# the matching lambda below - camera/landmark sign conventions vary.
YAW_TURN = 15
PITCH_TILT = 12

# label, check(yaw, pitch) -> bool
POSES = [
    ("Look STRAIGHT at the camera", lambda yaw, pitch: abs(yaw) <= 10 and abs(pitch) <= 10),
    ("Turn your head LEFT", lambda yaw, pitch: yaw >= YAW_TURN),
    ("Turn your head RIGHT", lambda yaw, pitch: yaw <= -YAW_TURN),
    ("Tilt your head UP", lambda yaw, pitch: pitch >= PITCH_TILT),
    ("Tilt your head DOWN", lambda yaw, pitch: pitch <= -PITCH_TILT),
]
NUM_SAMPLES = SAMPLES_PER_POSE * len(POSES)


def main():
    if len(sys.argv) != 2:
        print("Usage: python capture_faces.py <name>")
        sys.exit(1)

    name = sys.argv[1]
    save_dir = os.path.join(DATASET_DIR, name)
    os.makedirs(save_dir, exist_ok=True)

    detector = create_detector()
    recognizer = create_recognizer()

    landmark_detector = cv2.face.createFacemarkLBF()
    try:
        landmark_detector.loadModel(LANDMARK_MODEL_PATH)
    except cv2.error:
        print(f"Could not load landmark model from {LANDMARK_MODEL_PATH}")
        sys.exit(1)

    cam = cv2.VideoCapture(0, cv2.CAP_MSMF)
    if not cam.isOpened():
        print("Could not open webcam")
        sys.exit(1)

    ok, _ = cam.read()
    if not ok:
        print("Could not read from the webcam - it's likely already in use.")
        print("If Aaron (guard_watch.py) is running, stop him first: run.bat -> option 7, or stop_guard.bat")
        cam.release()
        sys.exit(1)

    print(f"Capturing {NUM_SAMPLES} face images for '{name}' ({SAMPLES_PER_POSE} per pose).")
    print("Keep your WHOLE face in frame.")
    print("Hold each pose when prompted - it only captures once your pose matches.")
    print("Press 'q' to stop early.")

    count = 0
    pose_index = 0
    pose_count = 0
    frames_since_save = 0

    while pose_index < len(POSES):
        ok, frame = cam.read()
        if not ok:
            break

        frames_since_save += 1
        face = detect_largest_face(detector, frame)

        pose_label, pose_check = POSES[pose_index]
        pose_matched = False
        yaw = pitch = None

        if face is not None:
            x, y, w, h = int(face[0]), int(face[1]), int(face[2]), int(face[3])
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face_rects = np.array([[x, y, w, h]], dtype=np.int32)
            fit_ok, landmark_sets = landmark_detector.fit(gray, face_rects)

            if fit_ok:
                landmarks = landmark_sets[0].reshape(-1, 2)
                pose = estimate_pose(landmarks, frame.shape)
                if pose is not None:
                    pitch, yaw, _roll = pose
                    pose_matched = pose_check(yaw, pitch)

                for (lx, ly) in landmarks:
                    cv2.circle(frame, (int(lx), int(ly)), 1, (255, 255, 0), -1)

            if pose_matched and frames_since_save >= SAVE_COOLDOWN:
                count += 1
                pose_count += 1
                frames_since_save = 0
                _feature, aligned = get_embedding(recognizer, frame, face)
                cv2.imwrite(os.path.join(save_dir, f"{count}.jpg"), aligned)

                if pose_count >= SAMPLES_PER_POSE:
                    pose_index += 1
                    pose_count = 0

        status_color = (0, 255, 0) if pose_matched else (0, 165, 255)
        cv2.putText(frame, f"Samples: {count}/{NUM_SAMPLES}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, pose_label, (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        if yaw is not None:
            cv2.putText(frame, f"yaw={yaw:.0f} pitch={pitch:.0f} {'MATCH' if pose_matched else ''}",
                        (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 1)

        cv2.imshow("Capturing faces - press q to stop", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()
    print(f"Done. Saved {count} images to {save_dir}")


if __name__ == "__main__":
    main()
