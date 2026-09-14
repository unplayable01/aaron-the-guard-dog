# Aaron - Architecture & Design

## System Overview

Aaron is organized as three independent processes that coordinate via local files and subprocess control. This design allows:
- The listener to be always-on without consuming GPU/camera resources
- The guard to be started/stopped remotely without manual intervention
- Clean separation of concerns (Telegram polling vs. face detection vs. voice listening)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Telegram Bot API                            │
└────────────┬────────────────────────────────────────────────────┘
             │
        Long-polls for updates
             │
      ┌──────▼──────────────────────────┐
      │   aaron_listener.py              │
      │ (Always-on, lightweight)         │
      │ - Polls Telegram                 │
      │ - Starts/stops guard_watch.py    │
      │ - Relays commands via file       │
      │ - Handles friends                │
      └──────┬───────────┬───────────────┘
             │           │
    Relayed  │           │ Subprocess
    commands │           │ management
    file     │           │
             │      ┌────▼────────────────────────┐
             │      │   guard_watch.py            │
             │      │ (Headless, uses camera)     │
             │      │ - Watches webcam            │
             │      │ - Detects/recognizes faces  │
             │      │ - Responds to gestures      │
             │      │ - Locks PC                  │
             │      │ - Logs & saves evidence     │
             └──────┼────────────────────────────┘
                    │
                    │ (also started by voice_wake)
                    │
      ┌─────────────▼──────────────────┐
      │   voice_wake.py                │
      │ (Optional, listening audio)    │
      │ - Hears wake phrase (Vosk)     │
      │ - Verifies your voice (Resemb) │
      │ - Starts guard_watch.py        │
      └────────────────────────────────┘
```

## The Three Processes

### 1. guard_watch.py - The Guard Dog

**Purpose**: Main security process. Watches the webcam, detects faces, recognizes trained people, and locks the PC on intrusion.

**Startup**: 
- Via `/wake` command (aaron_listener.py launches it)
- Via voice_wake.py (when wake phrase + voice verified)
- Manual via `batch/run_guard_hidden.vbs` or run.bat
- Desktop shortcut pointing to run_guard_hidden.vbs

**Shutdown**:
- Via `/sleep` command (aaron_listener.py kills it)
- Via built-in sleep gesture (Open_Palm hold for 1.5s)
- Via custom gesture mapped to "sleep"
- Manual via `batch/stop_guard.bat` or Task Manager

**Key State** (GuardState class):
- `armed`: Whether guarding is active (can be paused with `/sit`)
- `latest_frame`: Current webcam frame (shared with lock-state and watch threads)
- `unknown_streak`: Count of consecutive frames with unknown face
- `watch_active`: Whether pseudo-live view is running
- `triage_pending`: Whether a triage dialog was sent (awaiting user response)
- `triage_deadline`: Time limit for triage response before auto-lock
- `pc_locked`: Current Windows lock state
- `last_unlock_time`: Timestamp of last unlock (for gesture post-unlock grace)

**Main Loop**:
1. Capture frame from webcam
2. Detect static/corruption (reconnect camera if needed)
3. Check if triage deadline has passed (auto-lock if yes)
4. Recognize built-in gesture (Open_Palm for sleep)
5. Recognize custom gestures if trained
6. If armed, detect + recognize largest face
7. If unknown face detected for 3+ consecutive frames, either:
   - Send triage dialog (if score ≥ TRIAGE_FLOOR, might be you/trained person under bad lighting)
   - Lock instantly (if score < TRIAGE_FLOOR, definitely a stranger)
8. Handle commands relayed from listener via guard_command.json
9. Track lock/unlock state and send unlock notification with photo
10. Sleep 0.1s, repeat

**Threads** (all daemon):
- **command_relay_loop**: Watches guard_command.json for commands from listener
- **lock_state_loop**: Polls Windows lock state, suppresses alerts while locked, notifies on unlock
- **watch_loop** (on-demand): Updates pseudo-live photo feed every 2 seconds

**Output**:
- Telegram alerts (strangers, unlock notifications, command responses)
- Evidence photos: `private/evidence/<date>/HH-MM-SS_category_note.jpg`
- Log: `private/logs/guard_watch.log`

### 2. aaron_listener.py - The Switchboard

**Purpose**: Always-on, lightweight Telegram poller. Starts/stops guard_watch.py and routes commands without consuming camera resources or competing for Telegram updates with the guard.

**Startup**:
- Manual via `batch/run_listener_hidden.vbs`
- Windows Task Scheduler (recommended, auto-start at login)
- Desktop shortcut

**Shutdown**:
- Via `/sleep` command (it kills guard_watch.py if running)
- Manual via `batch/stop_listener.bat` or Task Manager

**Key Features**:

- **Exclusive Telegram Poller**: Only process that calls Telegram's `getUpdates()`. Previously, both guard_watch.py and the listener polled, causing a race where whoever grabbed an update first would "consume" it even if they didn't understand the command. Now only the listener polls and relays to the guard via a local file.

- **Command Routing**:
  - **Listener-only commands** (`/wake`, `/sleep`, `/fetch`): Handled directly
  - **Guard commands** (`/sit`, `/guard`, `/snapshot`, etc.): Relayed to guard_watch.py via `private/guard_command.json`
  - **Guard's /status**: Relayed to guard so it can report both running state and armed/resting detail

- **Friend Handling**:
  - Text/stickers/photos/GIFs sent to the bot by non-owner chat IDs are forwarded to the owner with metadata
  - Friends see a "play-only" keyboard: `/pet`, `/treat`, `/goodboy` (harmless canned replies)
  - Owner sees the full command keyboard

- **Wake Notification**: Any friend who messages while Aaron is asleep gets a "he's sleeping" message and a random dog fact; they're added to a waiting list and notified exactly once when Aaron wakes up.

**Threads**: None; single-threaded event loop.

**Output**:
- Log: `private/logs/aaron_listener.log`
- Relayed commands: `private/guard_command.json` (updated every time a guard command arrives)

### 3. voice_wake.py - Voice-Activated Listener

**Purpose**: Optional always-on process that listens for a wake phrase and verifies it's your voice before starting guard_watch.py.

**Startup**:
- Manual via `batch/run_voice_wake_hidden.vbs`
- Windows Task Scheduler (recommended)
- Desktop shortcut

**Shutdown**:
- Manual via `batch/stop_voice_wake.bat`

**Key Features**:

- **Offline Speech-to-Text**: Uses Vosk (small English model) to transcribe spoken words without sending audio anywhere
- **Fuzzy Phrase Matching**: Vosk's small model can mishear occasional words, so voice_wake matches "most" of the wake words (e.g., 2 of 3) rather than exact string match
- **Speaker Verification**: Computes a Resemblyzer embedding from the recognized speech and compares it to your voice profile (6 enrolled samples)
- **Cooldown**: After triggering (successfully or not), ignores the wake phrase for 5 seconds to avoid double-triggering on echoes

**Logic**:
1. Listen to microphone continuously
2. Feed audio to Vosk recognizer
3. When Vosk detects a complete utterance, extract text
4. Check if text contains wake words (fuzzy match)
5. If no match, log and continue
6. If matched but within cooldown, log and continue
7. If matched and past cooldown:
   - Compute voice embedding from audio
   - Compare to voice_profile.json (your enrolled samples)
   - If similarity ≥ SPEAKER_THRESHOLD, start guard_watch.py
   - If below threshold, log rejection and continue

**Enrollment** (enroll_voice.py):
- Prompts you to say the wake phrase 6 times
- Transcribes each utterance to verify Vosk heard the phrase correctly
- Computes Resemblyzer embeddings and saves to `private/voice_profile.json`

**Output**:
- Log: `private/logs/voice_wake.log`
- Starts subprocess: guard_watch.py

---

## Interprocess Communication

### guard_command.json (Listener → Guard Relay)

Location: `private/guard_command.json`

When the listener receives a command meant for the guard (anything except `/wake`, `/sleep`, `/fetch`, `/status`, `/help`, and the triage callback buttons), it writes:

```json
{
  "id": 1694712345123456789,
  "text": "/snapshot"
}
```

The `id` is a nanosecond timestamp (guarantees uniqueness) so the guard can detect new commands by comparing against the last-seen `id`. This avoids replaying old commands on startup.

The guard's command_relay_loop polls this file every 0.2 seconds and calls handle_command() when it sees a new id.

### Subprocess Management (Listener ↔ Guard)

**Starting guard_watch.py** (listener):
```python
subprocess.Popen(
    [PYTHONW, GUARD_SCRIPT],
    cwd=SCRIPT_DIR,
    creationflags=CREATE_NO_WINDOW
)
```

**Stopping guard_watch.py** (listener):
```python
pids = find_guard_pids()  # Uses psutil to find pythonw.exe running guard_watch.py
for pid in pids:
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], ...)
```

The listener doesn't track its own subprocess handle; instead, it uses psutil to search for guard_watch.py by matching the command line. This allows `/sleep` to work even if Aaron was started manually.

### Telegram Callback Buttons (Owner → Guard)

When the guard sends a triage question with buttons ("I know them" / "Lock now"), the listener's callback_query handler intercepts the button tap and relays it to the guard as:

```json
{"id": 1694712345987654321, "text": "__triage_ok__"}
// or
{"id": 1694712345987654321, "text": "__triage_lock__"}
```

---

## File-by-File Reference

### src/paths.py

**Purpose**: Single source of truth for all file locations. Separates public repo assets from private user data.

**Key Constants**:
- `SRC_DIR`: Directory containing src/
- `PROJECT_DIR`: Repository root
- `MISC_DIR`: misc/ folder (shareable assets)
- `PRIVATE_DIR`: Private folder (default `%USERPROFILE%\Desktop\Aaron_Private`, override via `AARON_PRIVATE_DIR` environment variable)
- `LOGS_DIR`: Subfolder within PRIVATE_DIR for logs

**Key Functions**:
- `misc(*parts)`: Construct path to misc/ subfolder (e.g., `misc("alarm.wav")`)
- `private(*parts)`: Construct path to private folder subfolder (e.g., `private("telegram_config.json")`)
- `log_file(name)`: Construct path to logs subfolder (e.g., `log_file("guard_watch.log")`)

**Usage**: All other modules import this to avoid hardcoding paths. This ensures the code works regardless of where the repo is cloned.

**Reads**: Environment variable `AARON_PRIVATE_DIR` (if set)
**Writes**: Creates `logs/` subfolder if it doesn't exist

### src/download_models.py

**Purpose**: Download the five third-party models that Aaron needs into misc/. Verifies integrity, skips files already present and valid, and re-downloads corrupted ones.

**Usage**: `python src/download_models.py`

**Models Downloaded**:
1. **face_detection_yunet_2023mar.onnx** - YuNet face detector (OpenCV)
   - Source: `media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/...`
   - Verified: sha256 hash
2. **face_recognition_sface_2021dec.onnx** - SFace face recognizer (OpenCV)
   - Source: `media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/...`
   - Verified: sha256 hash
3. **lbfmodel.yaml** - 68-point facial landmarks
   - Source: `raw.githubusercontent.com/kurnianggoro/GSOC2017/master/data/lbfmodel.yaml`
   - Verified: sha256 hash
4. **gesture_recognizer.task** - MediaPipe hand gesture recognizer
   - Source: `storage.googleapis.com/mediapipe-models/gesture_recognizer/...float16/latest/...`
   - Verified: Minimum file size (1 MB) since URL tracks "latest"
5. **vosk-model-small-en-us-0.15.zip** - Vosk English speech recognition model
   - Source: `alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip`
   - Verified: Expected subdirectories (am, conf, graph) after extraction

**Key Features**:
- **Atomic downloads**: Uses .part extension during download; renamed only after verification succeeds
- **Corruption detection**: Removes incomplete or invalid files and re-downloads
- **Interrupted-download safety**: Incomplete .part files never get mistaken for valid models
- **Vosk special handling**: Extracts zip to misc/, verifies subdirectories present
- **Standard library only**: No external dependencies beyond what Aaron already imports

**Reads**: Network (upstream URLs)
**Writes**: `misc/face_detection_yunet_2023mar.onnx`, `misc/face_recognition_sface_2021dec.onnx`, `misc/lbfmodel.yaml`, `misc/gesture_recognizer.task`, `misc/vosk-model-small-en-us-0.15/`

### src/face_engine.py

**Purpose**: Shared face detection and recognition engine using OpenCV's modern models.

**Key Constants**:
- `DEFAULT_COSINE_THRESHOLD = 0.363`: OpenCV's recommended SFace similarity cutoff
- `DETECT_SCORE_THRESHOLD = 0.7`: YuNet face detector confidence threshold

**Key Functions**:
- `create_detector(frame_size)`: Initializes YuNet face detector
- `create_recognizer()`: Initializes SFace face recognizer
- `detect_largest_face(detector, frame)`: Returns the biggest face in the frame (or None)
- `get_embedding(recognizer, frame, face)`: Aligns the face and extracts its 128-d embedding
- `cosine_score(recognizer, feature_a, feature_b)`: Computes similarity (0 = unrelated, 1 = identical)
- `best_match(recognizer, feature, known_embeddings)`: Finds the closest known person by embedding similarity
- `load_embeddings(path)`: Loads model_embeddings.json into a dict of {name: [np.ndarray(1,128), ...]}

**Models**:
- `face_detection_yunet_2023mar.onnx`: Detects faces and returns box + 5 landmark points
- `face_recognition_sface_2021dec.onnx`: Converts aligned face crop to 128-d embedding vector

**Reads**: Webcam frame (BGR)
**Writes**: Nothing (stateless utility functions)
**Used By**: capture_faces, train_model, recognize, security_watch, guard_watch

### src/capture_faces.py

**Purpose**: Gather training photos for a new person. Validates head pose to ensure varied angles.

**Usage**: `python capture_faces.py <name>`

**Key Constants**:
- `SAMPLES_PER_POSE = 30`: 30 images per pose
- `SAVE_COOLDOWN = 5`: Skip 5 frames between saves (avoid near-duplicates)
- `YAW_TURN = 15`, `PITCH_TILT = 12`: Head rotation thresholds in degrees

**Poses** (5 total):
1. Look STRAIGHT (yaw ≤ ±10°, pitch ≤ ±10°)
2. Turn LEFT (yaw ≥ 15°)
3. Turn RIGHT (yaw ≤ -15°)
4. Tilt UP (pitch ≥ 12°)
5. Tilt DOWN (pitch ≤ -12°)

**Process**:
1. Open webcam
2. For each pose, detect face and estimate head pose (via 68-point landmarks + solvePnP)
3. Only save when pose matches (color feedback: green if matching, orange if not)
4. Save 30 samples per pose as aligned YuNet crops to `misc/dataset/<name>/*.jpg`
5. Total: 150 images

**Reads**: Webcam, `lbfmodel.yaml` (68-point landmark detector)
**Writes**: `misc/dataset/<name>/*.jpg`

### src/train_model.py

**Purpose**: Extract SFace embeddings from captured images and save to model_embeddings.json.

**Usage**: `python train_model.py`

**Process**:
1. Scan `misc/dataset/` for person folders
2. For each image, pass through SFace to get 128-d embedding
3. Save all embeddings as `{name: [[128 floats], ...]}`

**Reads**: `private/dataset/<name>/*.jpg`
**Writes**: `private/model_embeddings.json`

### src/recognize.py

**Purpose**: Demo/test the trained model with live webcam view.

**Usage**: `python recognize.py`

**Key Constants**:
- `SMOOTHING_WINDOW = 10`: Temporal smoothing over 10 frames
- `SMOOTHING_MIN_AGREEMENT = 6`: Name display requires 6 of 10 frames agreeing
- `MISS_GRACE_FRAMES = 10`: Allow 10 frames of no-face before clearing smoothing window

**Display Logic**:
- Green box = known person
- Red box = unknown
- "..." = not enough agreement in recent frames
- Shows score (cosine similarity, 0-1)

**Reads**: Webcam, `private/model_embeddings.json`
**Writes**: Nothing (display only)

### src/head_pose.py

**Purpose**: Estimate yaw/pitch/roll from 68-point facial landmarks using solvePnP.

**Key Functions**:
- `estimate_pose(landmarks, frame_shape)`: Returns (pitch, yaw, roll) in degrees or None

**Algorithm**:
1. Extract 6 landmarks (nose tip, chin, eye corners, mouth corners)
2. Build camera matrix from frame size (assumes focal length = width)
3. Use solvePnP to find rotation/translation that maps a 3D generic face model to these points
4. Decompose rotation matrix into Euler angles (pitch/yaw/roll)

**Used By**: capture_faces.py (for pose validation)

### src/gesture.py

**Purpose**: Wrapper around MediaPipe's GestureRecognizer for built-in hand gestures.

**Key Functions**:
- `create_gesture_recognizer()`: Loads the MediaPipe gesture model
- `recognize_full(recognizer, frame_bgr)`: Returns full result with both gestures and hand landmarks
- `top_gesture(result)`: Extracts the top-scoring gesture name and confidence
- `recognize_gesture(recognizer, frame_bgr)`: One-shot convenience (recognize_full + top_gesture)

**Built-in Gestures**: Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up, Victory, ILoveYou, or None

**Model**: `gesture_recognizer.task` (MediaPipe pretrained)

**Used By**: guard_watch (for built-in Open_Palm sleep trigger and getting hand landmarks for custom matching)

### src/hand_shape.py

**Purpose**: Custom hand gesture matching by hand-shape distance (DIY alternative to MediaPipe Model Maker).

**Key Constants**:
- `DEFAULT_DISTANCE_THRESHOLD = 0.4`: Starting guess for gesture match distance

**Key Functions**:
- `landmarks_to_vector(hand_landmarks)`: Converts 21 MediaPipe landmarks to a normalized, scale-invariant 42-d vector
- `load_gesture_model(path)`: Loads gesture_model.json into {name: [np.ndarray, ...]}
- `best_gesture_match(vector, gesture_model)`: Finds closest saved example (Euclidean distance)

**Normalization**:
1. Translate so wrist is at origin
2. Scale by wrist-to-middle-knuckle distance (invariant to hand size/distance)
3. Drop z-coordinate (depth is too noisy frame-to-frame)
4. Flatten to 42 floats

**Result**: Same gesture matches regardless of hand position, scale, or distance in frame.

**Used By**: guard_watch (for custom gesture matching after face detection is armed)

### src/capture_gesture.py

**Purpose**: Record examples of a custom hand gesture.

**Usage**: `python capture_gesture.py <gesture_name>`

**Process**:
1. Open webcam
2. Detect hand via MediaPipe
3. Extract normalized hand-shape vector every 4 frames
4. Save 30 samples to `private/gesture_dataset/<name>/*.json`

**Reads**: Webcam, gesture_recognizer.task
**Writes**: `private/gesture_dataset/<name>/*.json`

### src/train_gestures.py

**Purpose**: Fold captured gesture samples into gesture_model.json.

**Usage**: `python train_gestures.py`

**Process**:
1. Scan `private/gesture_dataset/` for gesture folders
2. Load all *.json vectors
3. Save as `{name: [[42 floats], ...]}`

**Reads**: `private/gesture_dataset/<name>/*.json`
**Writes**: `private/gesture_model.json`

### src/voice_engine.py

**Purpose**: Shared utilities for Vosk (speech-to-text) and Resemblyzer (speaker verification).

**Key Constants**:
- `INPUT_DEVICE_NAME = "Microphone Array"`: Device to use (matched by substring)
- `SAMPLE_RATE = 16000`: Audio sampling rate for Vosk/Resemblyzer
- `DEFAULT_SPEAKER_THRESHOLD = 0.75`: Starting cosine similarity threshold for voice matching

**Key Functions**:
- `find_input_device(name_substring)`: Locates audio input device by name substring
- `load_vosk_model()`: Loads the Vosk speech model from disk
- `create_recognizer(model)`: Creates a Vosk recognizer instance
- `create_voice_encoder()`: Initializes Resemblyzer's VoiceEncoder
- `audio_bytes_to_float(raw_bytes)`: Converts int16 PCM to float32
- `compute_embedding(encoder, raw_audio_bytes)`: Extracts voice embedding from audio
- `cosine_similarity(a, b)`: Computes cosine distance between two vectors
- `best_speaker_similarity(embedding, profile_embeddings)`: Finds maximum similarity to any enrolled sample
- `load_voice_profile(path)`: Loads voice_profile.json (list of embeddings)
- `save_voice_profile(embeddings, path)`: Saves voice profile
- `phrase_matches(text, wake_words)`: Fuzzy word matching (requires most, not all, words)

**Models**:
- `vosk-model-small-en-us-0.15/`: Offline English speech recognition
- Resemblyzer (via pip): Pretrained neural network for voice embeddings

**Used By**: enroll_voice, voice_wake

### src/enroll_voice.py

**Purpose**: Record your voice samples for voice-activated wake.

**Usage**: `python enroll_voice.py`

**Process**:
1. Initialize Vosk recognizer and Resemblyzer encoder
2. Prompt 6 times: "Say 'Wake up Aaron'"
3. Wait for Vosk to detect complete utterance (speech + silence)
4. Show transcribed text to confirm Vosk heard the phrase
5. Compute Resemblyzer embedding
6. Save all 6 embeddings to `voice_profile.json`

**Reads**: Microphone
**Writes**: `private/voice_profile.json`

### src/voice_wake.py

**Purpose**: Always-on voice listener for starting guard_watch.py by saying the wake phrase.

**Key Constants**:
- `WAKE_WORDS = ["wake", "up", "aaron"]`
- `SPEAKER_THRESHOLD = 0.55`: Cosine similarity threshold (lower than default to account for background noise)
- `WAKE_COOLDOWN_SECONDS = 5`: Prevent double-triggering

**Process**:
1. Initialize Vosk recognizer and Resemblyzer encoder
2. Load voice_profile.json (your enrolled samples)
3. Listen to microphone continuously
4. For each complete utterance:
   - Check if text contains wake words (fuzzy match: 2 of 3)
   - Check if within cooldown
   - Compute voice embedding
   - Compare to voice profile
   - If ≥ SPEAKER_THRESHOLD, start guard_watch.py

**Reads**: Microphone, `private/voice_profile.json`
**Writes**: `private/logs/voice_wake.log`
**Starts Subprocess**: guard_watch.py

### src/security_watch.py

**Purpose**: Alternative to guard_watch.py that shows a visible window and sends Telegram alerts without locking.

**Usage**: `python security_watch.py`

**Like recognize.py + Telegram alerts**: Displays face recognition with green/red boxes, sends Telegram alert every 5 minutes if an unknown face is present.

**Reads**: Webcam, `private/model_embeddings.json`, `private/telegram_config.json`
**Writes**: Telegram messages

### src/guard_watch.py

**Purpose**: Headless intrusion guard. Main security process.

See "The Three Processes → guard_watch.py" section above for full details.

**Key Files Read**:
- `private/model_embeddings.json`: Known face embeddings
- `private/telegram_config.json`: Bot token and owner chat_id
- `private/gesture_model.json`: Custom gestures (optional)
- `private/gesture_actions.json`: Gesture → action mapping (optional)
- `private/guard_command.json`: Commands relayed from listener
- `private/voice_profile.json`: For logging (not used during guarding)

**Key Files Written**:
- `private/logs/guard_watch.log`: Activity log
- `private/evidence/<date>/<time>_category_note.jpg`: Security photos
- `private/guard_command.json`: Updated to clear stale commands

**Subprocess Started**: None

**Subprocesses It Manages**: None (killed by listener if `/sleep`)

### src/aaron_listener.py

**Purpose**: Always-on Telegram switchboard. Only process that polls Telegram.

See "The Three Processes → aaron_listener.py" section above for full details.

**Key Files Read**:
- `private/telegram_config.json`: Bot token, owner chat_id, friends list
- `private/guard_command.json`: For detecting when guard_watch has seen the command (optional)

**Key Files Written**:
- `private/logs/aaron_listener.log`: Activity log
- `private/guard_command.json`: Relayed commands from Telegram

**Subprocess Started**: guard_watch.py (on `/wake` or voice_wake.py trigger)
**Subprocesses It Manages**: guard_watch.py (kills on `/sleep`)

---

## Configuration & Tuning

See [CONFIGURATION.md](CONFIGURATION.md) for all tunable constants, their current values, and recommendations for adjustment.

Key thresholds:
- **Face Recognition**: `DEFAULT_COSINE_THRESHOLD` (0.363), `TRIAGE_FLOOR` (0.05)
- **Gestures**: `GESTURE_SCORE_THRESHOLD` (0.6), `CUSTOM_GESTURE_DISTANCE` (1.8)
- **Voice**: `SPEAKER_THRESHOLD` (0.55)
- **Timing**: Intrusion detection requires 3 consecutive unknown frames; triage allows 10s before auto-lock

---

## File Organization

Personal data lives in a private folder (default `%USERPROFILE%\Desktop\Aaron_Private`, override with `AARON_PRIVATE_DIR` environment variable) and is never committed to version control:

- **telegram_config.json**: Bot token, owner chat_id, friends list
- **model_embeddings.json**: Trained face embeddings for recognized people
- **voice_profile.json**: Your enrolled voice embeddings
- **gesture_model.json**: Custom gesture hand-shape vectors
- **gesture_actions.json**: Mapping of gesture names to actions
- **guard_command.json**: IPC relay file (listener writes, guard reads)
- **dataset/**: Face training images (organized by person name)
- **gesture_dataset/**: Custom gesture training samples (organized by gesture name)
- **evidence/**: Security photos (organized by date, timestamped)
- **logs/**: Three log files (guard_watch.log, aaron_listener.log, voice_wake.log)

Shareable assets (models, code, requirements) stay in the repo in `misc/`.

## Logging

All three processes log to `private/logs/` with ISO8601 timestamps:

```
2026-09-14T14:32:15 [Aaron] Detected stranger (score=0.125) - asking for triage.
2026-09-14T14:32:15 [Aaron-listener] Relayed '/triage_ok' to Aaron.
2026-09-14T14:32:16 [voice_wake] Heard "wake up aaron" - speaker similarity=0.612 (threshold=0.55)
```

Check logs in the private folder to troubleshoot issues, understand behavior, or audit guard activity.

---

## Extension Points

- **Custom Gestures**: Capture + train gestures, map to actions in gesture_actions.json
- **New Telegram Commands**: Extend handle_command() in guard_watch.py and/or aaron_listener.py
- **Face Recognition Thresholds**: Adjust COSINE_THRESHOLD and TRIAGE_FLOOR in guard_watch.py
- **Voice Wake Threshold**: Adjust SPEAKER_THRESHOLD in voice_wake.py
- **Detection Sensitivity**: Adjust UNKNOWN_TRIGGER_FRAMES in guard_watch.py (currently 3)
- **Alert Frequency**: Adjust ALERT_COOLDOWN_SECONDS in guard_watch.py and security_watch.py
