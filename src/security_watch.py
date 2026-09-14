"""
Watches the webcam and sends a Telegram alert (with a photo) whenever an
UNRECOGNIZED face is detected - useful as a simple "who's at my desk/door"
security ping.

Setup:
    1. Fill in telegram_config.json with your real bot token + chat id.
    2. Make sure model_embeddings.json exists (run capture_faces.py then
       train_model.py first).

Usage:
    python security_watch.py

Press 'q' (with the preview window focused) to quit.
"""

import json
import os
import time
from collections import deque, Counter
import cv2
import requests

from face_engine import (
    create_detector, create_recognizer, detect_largest_face, get_embedding,
    load_embeddings, best_match, DEFAULT_COSINE_THRESHOLD,
)

import paths

EMBEDDINGS_PATH = paths.private("model_embeddings.json")
CONFIG_PATH = paths.private("telegram_config.json")

COSINE_THRESHOLD = DEFAULT_COSINE_THRESHOLD
SMOOTHING_WINDOW = 10
SMOOTHING_MIN_AGREEMENT = 6
MISS_GRACE_FRAMES = 10

# Send at most one alert this often while the SAME unknown presence lingers,
# so it doesn't spam you every frame someone unrecognized is in view.
ALERT_COOLDOWN_SECONDS = 300


def load_telegram_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    if not config.get("bot_token") or "PASTE" in config["bot_token"]:
        raise RuntimeError(f"Fill in your real bot token and chat_id in {CONFIG_PATH} first.")
    return config["bot_token"], config["chat_id"]


def send_telegram_photo(bot_token, chat_id, frame, caption):
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    files = {"photo": ("alert.jpg", buf.tobytes(), "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    try:
        resp = requests.post(url, data=data, files=files, timeout=10)
        if not resp.ok:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        print(f"Telegram send error: {e}")


def main():
    try:
        bot_token, chat_id = load_telegram_config()
    except (FileNotFoundError, RuntimeError) as e:
        print(e)
        return

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

    print("Watching. Press 'q' to quit.")

    recent_labels = deque(maxlen=SMOOTHING_WINDOW)
    miss_streak = 0
    last_alert_time = 0.0
    currently_unknown = False

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

            most_common, count = Counter(recent_labels).most_common(1)[0]
            name = most_common if count >= SMOOTHING_MIN_AGREEMENT else "..."

            color = (0, 255, 0) if name not in ("Unknown", "...") else (0, 0, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, f"{name} ({score:.2f})", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            if name == "Unknown":
                now = time.time()
                if not currently_unknown or (now - last_alert_time) >= ALERT_COOLDOWN_SECONDS:
                    send_telegram_photo(bot_token, chat_id, frame, "🐕 WOOF WOOF! Aaron spotted someone unrecognized on webcam.")
                    last_alert_time = now
                    print("[Aaron] Alert sent.")
                currently_unknown = True
            elif name != "...":
                currently_unknown = False
        else:
            miss_streak += 1
            if miss_streak >= MISS_GRACE_FRAMES:
                recent_labels.clear()
                currently_unknown = False

        cv2.imshow("Security watch - press q to quit", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
