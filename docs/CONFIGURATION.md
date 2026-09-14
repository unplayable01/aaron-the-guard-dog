# Aaron - Configuration & Tunable Constants

This document lists every tunable constant in Aaron's codebase. Read the values from the source code; adjust them based on your testing and observations.

## Face Recognition

### COSINE_THRESHOLD

- **File**: `src/guard_watch.py` line 104 (guard), `src/recognize.py` line 25, `src/security_watch.py` line 34
- **Current Value**: `0.363` (from `src/face_engine.py` DEFAULT_COSINE_THRESHOLD)
- **Meaning**: Minimum cosine similarity required to consider a face a match. Similarity is 0 (unrelated) to 1 (identical)
- **Higher** → Stricter matching, fewer false positives (fewer people locked out), but may reject your own face under bad lighting/angle
- **Lower** → Looser matching, more false positives, but won't reject you as easily
- **Tuning**: OpenCV's documented recommendation is 0.363. Only adjust if you get consistent false accepts or false rejects. Real testing with your own face under various lighting/angles is essential.

### DEFAULT_COSINE_THRESHOLD

- **File**: `src/face_engine.py` line 24
- **Current Value**: `0.363`
- **Meaning**: The shared threshold used by all scripts that do face recognition
- **Note**: Change this one value to affect all scripts at once (guard_watch, recognize, security_watch)

### DETECT_SCORE_THRESHOLD

- **File**: `src/face_engine.py` line 26
- **Current Value**: `0.7`
- **Meaning**: YuNet face detector confidence (0–1). Only detections ≥ 0.7 are returned
- **Higher** → Fewer false face detections, but might miss small/distant faces
- **Lower** → More detections (including false positives), especially at range
- **Tuning**: 0.7 is a reasonable starting point. If the detector keeps missing faces you want to protect, lower it; if it keeps falsely detecting non-faces, raise it.

### TRIAGE_FLOOR

- **File**: `src/guard_watch.py` line 135
- **Current Value**: `0.05`
- **Meaning**: Lower cosine similarity threshold that splits unknowns into two categories:
  - `score >= TRIAGE_FLOOR`: Resembles a trained person somewhat (but below COSINE_THRESHOLD) → Send triage dialog, wait for user response
  - `score < TRIAGE_FLOOR`: Doesn't resemble anyone trained at all → Lock instantly, no dialog
- **Rationale**: Testing showed your own face under poor lighting can score as low as 0.1–0.3 and still genuinely be you. Setting TRIAGE_FLOOR too high would cause your own bad-lighting frames to trigger instant lock instead of the triage grace period. The floor sits conservatively low to let borderline cases get human judgment.
- **Higher** → More strangers get the triage dialog (slower but safer, gives you a chance to confirm), fewer get instant-locked
- **Lower** → Fewer get dialog, more get instant-locked (faster response, riskier to legitimate users)
- **Tuning**: Only adjust if you observe real strangers scoring between your current TRIAGE_FLOOR and COSINE_THRESHOLD. Log scores from real testing on multiple people, then place the floor in the gap you find.

---

## Intrusion Detection Timing

### UNKNOWN_TRIGGER_FRAMES

- **File**: `src/guard_watch.py` line 110
- **Current Value**: `3`
- **Meaning**: Number of consecutive frames with unknown face required to trigger alert/lock
- **Rationale**: A single bad frame (motion blur, brief bad angle, lighting glitch) is common. 3 frames at ~10 FPS loop = ~0.3 seconds of sustained unknown face before reacting. This is fast enough to catch real threats but slow enough to ignore momentary false positives.
- **Higher** → Slower reaction, more false unknowns tolerated (but 10 consecutive frames = 1 second; too slow for security)
- **Lower** → Faster reaction (1 frame = instant), but more sensitive to noise
- **Tuning**: 3 is a good balance. Only change if you're seeing a specific problem (too many false locks = raise it; too many misses = lower it).

### ALERT_COOLDOWN_SECONDS

- **File**: `src/guard_watch.py` line 114
- **Current Value**: `60`
- **Meaning**: After triggering an alert/lock on an unknown face, don't alert again for at least this many seconds while the same presence lingers
- **Rationale**: If someone stays at your desk trying the door, you don't want 60 repeated "intruder!" messages—one is enough. This prevents alert spam.
- **Higher** → Fewer repeat alerts (good if you're spam-sensitive, bad if presence leaves/returns and you want to know)
- **Lower** → More frequent updates (good if you want to know the instant they leave, bad if it spams)
- **Tuning**: 60 seconds is reasonable. Adjust if you find repeat alerts during a real intrusion are helpful or annoying.

### TRIAGE_GRACE_SECONDS

- **File**: `src/guard_watch.py` line 120
- **Current Value**: `10`
- **Meaning**: If a triage dialog is sent, wait this long for your response. If no response, auto-lock anyway (fail-safe default is "lock", not "do nothing").
- **Higher** → More time to respond from your phone (good if network is slow), but slower security response
- **Lower** → Faster response (but might not give you enough time to tap a button)
- **Tuning**: 10 seconds is a reasonable balance. Only change if you consistently run out of time or find it too slow.

---

## Gesture Recognition

### SLEEP_GESTURE

- **File**: `src/guard_watch.py` line 184
- **Current Value**: `"Open_Palm"`
- **Meaning**: The built-in MediaPipe gesture that triggers sleep mode
- **Built-in Options**: `Closed_Fist`, `Open_Palm`, `Pointing_Up`, `Thumb_Down`, `Thumb_Up`, `Victory`, `ILoveYou`, or `None`
- **Tuning**: Change to a different built-in gesture if Open_Palm triggers accidentally. For example, `"Victory"` (peace sign).

### GESTURE_SCORE_THRESHOLD

- **File**: `src/guard_watch.py` line 185
- **Current Value**: `0.6`
- **Meaning**: Minimum MediaPipe confidence (0–1) for the built-in gesture to be considered detected
- **Higher** → Stricter, fewer false triggers (but might require exaggerated hand posture)
- **Lower** → Looser, easier to trigger (but more false positives)
- **Tuning**: 0.6 is reasonable. If Open_Palm triggers accidentally, raise to 0.7–0.8; if it doesn't trigger when you clearly hold it, lower to 0.5.

### GESTURE_HOLD_FRAMES

- **File**: `src/guard_watch.py` line 186
- **Current Value**: `15`
- **Meaning**: Number of consecutive frames the built-in gesture must be held to trigger action (roughly 1.5 seconds at ~10 FPS)
- **Rationale**: Prevents accidental triggers from brief hand motions; requires sustained hold
- **Higher** → Longer hold required (safer against accidents, but less responsive)
- **Lower** → Shorter hold required (more responsive, but more accident-prone)
- **Tuning**: 15 is reasonable. Adjust if you find it consistently over/under-triggers during normal use.

### CUSTOM_GESTURE_DISTANCE

- **File**: `src/guard_watch.py` line 195
- **Current Value**: `1.8`
- **Meaning**: Euclidean distance threshold for custom hand-gesture matching (lower = more similar)
- **Rationale**: Live-measured data showed:
  - Genuinely holding the trained gesture: 1.0–1.6
  - Not holding it (hand relaxed/moving): 6–10
  - Gap is huge, so 1.8 sits safely in the middle with margin on both sides
- **Higher** → Looser matching (more false positives)
- **Lower** → Stricter matching (might miss your gesture)
- **Tuning**: 1.8 is well-tuned from real data. Only adjust if testing shows consistent misses or false triggers. Log distances during testing to find your own hand's range.

### CUSTOM_GESTURE_HOLD_FRAMES

- **File**: `src/guard_watch.py` line 198
- **Current Value**: `5`
- **Meaning**: Number of consecutive frames a custom gesture must match to trigger (roughly 2 seconds at ~10 FPS, but leaky-streak means it's slower)
- **Rationale**: Leaky-streak accrual is slower than raw loop FPS suggests. 15 frames of built-in gesture = ~1.5s real hold; 5 frames of custom = ~2s.
- **Higher** → Longer hold required
- **Lower** → Shorter hold required
- **Tuning**: 5 is a starting guess. If your custom gesture keeps triggering unintentionally, raise it; if it doesn't trigger when you hold it, lower it.

### GESTURE_POST_UNLOCK_GRACE_SECONDS

- **File**: `src/guard_watch.py` line 142
- **Current Value**: `10`
- **Meaning**: After any unlock (real or false), ignore gesture triggers for this many seconds
- **Rationale**: Right after unlocking, your hands are near the keyboard/trackpad entering your password—accidental hand positions/motions might satisfy a loosely-tuned custom gesture. This grace period avoids re-tightening the gesture itself, which would undo usability tuning.
- **Higher** → Longer protection against accidental triggers (better during password entry)
- **Lower** → Shorter protection (more responsive if you want to gesture immediately)
- **Tuning**: 10 seconds is reasonable for a typical password entry window. Adjust if you find gesture triggers interfering with login.

---

## Hand-Shape Matching

### DEFAULT_DISTANCE_THRESHOLD (hand_shape.py)

- **File**: `src/hand_shape.py` line 19
- **Current Value**: `0.4`
- **Meaning**: Euclidean distance threshold when matching custom gestures (lower = more similar)
- **Note**: This is a fallback/documentation value. The actual threshold used in guard_watch.py is `CUSTOM_GESTURE_DISTANCE` (1.8). See that entry for tuning guidance.

---

## Voice Recognition

### SPEAKER_THRESHOLD

- **File**: `src/voice_wake.py` line 41
- **Current Value**: `0.55`
- **Meaning**: Minimum cosine similarity (0–1) between detected speech and your voice profile to trigger wake
- **Rationale**: Live-measured data showed a genuine attempt score as low as 0.582 (rejected under the old 0.75 default) while another scored 0.795. Real variance comes from background noise/mic distance/voice tone. 0.55 sits comfortably below the lowest genuine sample observed.
- **Higher** → Stricter speaker verification (fewer false wakes from other voices, but might reject you if the mic is far/noisy)
- **Lower** → Looser verification (anyone vaguely sounding like you might trigger wake)
- **Tuning**: 0.55 is conservative. If re-enrollment with cleaner samples tightens the observed range, this can come back up. If voice wake keeps rejecting you, lower it; if it keeps waking on other voices, raise it.

### WAKE_WORDS

- **File**: `src/voice_wake.py` line 35
- **Current Value**: `["wake", "up", "aaron"]`
- **Meaning**: The phrase to listen for (list of words; fuzzy matching requires most, not all)
- **Tuning**: Change to whatever you prefer. Common alternatives: `["hey", "aaron"]` or `["wake", "up", "guard"]`.

### WAKE_COOLDOWN_SECONDS

- **File**: `src/voice_wake.py` line 45
- **Current Value**: `5`
- **Meaning**: After triggering the wake phrase (successfully or not), ignore it for this many seconds
- **Rationale**: Prevents double-triggering on echoes or repeated attempts
- **Higher** → More protection against accidental re-triggers
- **Lower** → Can wake again sooner if the first attempt failed
- **Tuning**: 5 is reasonable. Adjust if you find voice_wake keeps waking twice in a row.

### DEFAULT_SPEAKER_THRESHOLD (voice_engine.py)

- **File**: `src/voice_engine.py` line 38
- **Current Value**: `0.75`
- **Meaning**: Fallback/documentation default for speaker similarity; actual threshold used is in voice_wake.py (0.55)
- **Note**: The actual tuned threshold in voice_wake.py (0.55) is lower than this documented default because of real-world noise/distance variance.

---

## Camera & Frame Management

### STATIC_FRAME_VARIANCE

- **File**: `src/guard_watch.py` line 151
- **Current Value**: `8000`
- **Meaning**: Laplacian variance threshold for detecting corrupted/static frames
- **Rationale**: Windows can suspend the camera when locked; some backends (DirectShow) feed garbage/static instead of recovering cleanly. Real frames have spatial correlation between neighboring pixels; pure static doesn't. High Laplacian variance = static detection.
- **Higher** → More lenient (only very obviously static frames trigger reconnect)
- **Lower** → Stricter (minor noise triggers reconnect, might be flaky)
- **Tuning**: 8000 is a reasonable starting point. If camera disconnects/reconnects too often, raise it; if corrupted frames persist, lower it.

### STATIC_FRAME_TRIGGER

- **File**: `src/guard_watch.py` line 152
- **Current Value**: `10`
- **Meaning**: Number of consecutive static frames before force-reconnecting the camera
- **Rationale**: Prevents single glitchy frame from triggering reconnect; requires a streak
- **Higher** → More lenient (tolerate longer glitches)
- **Lower** → Stricter (reconnect faster)
- **Tuning**: 10 is reasonable. Adjust if you see camera glitches lasting too long or reconnects happening too often.

### LOCK_POLL_SECONDS

- **File**: `src/guard_watch.py` line 164
- **Current Value**: `1.5`
- **Meaning**: Poll Windows lock state every 1.5 seconds (spawns tasklist, cheap operation)
- **Tuning**: 1.5 is fast enough to detect unlock quickly without wasting CPU. No real need to adjust.

---

## Temporal Smoothing (Live Webcam Recognition)

### SMOOTHING_WINDOW (recognize.py / security_watch.py)

- **File**: `src/recognize.py` line 30, `src/security_watch.py` line 35
- **Current Value**: `10`
- **Meaning**: Keep the last 10 face recognition results in a rolling window
- **Purpose**: Prevents flickering display when a single frame has motion blur or bad angle

### SMOOTHING_MIN_AGREEMENT (recognize.py / security_watch.py)

- **File**: `src/recognize.py` line 31, `src/security_watch.py` line 36
- **Current Value**: `6`
- **Meaning**: Only display a name once 6 of the last 10 frames agree on it
- **Example**: If 6 frames say "Person A", 3 say "Person B", 1 says "Unknown", display "Person A"

### MISS_GRACE_FRAMES (recognize.py / security_watch.py)

- **File**: `src/recognize.py` line 36, `src/security_watch.py` line 37
- **Current Value**: `10`
- **Meaning**: Allow 10 frames without a face detection before clearing the smoothing window
- **Rationale**: A single blink or motion blur shouldn't wipe the smoothing state; only persistent absence does

### SAMPLES_PER_POSE (capture_faces.py)

- **File**: `src/capture_faces.py` line 26
- **Current Value**: `30`
- **Meaning**: Collect 30 samples per pose (× 5 poses = 150 total images)
- **Tuning**: Increase for more training data (more robust recognition); decrease for faster capture.

### SAVE_COOLDOWN (capture_faces.py / capture_gesture.py)

- **File**: `src/capture_faces.py` line 27, `src/capture_gesture.py` line 27
- **Current Value**: `5` (faces), `4` (gestures)
- **Meaning**: Skip this many frames between saves to avoid near-duplicates/blur
- **Higher** → Fewer similar samples (more variety, but slower capture)
- **Lower** → More samples (faster capture, but more redundant near-duplicates)

### NUM_SAMPLES (capture_gesture.py)

- **File**: `src/capture_gesture.py` line 26
- **Current Value**: `30`
- **Meaning**: Collect 30 samples per custom gesture
- **Tuning**: Same as SAMPLES_PER_POSE—increase for robustness, decrease for speed.

### Pose Thresholds (capture_faces.py)

- **File**: `src/capture_faces.py` lines 32–33
- **YAW_TURN = 15**: Left/right head rotation threshold (degrees)
- **PITCH_TILT = 12**: Up/down head tilt threshold (degrees)
- **Tuning**: If pose validation feels too strict/loose, adjust these. Increase to require more exaggerated poses; decrease to accept subtle angles.

### Straight Pose Tolerance (capture_faces.py)

- **File**: `src/capture_faces.py` line 37
- **Current Check**: `abs(yaw) <= 10 and abs(pitch) <= 10`
- **Meaning**: "Straight" pose allows ±10° of deviation (less strict than LEFT/RIGHT/UP/DOWN)
- **Tuning**: Adjust if straight-on captures feel too restrictive

---

## Output Device

### OUTPUT_DEVICE_NAME

- **File**: `src/guard_watch.py` line 79
- **Current Value**: `"Speakers (2- Realtek"`
- **Meaning**: Speaker device to play alarm through (matched by substring)
- **Rationale**: Windows' default output device can be Bluetooth earbuds that aren't always worn. This targets a specific speaker instead. If alarm doesn't play, check your actual device name in Sound Settings or Device Manager.
- **Tuning**: Run `python -c "import sounddevice as sd; print(sd.query_devices())"` to see your device names, then update this string to match your speakers.

### INPUT_DEVICE_NAME (voice_engine.py)

- **File**: `src/voice_engine.py` line 19
- **Current Value**: `"Microphone Array"`
- **Meaning**: Microphone device to listen on (matched by substring)
- **Tuning**: Run `python -c "import sounddevice as sd; print(sd.query_devices())"` to find your mic name, then update this string.

---

## Watch (Pseudo-Live View) Timing

### WATCH_REFRESH_SECONDS

- **File**: `src/guard_watch.py` line 204
- **Current Value**: `2.0`
- **Meaning**: Update the pseudo-live photo every 2 seconds
- **Tuning**: Adjust for faster/slower refresh. Lower = snappier but more Telegram API calls.

### WATCH_MAX_DURATION_SECONDS

- **File**: `src/guard_watch.py` line 205
- **Current Value**: `120`
- **Meaning**: Pseudo-live view times out after 2 minutes (prevents infinite refresh if you forget /stopwatch)
- **Tuning**: Increase if you want longer watch sessions, decrease for shorter.

---

## Alert Cooldown (security_watch.py)

### ALERT_COOLDOWN_SECONDS (security_watch.py)

- **File**: `src/security_watch.py` line 41
- **Current Value**: `300` (5 minutes)
- **Meaning**: Send at most one alert this often while an unknown presence lingers (prevents spam)
- **Note**: This is different from guard_watch.py's ALERT_COOLDOWN_SECONDS (60 seconds) because security_watch.py is just for monitoring, not for locking.

---

## Miscellaneous

### TELEGRAM_POLL_TIMEOUT

- **File**: `src/aaron_listener.py` line 47
- **Current Value**: `25`
- **Meaning**: Timeout for long-polling Telegram (seconds)
- **Rationale**: Telegram's recommended timeout for efficient polling without hammering the API
- **Tuning**: No real need to adjust. 25 is standard.

### NUM_SAMPLES (enroll_voice.py)

- **File**: `src/enroll_voice.py` line 22
- **Current Value**: `6`
- **Meaning**: Collect 6 voice samples during enrollment
- **Tuning**: More samples = better voice profile (more robust to noise/distance). Fewer samples = faster enrollment.

### Sample Rate

- **File**: `src/voice_engine.py` line 33
- **Current Value**: `16000` (Hz)
- **Meaning**: Audio sample rate for Vosk and Resemblyzer
- **Note**: Don't change; this is hardcoded by Vosk and Resemblyzer requirements.

---

## Summary Table

| Constant | File | Value | Type | Tuning |
|----------|------|-------|------|--------|
| COSINE_THRESHOLD | guard_watch.py | 0.363 | float | Strictness of face match |
| TRIAGE_FLOOR | guard_watch.py | 0.05 | float | Borderline face handling |
| UNKNOWN_TRIGGER_FRAMES | guard_watch.py | 3 | int | Frames required before alert |
| ALERT_COOLDOWN_SECONDS | guard_watch.py | 60 | int | Minimum alert spacing |
| TRIAGE_GRACE_SECONDS | guard_watch.py | 10 | int | Triage response timeout |
| SLEEP_GESTURE | guard_watch.py | "Open_Palm" | str | Built-in sleep trigger |
| GESTURE_SCORE_THRESHOLD | guard_watch.py | 0.6 | float | Gesture confidence cutoff |
| GESTURE_HOLD_FRAMES | guard_watch.py | 15 | int | Built-in gesture hold time |
| CUSTOM_GESTURE_DISTANCE | guard_watch.py | 1.8 | float | Custom gesture match threshold |
| CUSTOM_GESTURE_HOLD_FRAMES | guard_watch.py | 5 | int | Custom gesture hold time |
| GESTURE_POST_UNLOCK_GRACE_SECONDS | guard_watch.py | 10 | int | Grace period after unlock |
| SPEAKER_THRESHOLD | voice_wake.py | 0.55 | float | Voice match strictness |
| WAKE_WORDS | voice_wake.py | ["wake", "up", "aaron"] | list | Wake phrase |
| WAKE_COOLDOWN_SECONDS | voice_wake.py | 5 | int | Wake trigger cooldown |
| STATIC_FRAME_VARIANCE | guard_watch.py | 8000 | int | Static frame detection |
| STATIC_FRAME_TRIGGER | guard_watch.py | 10 | int | Frames before reconnect |
| LOCK_POLL_SECONDS | guard_watch.py | 1.5 | float | Lock state polling interval |
| WATCH_REFRESH_SECONDS | guard_watch.py | 2.0 | float | Live view refresh rate |
| WATCH_MAX_DURATION_SECONDS | guard_watch.py | 120 | int | Live view timeout |
| OUTPUT_DEVICE_NAME | guard_watch.py | "Speakers (2- Realtek" | str | Alarm speaker |
| INPUT_DEVICE_NAME | voice_engine.py | "Microphone Array" | str | Audio input device |
| SAMPLES_PER_POSE | capture_faces.py | 30 | int | Training samples per pose |
| SAVE_COOLDOWN | capture_faces.py | 5 | int | Frame skip between saves |
| YAW_TURN | capture_faces.py | 15 | int | Left/right pose threshold |
| PITCH_TILT | capture_faces.py | 12 | int | Up/down pose threshold |
| NUM_SAMPLES | capture_gesture.py | 30 | int | Gesture training samples |
| SAVE_COOLDOWN | capture_gesture.py | 4 | int | Frame skip between saves |
| NUM_SAMPLES | enroll_voice.py | 6 | int | Voice enrollment samples |

---

## How to Adjust Constants

1. **Edit** the source file (e.g., `src/guard_watch.py`)
2. **Change** the constant value
3. **Save** the file
4. **Restart** the affected process(es):
   - If you changed guard_watch.py constants: `/sleep`, then `/wake`
   - If you changed voice_wake.py constants: `batch/stop_voice_wake.bat`, then re-launch
   - If you changed face_engine.py: Restart any script using it
5. **Test** thoroughly before deploying (e.g., test face recognition on different people/lighting before relying on auto-lock)

---

## Tuning Strategy

1. **Capture baseline data**: Run tests and log values you see (cosine scores, gesture distances, voice similarities)
2. **Identify the gap**: Where do your genuine samples cluster vs. false samples?
3. **Place the threshold**: Put the cutoff in the gap between genuine and false
4. **Add margin**: Thresholds should leave room for variance (noise, lighting, mic distance, etc.)
5. **Iterate**: If you see consistent misses or false positives, adjust and test again

Example: If you see your own face score 0.35–0.40 on good days and 0.15–0.30 on bad days, and strangers score 0.05–0.20, a TRIAGE_FLOOR of 0.05 and COSINE_THRESHOLD of 0.363 is reasonable (asks for human judgment on 0.05–0.363 range, locks on < 0.05).
