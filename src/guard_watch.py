"""
Headless intrusion guard: watches the webcam in the background (no window).
When it sees a face that doesn't confidently match a trained person, it
reacts in one of two ways depending on how close the nearest match is:
  - resembles a trained person somewhat (score >= TRIAGE_FLOOR) - asks via
    Telegram buttons first, in case it's really you/someone trained under
    bad lighting/angle.
  - doesn't resemble anyone trained at all (score < TRIAGE_FLOOR) - locks
    instantly, no waiting - this is someone never captured by the system.
Meant to be launched via pythonw.exe (no console) so nothing visible
appears on screen.

Remote-controllable from Telegram (only the chat_id in telegram_config.json
is trusted - messages from anyone else are ignored):
    /sit      - pause guarding (e.g. a friend is sitting next to you)
    /guard    - resume guarding
    /status   - check whether Aaron is guarding or resting
    /snapshot - get a photo of what the camera currently sees
    /watch    - pseudo-live view: refreshes a photo every ~2s for up to 2 min
    /stopwatch- end an active /watch session early
    /lock     - lock the PC right now, regardless of guard state
    /help     - list commands

Also responds to a hand gesture: hold an open palm up to the camera for
about 1.5 seconds and Aaron goes fully to sleep (process exits, same as
sending /sleep to the listener) - works whether or not he's currently armed.

On top of that, custom gestures you define yourself (see capture_gesture.py
+ train_gestures.py) can be mapped in gesture_actions.json to any of:
sleep, lock, snapshot, sit, guard - same actions as the Telegram commands.

The camera keeps running while the PC is locked (it needs to, to know when
things change), but stranger alerts go quiet while already locked - there's
no point re-alerting on an already-secured PC. The moment it's unlocked
again, Aaron sends exactly one message with a photo of who's there.

Setup: same as security_watch.py - telegram_config.json must be filled in,
and model_embeddings.json must exist (run capture_faces.py + train_model.py
first). Only trained/known faces are treated as "you" - anyone else trips it.

There is no on-screen UI; see stop_guard.bat to stop it, or Task Manager ->
End Task on pythonw.exe.
"""

import ctypes
import json
import os
import subprocess
import threading
import time
import wave
from datetime import datetime
import cv2
import numpy as np
import requests
import sounddevice as sd

from face_engine import (
    create_detector, create_recognizer, detect_largest_face, get_embedding,
    load_embeddings, best_match, DEFAULT_COSINE_THRESHOLD,
)
from gesture import create_gesture_recognizer, recognize_full, top_gesture
from hand_shape import landmarks_to_vector, load_gesture_model, best_gesture_match, DEFAULT_DISTANCE_THRESHOLD
import paths

EMBEDDINGS_PATH = paths.private("model_embeddings.json")
CONFIG_PATH = paths.private("telegram_config.json")
LOG_PATH = paths.log_file("guard_watch.log")
GESTURE_MODEL_PATH = paths.private("gesture_model.json")
GESTURE_ACTIONS_PATH = paths.private("gesture_actions.json")
GUARD_COMMAND_PATH = paths.private("guard_command.json")
EVIDENCE_DIR = paths.private("evidence")
ALARM_PATH = paths.misc("alarm.wav")

# winsound only plays through whatever Windows' CURRENT DEFAULT output
# device is - on this machine that's Bluetooth earbuds, silent if they're
# not being worn. sounddevice lets us target a specific device by name
# instead, same fix as the microphone in voice_engine.py.
OUTPUT_DEVICE_NAME = "Speakers (2- Realtek"


def find_output_device(name_substring=OUTPUT_DEVICE_NAME):
    for i, d in enumerate(sd.query_devices()):
        if name_substring.lower() in d["name"].lower() and d["max_output_channels"] > 0:
            return i
    return None  # fall back to system default if not found


def play_alarm():
    try:
        with wave.open(ALARM_PATH, "rb") as wf:
            n_channels = wf.getnchannels()
            framerate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels > 1:
            audio = audio.reshape(-1, n_channels)
        sd.play(audio, framerate, device=find_output_device())
    except Exception as e:
        log(f"Alarm playback error: {e}")

COSINE_THRESHOLD = DEFAULT_COSINE_THRESHOLD

# Lock fast: this many CONSECUTIVE frames classified as an unrecognized face
# (not a rolling majority) before triggering. A false lock just costs you
# re-entering your password; a missed intrusion is the worse failure mode,
# so this is intentionally quicker/more sensitive than recognize.py's display.
UNKNOWN_TRIGGER_FRAMES = 3

# Don't re-send an alert / re-issue a lock more than once this often while
# an unrecognized presence keeps being seen (e.g. someone repeatedly retrying).
ALERT_COOLDOWN_SECONDS = 60

# Instead of locking instantly, ask via Telegram buttons first - gives you a
# chance to wave off a false alarm (a friend, family member you haven't
# trained). No response within this many seconds and it locks anyway - the
# fail-safe default is still "lock", not "do nothing".
TRIAGE_GRACE_SECONDS = 10

# Below COSINE_THRESHOLD, the face isn't a confirmed match - but nearest-
# neighbor matching always returns SOME closest trained person and score,
# even for a total stranger. TRIAGE_FLOOR splits that range in two:
#   score >= TRIAGE_FLOOR : resembles a trained person somewhat -> ask via
#       triage (could be you/a trained person under bad lighting/angle)
#   score <  TRIAGE_FLOOR : doesn't resemble anyone trained -> lock
#       instantly, no triage (this is someone never captured at all)
# Set conservatively low: testing showed YOUR OWN face under bad lighting
# can score as low as 0.1-0.3 and still genuinely be you - if this floor
# sits above that, your own bad-lighting frames would instant-lock instead
# of getting the triage chance. Watch the logged scores on real strangers
# (once you've trained more than one person) and raise this only if you
# see a clean gap, the same way every other threshold here was tuned.
TRIAGE_FLOOR = 0.05

# Right after unlocking, your hands are near the keyboard/trackpad entering
# your password - observed in testing to sometimes accidentally satisfy a
# loosely-tuned custom gesture. Ignore gesture triggers for a few seconds
# after any unlock, real or not, rather than re-tightening the gesture
# itself (which would undo the usability tuning you asked for).
GESTURE_POST_UNLOCK_GRACE_SECONDS = 10

# Windows can suspend the camera when the workstation locks; some backends
# (DirectShow in particular) feed garbage/static frames after unlock instead
# of recovering cleanly. Real frames have spatial correlation between
# neighboring pixels - pure static doesn't - so a very high Laplacian
# variance is a reliable "this frame is garbage" signal. If it persists for
# several frames in a row, close and reopen the camera to force a clean
# reconnect to the Frame Server.
STATIC_FRAME_VARIANCE = 8000
STATIC_FRAME_TRIGGER = 10


def looks_like_static(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var() > STATIC_FRAME_VARIANCE


CREATE_NO_WINDOW = 0x08000000

# How often to check whether the workstation is actually locked - cheap
# enough (spawns tasklist) to poll every second or two without any real cost.
LOCK_POLL_SECONDS = 1.5


def is_workstation_locked():
    """Windows doesn't expose lock state via a simple call without pywin32,
    but LogonUI.exe (the lock/login screen UI) only runs while the session
    is actually locked - checking for it is a well-known, dependency-free
    way to detect lock state."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq LogonUI.exe"],
            capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW,
        )
        return "LogonUI.exe" in result.stdout
    except (subprocess.SubprocessError, OSError):
        return False

# Hold an open palm up for this many consecutive frames (~10fps loop, so
# ~1.5s) to send Aaron to sleep. Change SLEEP_GESTURE to "Closed_Fist",
# "Thumb_Down", "Victory", etc. if Open_Palm triggers by accident.
SLEEP_GESTURE = "Open_Palm"
GESTURE_SCORE_THRESHOLD = 0.6
GESTURE_HOLD_FRAMES = 15

# Same hold-time idea, but for custom gestures matched by hand-shape
# distance (lower = more similar). Live-measured with real data: actually
# holding the trained gesture clusters around 1.0-1.6; NOT holding it
# (hand relaxed/moving between attempts) jumps to 6-10 - a huge, clean
# gap. 1.8 sits in that gap with margin on both sides. The 15-frame hold
# requirement (leaky, see below) is the real defense against an incidental
# hand-in-frame accidentally triggering this.
CUSTOM_GESTURE_DISTANCE = 1.8
# 15 measured out to ~6s of real holding in testing (leaky-streak accrual
# is slower than raw loop fps suggests) - scaled down for a ~2s hold.
CUSTOM_GESTURE_HOLD_FRAMES = 5

VALID_GESTURE_ACTIONS = {"sleep", "lock", "snapshot", "sit", "guard"}

# /watch: refresh the same Telegram message with a new photo this often,
# for at most this long, so it can't run forever if you forget /stopwatch.
WATCH_REFRESH_SECONDS = 2.0
WATCH_MAX_DURATION_SECONDS = 120


def load_gesture_actions():
    """Optional feature - returns ({}, None) if no custom gestures are set up."""
    try:
        gesture_model = load_gesture_model(GESTURE_MODEL_PATH)
    except FileNotFoundError:
        return {}, None
    try:
        with open(GESTURE_ACTIONS_PATH) as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}, None

    actions = {
        name: action for name, action in raw.items()
        if action in VALID_GESTURE_ACTIONS and name in gesture_model
    }
    return actions, gesture_model


def log(message):
    line = f"{datetime.now().isoformat(timespec='seconds')} [Aaron] {message}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def save_evidence(category, frame, note=""):
    """Saves a local timestamped copy of a security-relevant photo - a
    record that survives even if Telegram's chat history, your phone
    battery, or connectivity doesn't. category e.g. "stranger"/"unlock",
    organized by day so it's easy to browse without scrolling a chat."""
    now = datetime.now()
    day_dir = os.path.join(EVIDENCE_DIR, now.strftime("%Y-%m-%d"))
    try:
        os.makedirs(day_dir, exist_ok=True)
        filename = f"{now.strftime('%H-%M-%S')}_{category}"
        if note:
            safe_note = "".join(c if c.isalnum() else "_" for c in note)[:40]
            filename += f"_{safe_note}"
        path = os.path.join(day_dir, f"{filename}.jpg")
        cv2.imwrite(path, frame)
        return path
    except OSError as e:
        log(f"Evidence save failed: {e}")
        return None


def load_telegram_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    if not config.get("bot_token") or "PASTE" in config["bot_token"]:
        raise RuntimeError(f"Fill in your real bot token and chat_id in {CONFIG_PATH} first.")
    return config["bot_token"], str(config["chat_id"])


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
            log(f"Telegram send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram send error: {e}")


def send_telegram_photo_with_buttons(bot_token, chat_id, frame, caption, buttons):
    """buttons: list of (label, callback_data) tuples, one row."""
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    reply_markup = json.dumps({
        "inline_keyboard": [[{"text": label, "callback_data": data} for label, data in buttons]],
    })
    files = {"photo": ("triage.jpg", buf.tobytes(), "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption, "reply_markup": reply_markup}
    try:
        resp = requests.post(url, data=data, files=files, timeout=10)
        if not resp.ok:
            log(f"Telegram send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram send error: {e}")


def send_telegram_message(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
        if not resp.ok:
            log(f"Telegram send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram send error: {e}")


def send_telegram_photo_get_id(bot_token, chat_id, frame, caption):
    """Like send_telegram_photo, but returns the sent message's id (or None)
    so a later call can edit that SAME message instead of sending new ones."""
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return None
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    files = {"photo": ("watch.jpg", buf.tobytes(), "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    try:
        resp = requests.post(url, data=data, files=files, timeout=10)
        if resp.ok:
            return resp.json()["result"]["message_id"]
        log(f"Telegram send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram send error: {e}")
    return None


def edit_telegram_photo(bot_token, chat_id, message_id, frame, caption):
    """Replaces an existing message's photo in place - this is what makes
    /watch feel like a refreshing live view instead of a flood of messages."""
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/editMessageMedia"
    media = json.dumps({"type": "photo", "media": "attach://watch.jpg", "caption": caption})
    files = {"watch.jpg": ("watch.jpg", buf.tobytes(), "image/jpeg")}
    data = {"chat_id": chat_id, "message_id": message_id, "media": media}
    try:
        resp = requests.post(url, data=data, files=files, timeout=10)
        if not resp.ok:
            log(f"Telegram edit failed: {resp.status_code} {resp.text}")
        return resp.ok
    except requests.RequestException as e:
        log(f"Telegram edit error: {e}")
        return False


def lock_windows():
    ctypes.windll.user32.LockWorkStation()


def run_gesture_action(action, gesture_name, bot_token, chat_id, state, frame):
    """Runs an action triggered by a custom gesture. Returns True if the
    caller should stop the whole guard (i.e. 'sleep')."""
    if action == "sleep":
        log(f"Aaron saw custom gesture '{gesture_name}' - going to sleep.")
        send_telegram_message(bot_token, chat_id, f"🐕 Aaron saw your '{gesture_name}' gesture and is going to sleep. Zzz...")
        return True

    if action == "lock":
        log(f"Aaron saw custom gesture '{gesture_name}' - locking now.")
        send_telegram_message(bot_token, chat_id, f"🔒 Aaron saw your '{gesture_name}' gesture - locking your PC now.")
        lock_windows()

    elif action == "snapshot":
        log(f"Aaron saw custom gesture '{gesture_name}' - sending snapshot.")
        send_telegram_photo(bot_token, chat_id, frame, f"🐕 Aaron saw your '{gesture_name}' gesture - here's what he sees.")

    elif action == "sit":
        with state.lock:
            state.armed = False
        log(f"Aaron saw custom gesture '{gesture_name}' - lying down.")
        send_telegram_message(bot_token, chat_id, f"🐕 Aaron saw your '{gesture_name}' gesture and lies down. Guarding paused.")

    elif action == "guard":
        with state.lock:
            state.armed = True
            state.unknown_streak = 0
        log(f"Aaron saw custom gesture '{gesture_name}' - back on guard.")
        send_telegram_message(bot_token, chat_id, f"🐕 Aaron saw your '{gesture_name}' gesture and hops back on guard!")

    return False


class GuardState:
    """Shared between the detection loop and the Telegram command thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.armed = True
        self.latest_frame = None
        self.unknown_streak = 0
        self.watch_active = False
        self.triage_pending = False
        self.triage_deadline = 0.0
        self.pc_locked = False
        self.last_unlock_time = 0.0


def watch_loop(bot_token, chat_id, state):
    """Pseudo-live view: sends one photo, then keeps replacing it in place
    every WATCH_REFRESH_SECONDS - feels like a refreshing live feed on your
    phone without needing any real video streaming infrastructure."""
    log("Live watch started.")

    with state.lock:
        frame = state.latest_frame.copy() if state.latest_frame is not None else None
    if frame is None:
        send_telegram_message(bot_token, chat_id, "No camera frame available yet - try again in a second.")
        with state.lock:
            state.watch_active = False
        return

    message_id = send_telegram_photo_get_id(
        bot_token, chat_id, frame,
        "🐕 Live watch started - updates every couple seconds. Send /stopwatch to end early.",
    )
    if message_id is None:
        with state.lock:
            state.watch_active = False
        return

    start_time = time.time()
    while True:
        with state.lock:
            active = state.watch_active
        if not active:
            break
        if time.time() - start_time >= WATCH_MAX_DURATION_SECONDS:
            send_telegram_message(bot_token, chat_id, "🐕 Live watch timed out after 2 minutes. Send /watch again if you need more.")
            break

        time.sleep(WATCH_REFRESH_SECONDS)

        with state.lock:
            frame = state.latest_frame.copy() if state.latest_frame is not None else None
        if frame is None:
            continue
        edit_telegram_photo(bot_token, chat_id, message_id, frame, f"🐕 Live watch - {datetime.now().strftime('%H:%M:%S')}")

    with state.lock:
        state.watch_active = False
    log("Live watch ended.")


def lock_state_loop(bot_token, chat_id, state, detector, recognizer, known_embeddings):
    """Tracks actual Windows lock/unlock state (not just our own armed flag)
    so Aaron can go quiet while locked - the PC is already secured, so more
    "stranger detected" pings just add noise - and then speak up exactly
    once, right when it's unlocked again, with a photo of who's there."""
    was_locked = is_workstation_locked()
    with state.lock:
        state.pc_locked = was_locked

    while True:
        time.sleep(LOCK_POLL_SECONDS)
        now_locked = is_workstation_locked()

        if now_locked != was_locked:
            with state.lock:
                state.pc_locked = now_locked

            if now_locked:
                log("Workstation locked - suppressing further stranger alerts until unlocked.")
            else:
                log("Workstation unlocked - checking who's there.")
                with state.lock:
                    state.last_unlock_time = time.time()
                    frame = state.latest_frame.copy() if state.latest_frame is not None else None

                if frame is None:
                    send_telegram_message(bot_token, chat_id, "🐕 Your PC was just unlocked (no camera frame to check who).")
                else:
                    face = detect_largest_face(detector, frame)
                    if face is not None:
                        feature, _aligned = get_embedding(recognizer, frame, face)
                        best_name, score = best_match(recognizer, feature, known_embeddings)
                        if best_name is not None and score >= COSINE_THRESHOLD:
                            caption = f"🐕 Your PC was just unlocked - looks like {best_name} (score={score:.2f})."
                            save_evidence("unlock", frame, best_name)
                        else:
                            caption = f"🐕 Your PC was just unlocked by someone Aaron doesn't recognize (score={score:.2f})."
                            save_evidence("unlock", frame, "unrecognized")
                    else:
                        caption = "🐕 Your PC was just unlocked (no face in view to check)."
                        save_evidence("unlock", frame, "noface")
                    send_telegram_photo(bot_token, chat_id, frame, caption)

        was_locked = now_locked


def handle_command(text, bot_token, chat_id, state):
    text = text.strip().lower()

    if text in ("/guard", "/start"):
        with state.lock:
            state.armed = True
            state.unknown_streak = 0
        log("Aaron is back on guard (remote command).")
        send_telegram_message(bot_token, chat_id, "🐕 Aaron hops back up. Back on guard!")

    elif text == "/sit":
        with state.lock:
            state.armed = False
        log("Aaron lies down (paused by /sit).")
        send_telegram_message(bot_token, chat_id, "🐕 Aaron lies down. Guarding paused - send /guard to wake him up.")

    elif text == "/status":
        with state.lock:
            armed = state.armed
            pc_locked = state.pc_locked
        status = "on guard, watching the desk 🐕👀" if armed else "resting (paused) 🐾💤"
        lock_note = "🔒 PC is locked (alerts paused until unlock)" if pc_locked else "🔓 PC is unlocked"
        send_telegram_message(bot_token, chat_id, f"Aaron is currently: {status}\n{lock_note}")

    elif text == "/snapshot":
        with state.lock:
            frame = state.latest_frame.copy() if state.latest_frame is not None else None
        if frame is not None:
            send_telegram_photo(bot_token, chat_id, frame, "🐕 Here's what Aaron sees right now.")
        else:
            send_telegram_message(bot_token, chat_id, "No camera frame available yet - try again in a second.")

    elif text == "__triage_ok__":
        with state.lock:
            was_pending = state.triage_pending
            state.triage_pending = False
            state.unknown_streak = 0
        if was_pending:
            log("Triage: confirmed known person - standing down.")
            send_telegram_message(bot_token, chat_id, "🐕 Got it, standing down. Back on guard.")

    elif text == "__triage_lock__":
        with state.lock:
            state.triage_pending = False
        log("Triage: chose to lock now.")
        send_telegram_message(bot_token, chat_id, "🔒 Locking your PC now.")
        lock_windows()

    elif text == "/watch":
        with state.lock:
            already_watching = state.watch_active
            if not already_watching:
                state.watch_active = True
        if already_watching:
            send_telegram_message(bot_token, chat_id, "🐕 Already watching! Send /stopwatch to end it.")
        else:
            threading.Thread(target=watch_loop, args=(bot_token, chat_id, state), daemon=True).start()

    elif text == "/stopwatch":
        with state.lock:
            was_watching = state.watch_active
            state.watch_active = False
        send_telegram_message(bot_token, chat_id, "🐕 Stopped watching." if was_watching else "Wasn't watching.")

    elif text == "/lock":
        log("Remote /lock command received - locking now.")
        send_telegram_message(bot_token, chat_id, "🔒 Locking your PC now.")
        lock_windows()

    elif text == "/help":
        send_telegram_message(
            bot_token, chat_id,
            "🐕 Aaron commands (he's awake right now, so these work):\n"
            "/guard - resume guarding\n"
            "/sit - pause guarding\n"
            "/status - is Aaron guarding or resting?\n"
            "/snapshot - live photo from the camera\n"
            "/watch - pseudo-live view, refreshes every ~2s for up to 2 min\n"
            "/stopwatch - end an active /watch early\n"
            "/lock - lock the PC right now\n"
            "/help - this message\n\n"
            "/sleep also works and stops him entirely (handled by the listener).\n\n"
            f"When he spots a stranger he'll ask via buttons first instead of "
            f"locking instantly - {TRIAGE_GRACE_SECONDS}s to say it's someone you "
            f"know, otherwise he locks automatically.",
        )

    else:
        send_telegram_message(bot_token, chat_id, "Woof? Unknown command. Try /help")


def command_relay_loop(bot_token, chat_id, state):
    """Watches for commands relayed by aaron_listener.py via a local file,
    instead of polling Telegram directly - only aaron_listener.py does that
    now. Having two processes independently long-poll the same bot's
    getUpdates caused a race where whichever one grabbed an update first
    would "consume" it even if it didn't recognize the command, silently
    losing valid commands meant for the other process."""
    # Whatever's already in the file at startup is stale (from a previous
    # run) - treat it as already-handled so it doesn't get replayed. A
    # leftover /lock replaying itself right at startup would be a nasty
    # surprise.
    last_id = None
    try:
        with open(GUARD_COMMAND_PATH) as f:
            last_id = json.load(f).get("id")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    while True:
        try:
            with open(GUARD_COMMAND_PATH) as f:
                command = json.load(f)
            if command["id"] != last_id:
                last_id = command["id"]
                handle_command(command["text"], bot_token, chat_id, state)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        time.sleep(0.2)


def main():
    log("Aaron is waking up.")

    try:
        bot_token, chat_id = load_telegram_config()
    except (FileNotFoundError, RuntimeError) as e:
        log(str(e))
        return

    try:
        known_embeddings = load_embeddings(EMBEDDINGS_PATH)
    except FileNotFoundError:
        log(f"'{EMBEDDINGS_PATH}' not found. Run capture_faces.py then train_model.py first.")
        return

    detector = create_detector()
    recognizer = create_recognizer()
    gesture_recognizer = create_gesture_recognizer()

    gesture_actions, gesture_model = load_gesture_actions()
    if gesture_actions:
        log(f"Loaded {len(gesture_actions)} custom gesture(s): {list(gesture_actions.keys())}")

    cam = cv2.VideoCapture(0, cv2.CAP_MSMF)
    if not cam.isOpened():
        log("Could not open webcam")
        return

    state = GuardState()
    threading.Thread(target=command_relay_loop, args=(bot_token, chat_id, state), daemon=True).start()
    threading.Thread(
        target=lock_state_loop, args=(bot_token, chat_id, state, detector, recognizer, known_embeddings),
        daemon=True,
    ).start()

    log("Aaron is on guard. Remote commands: /sit /guard /status /snapshot /lock")

    last_trigger_time = 0.0
    gesture_streak = 0
    custom_streaks = {name: 0 for name in gesture_actions}
    static_streak = 0
    last_gesture_log_time = 0.0

    while True:
        ok, frame = cam.read()
        if ok and looks_like_static(frame):
            static_streak += 1
            if static_streak >= STATIC_FRAME_TRIGGER:
                log("Camera feed looks corrupted (likely post-lock DirectShow/Frame Server glitch) - reconnecting.")
                cam.release()
                time.sleep(0.5)
                cam = cv2.VideoCapture(0, cv2.CAP_MSMF)
                static_streak = 0
            continue
        static_streak = 0
        if not ok:
            time.sleep(1)
            continue

        with state.lock:
            state.latest_frame = frame

        with state.lock:
            triage_due = state.triage_pending and time.time() >= state.triage_deadline
            if triage_due:
                state.triage_pending = False
        if triage_due:
            log("Triage timed out with no response - locking automatically.")
            play_alarm()
            send_telegram_message(bot_token, chat_id, "🐕 No response - locking your PC now (better safe than sorry).")
            lock_windows()

        gesture_result = recognize_full(gesture_recognizer, frame)

        with state.lock:
            in_unlock_grace = time.time() - state.last_unlock_time < GESTURE_POST_UNLOCK_GRACE_SECONDS

        # Built-in gesture: the default sleep trigger (e.g. Open_Palm).
        gesture_name, gesture_score = top_gesture(gesture_result)
        if not in_unlock_grace and gesture_name == SLEEP_GESTURE and gesture_score >= GESTURE_SCORE_THRESHOLD:
            gesture_streak += 1
        else:
            gesture_streak = 0

        if gesture_streak >= GESTURE_HOLD_FRAMES:
            log(f"Aaron saw the sleep gesture ({SLEEP_GESTURE}, score={gesture_score:.2f}) - going to sleep.")
            send_telegram_message(bot_token, chat_id, "🐕 Aaron saw your gesture and is going to sleep. Zzz...")
            cam.release()
            return

        # Custom gestures: nearest-neighbor match against your own captured shapes.
        if gesture_actions and gesture_result.hand_landmarks:
            vector = landmarks_to_vector(gesture_result.hand_landmarks[0])
            custom_name, distance = best_gesture_match(vector, gesture_model)

            if time.time() - last_gesture_log_time >= 1.0:
                log(f"Custom gesture check: closest={custom_name} distance={distance:.3f} "
                    f"(threshold={CUSTOM_GESTURE_DISTANCE})"
                    + (" [unlock grace - ignored]" if in_unlock_grace else ""))
                last_gesture_log_time = time.time()

            if in_unlock_grace:
                for name in custom_streaks:
                    custom_streaks[name] = 0
            else:
                # Leaky streak: a single noisy frame costs 1, not the whole
                # streak - frame-to-frame landmark jitter means distance
                # regularly ticks just above/below the threshold even while
                # you're genuinely holding the gesture steady.
                for name in custom_streaks:
                    if name == custom_name and distance <= CUSTOM_GESTURE_DISTANCE:
                        custom_streaks[name] += 1
                    else:
                        custom_streaks[name] = max(0, custom_streaks[name] - 1)

                for name, streak in custom_streaks.items():
                    if streak >= CUSTOM_GESTURE_HOLD_FRAMES:
                        should_stop = run_gesture_action(gesture_actions[name], name, bot_token, chat_id, state, frame)
                        custom_streaks[name] = 0
                        if should_stop:
                            cam.release()
                            return
        elif gesture_actions:
            for name in custom_streaks:
                custom_streaks[name] = 0

        with state.lock:
            armed = state.armed

        if not armed:
            time.sleep(0.2)
            continue

        face = detect_largest_face(detector, frame)

        if face is not None:
            feature, _aligned = get_embedding(recognizer, frame, face)
            best_name, score = best_match(recognizer, feature, known_embeddings)
            is_known = best_name is not None and score >= COSINE_THRESHOLD

            with state.lock:
                if is_known:
                    state.unknown_streak = 0
                else:
                    state.unknown_streak += 1
                unknown_streak = state.unknown_streak

            if unknown_streak >= UNKNOWN_TRIGGER_FRAMES:
                now = time.time()
                with state.lock:
                    triage_pending = state.triage_pending
                    pc_locked = state.pc_locked
                if not triage_pending and not pc_locked and now - last_trigger_time >= ALERT_COOLDOWN_SECONDS:
                    if score >= TRIAGE_FLOOR:
                        # Resembles a trained person somewhat - could be you/
                        # someone trained under bad lighting/angle. Ask first.
                        log(f"Aaron spotted a possible match (best_match={best_name} score={score:.3f}) - asking for triage.")
                        save_evidence("stranger", frame, f"score{score:.2f}")
                        play_alarm()
                        send_telegram_photo_with_buttons(
                            bot_token, chat_id, frame,
                            f"🐕 Aaron spotted someone he don't know. Is this someone you know? "
                            f"No response in {TRIAGE_GRACE_SECONDS}s and he'll lock automatically.",
                            [("✅ I know them", "triage_ok"), ("🔒 Lock now", "triage_lock")],
                        )
                        with state.lock:
                            state.triage_pending = True
                            state.triage_deadline = now + TRIAGE_GRACE_SECONDS
                    else:
                        # Doesn't resemble anyone trained at all - not worth
                        # the wait, lock right away.
                        log(f"Aaron spotted a total stranger (best_match={best_name} score={score:.3f}, "
                            f"below TRIAGE_FLOOR={TRIAGE_FLOOR}) - locking instantly.")
                        save_evidence("stranger", frame, f"score{score:.2f}_instant")
                        play_alarm()
                        send_telegram_photo(bot_token, chat_id, frame,
                                             "🐕 Aaron spotted a total stranger RUFF RUFF!! - your PC has been locked.")
                        lock_windows()
                    last_trigger_time = now
                with state.lock:
                    state.unknown_streak = 0
        else:
            with state.lock:
                state.unknown_streak = 0

        time.sleep(0.1)


if __name__ == "__main__":
    main()
