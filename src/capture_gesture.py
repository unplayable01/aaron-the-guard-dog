"""
Capture examples of a custom hand gesture.

Usage:
    python capture_gesture.py <gesture_name>

Hold your gesture steady in front of the camera - saves normalized hand-
shape samples to gesture_dataset/<gesture_name>/*.json. Run train_gestures.py
afterward to fold them into gesture_model.json, then map the gesture to an
action in gesture_actions.json.

Press 'q' to stop early.
"""

import sys
import os
import json
import cv2

from gesture import create_gesture_recognizer, recognize_full
from hand_shape import landmarks_to_vector

import paths

DATASET_DIR = paths.private("gesture_dataset")
NUM_SAMPLES = 30
SAVE_COOLDOWN = 4  # skip this many frames between saves for a bit of natural variety


def main():
    if len(sys.argv) != 2:
        print("Usage: python capture_gesture.py <gesture_name>")
        sys.exit(1)

    name = sys.argv[1]
    save_dir = os.path.join(DATASET_DIR, name)
    os.makedirs(save_dir, exist_ok=True)

    recognizer = create_gesture_recognizer()

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

    print(f"Capturing {NUM_SAMPLES} samples of gesture '{name}'.")
    print("Hold your hand gesture steady and in frame. Press 'q' to stop early.")

    count = 0
    frames_since_save = 0

    while count < NUM_SAMPLES:
        ok, frame = cam.read()
        if not ok:
            break

        frames_since_save += 1
        result = recognize_full(recognizer, frame)

        if result.hand_landmarks:
            hand = result.hand_landmarks[0]
            h, w = frame.shape[:2]
            for lm in hand:
                cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 3, (255, 255, 0), -1)

            if frames_since_save >= SAVE_COOLDOWN:
                count += 1
                frames_since_save = 0
                vector = landmarks_to_vector(hand)
                with open(os.path.join(save_dir, f"{count}.json"), "w") as f:
                    json.dump(vector.tolist(), f)

        cv2.putText(frame, f"Samples: {count}/{NUM_SAMPLES}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Capturing gesture - press q to stop", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()
    print(f"Done. Saved {count} samples to {save_dir}")
    if count == 0:
        print("No hand was detected in any frame - make sure your hand is clearly "
              "in view and well lit, then try again.")


if __name__ == "__main__":
    main()
