"""
Step 3: Live face recognition from the webcam using the trained model.

Usage:
    python recognize.py

Press 'q' to quit.
"""

import os
from collections import deque, Counter
import cv2

from face_engine import (
    create_detector, create_recognizer, detect_largest_face, get_embedding,
    load_embeddings, best_match, DEFAULT_COSINE_THRESHOLD,
)

import paths

EMBEDDINGS_PATH = paths.private("model_embeddings.json")

# SFace cosine similarity: HIGHER means a more confident match (opposite of
# the old LBPH "distance"). Tune this if you get false positives/negatives.
COSINE_THRESHOLD = DEFAULT_COSINE_THRESHOLD

# Smooth the displayed label over a short window of frames instead of
# trusting each frame in isolation - a single frame is prone to flicker
# from motion blur or a slightly off angle.
SMOOTHING_WINDOW = 10
SMOOTHING_MIN_AGREEMENT = 6  # of the last SMOOTHING_WINDOW frames

# A single missed detection (blink, motion blur, brief bad angle) is normal
# - don't wipe the smoothing window until the face has actually been gone
# for a while.
MISS_GRACE_FRAMES = 10


def main():
    try:
        known_embeddings = load_embeddings(EMBEDDINGS_PATH)
    except FileNotFoundError:
        print(f"'{EMBEDDINGS_PATH}' not found. Run capture_faces.py then train_model.py first.")
        return

    detector = create_detector()
    recognizer = create_recognizer()

    cam = cv2.VideoCapture(0, cv2.CAP_MSMF)
    if not cam.isOpened():
        print("Could not open webcam")
        return

    ok, _ = cam.read()
    if not ok:
        print("Could not read from the webcam - it's likely already in use.")
        print("If Aaron (guard_watch.py) is running, stop him first: run.bat -> option 7, or stop_guard.bat")
        cam.release()
        return

    print("Running. Press 'q' to quit.")

    recent_labels = deque(maxlen=SMOOTHING_WINDOW)
    miss_streak = 0

    while True:
        ok, frame = cam.read()
        if not ok:
            break

        face = detect_largest_face(detector, frame)

        if face is not None:
            miss_streak = 0
            x, y, w, h = int(face[0]), int(face[1]), int(face[2]), int(face[3])
            feature, _aligned = get_embedding(recognizer, frame, face)
            best_name, score = best_match(recognizer, feature, known_embeddings)

            raw_name = best_name if best_name and score >= COSINE_THRESHOLD else "Unknown"
            recent_labels.append(raw_name)

            # Only display a name once it has a clear majority in the recent
            # window; otherwise show "..." rather than flicker between guesses.
            most_common, count = Counter(recent_labels).most_common(1)[0]
            if count >= SMOOTHING_MIN_AGREEMENT:
                name = most_common
            else:
                name = "..."

            color = (0, 255, 0) if name not in ("Unknown", "...") else (0, 0, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, f"{name} ({score:.2f})", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        else:
            miss_streak += 1
            if miss_streak >= MISS_GRACE_FRAMES:
                recent_labels.clear()

        cv2.imshow("Face recognition - press q to quit", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
