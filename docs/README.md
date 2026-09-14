# Aaron - Webcam Face-Recognition Guard for Windows

Aaron is a Python-based security system for Windows that watches your webcam in the background and locks your PC when it detects an unrecognized face. It combines modern face detection (OpenCV YuNet) and face recognition (SFace embeddings) with Telegram remote control, voice-activated wake, and custom hand gesture triggers.

## Features

- **Face Recognition**: Modern embedding-based recognition (SFace) that generalizes across distance, lighting, and angle far better than older texture-matching algorithms
- **Intelligent Intrusion Detection**: Detects unrecognized faces and locks the PC automatically (with a triage step for borderline cases)
- **Telegram Remote Control**: Start/stop Aaron, get snapshots, watch pseudo-live feeds, and receive alerts directly from your phone
- **Voice-Activated Wake**: Say your custom wake phrase and Aaron starts listening—completely offline via Vosk
- **Speaker Verification**: Voice wake confirms it's actually your voice, not just anyone saying the phrase (via Resemblyzer embeddings)
- **Custom Hand Gestures**: Define your own gestures (e.g., peace sign = lock, thumbs up = sleep) and map them to actions
- **Persistent Logging**: Activity logs and timestamped security photos saved locally in private folder
- **Lock-State Tracking**: Stops sending redundant alerts while the PC is already locked; sends exactly one photo when unlocked
- **Post-Unlock Grace Period**: Ignores accidental hand gestures for 10 seconds after unlock (when you're entering your password)

## Project Layout

The repository is split into two parts:

**In the repo (src/, batch/, misc/, docs/):**
- **src/**: All Python source code
- **batch/**: Windows batch and VBS launchers
- **misc/**: Shareable assets (models, requirements.txt, alarm.wav)
- **docs/**: This documentation

**Outside the repo (private folder, default `%USERPROFILE%\Desktop\Aaron_Private`, or override with `AARON_PRIVATE_DIR` env var):**
- Personal data: Telegram config, face/voice/gesture data, evidence photos, logs, runtime state
- Never committed to version control for safety

```
CV/ (repository)
├── src/                              # All Python source files
│   ├── paths.py                     # Single source of truth for file locations
│   ├── guard_watch.py               # Main headless guard process (Aaron)
│   ├── aaron_listener.py            # Always-on Telegram listener
│   ├── voice_wake.py                # Voice-activated wake
│   │
│   ├── face_engine.py               # Face detection + recognition (YuNet + SFace)
│   ├── capture_faces.py             # Capture training photos (5 poses)
│   ├── train_model.py               # Extract embeddings
│   ├── recognize.py                 # Live webcam demo
│   │
│   ├── head_pose.py                 # Head pose estimation
│   ├── gesture.py                   # Built-in gesture recognition (MediaPipe)
│   ├── hand_shape.py                # Custom gesture matching
│   ├── capture_gesture.py           # Capture gesture examples
│   ├── train_gestures.py            # Train gesture model
│   │
│   ├── voice_engine.py              # Vosk + Resemblyzer utilities
│   ├── enroll_voice.py              # Build voice profile
│   │
│   └── security_watch.py            # Alternative: visible window + alerts
│
├── batch/                            # Windows launchers
│   ├── run.bat                       # Main menu
│   ├── run_guard_hidden.vbs          # Launch guard_watch.py (headless)
│   ├── stop_guard.bat                # Stop guard
│   ├── run_listener_hidden.vbs       # Launch listener (headless)
│   ├── stop_listener.bat             # Stop listener
│   ├── run_voice_wake_hidden.vbs     # Launch voice_wake.py
│   ├── stop_voice_wake.bat           # Stop voice_wake
│   └── system_check.bat              # Verify dependencies
│
├── misc/                             # Shareable assets (repo-tracked)
│   ├── examples/
│   │   ├── telegram_config.example.json      # Template: copy to private folder
│   │   └── gesture_actions.example.json      # Template: copy to private folder
│   │
│   ├── face_detection_yunet_2023mar.onnx    # YuNet detector (download)
│   ├── face_recognition_sface_2021dec.onnx  # SFace recognizer (download)
│   ├── gesture_recognizer.task              # MediaPipe gesture (download)
│   ├── lbfmodel.yaml                        # Face landmarks (download)
│   ├── vosk-model-small-en-us-0.15/         # Vosk model (download)
│   │
│   ├── alarm.wav                     # Alarm sound (included)
│   └── requirements.txt              # Python dependencies
│
└── docs/                             # Documentation
    ├── README.md                     # This file
    ├── ARCHITECTURE.md               # Process design
    ├── CONFIGURATION.md              # Tunable constants
    ├── TELEGRAM_COMMANDS.md          # Bot commands
    └── CHANGELOG.md                  # Version history

Aaron_Private/ (private folder, default Desktop/Aaron_Private)
├── telegram_config.json              # Bot token, chat IDs (NEVER share!)
├── model_embeddings.json             # Trained face embeddings
├── voice_profile.json                # Your voice embeddings
├── gesture_model.json                # Custom gesture models
├── gesture_actions.json              # Gesture → action mapping
│
├── dataset/                          # Face training data
│   └── <person>/*.jpg                # ~150 aligned crops per person
│
├── gesture_dataset/                  # Custom gesture training data
│   └── <gesture_name>/*.json         # Hand-shape vectors
│
├── evidence/                         # Security photos
│   └── YYYY-MM-DD/
│       └── HH-MM-SS_category_note.jpg
│
├── logs/
│   ├── guard_watch.log               # Guard activity
│   ├── aaron_listener.log            # Listener activity
│   └── voice_wake.log                # Voice wake activity
│
└── guard_command.json                # IPC relay (internal use)
```

## First-Time Setup (For People Cloning This Repo)

### 1. Prerequisites

- Windows 10+ with Python 3.9+
- Webcam
- Microphone (optional, only if using voice wake)
- Telegram account (for remote control)

### 2. Create Virtual Environment & Install Dependencies

```cmd
cd path\to\this\repo
python -m venv venv
venv\Scripts\pip install -r misc\requirements.txt
```

### 3. Download Models

The large model files are not included in the repo but are downloaded on demand. After installing dependencies, run:

```cmd
python src/download_models.py
```

This script downloads all five third-party models (~170 MB total) into `misc/`:
- YuNet face detector (~7 MB)
- SFace face recognizer (~23 MB)
- MediaPipe gesture recognizer (~27 MB)
- Facial landmarks (lbfmodel.yaml, ~100 KB)
- Vosk speech recognition model (~40 MB)

The script verifies all files (sha256 hash where the upstream file is fixed; minimum size for the MediaPipe 'latest' file), skips files already present and valid, and re-downloads corrupted ones. Safe to re-run anytime.

### 4. Create Private Folder & Copy Example Configs

By default, personal data lives in `%USERPROFILE%\Desktop\Aaron_Private` (override with `AARON_PRIVATE_DIR` environment variable).

Create the folder and copy the example configs:

```cmd
mkdir %USERPROFILE%\Desktop\Aaron_Private
copy misc\examples\telegram_config.example.json %USERPROFILE%\Desktop\Aaron_Private\telegram_config.json
copy misc\examples\gesture_actions.example.json %USERPROFILE%\Desktop\Aaron_Private\gesture_actions.json
```

### 5. Configure Telegram

1. Create a Telegram bot via BotFather (@BotFather on Telegram)
2. Get your chat ID:
   - Message @userinfobot and it will tell you your chat ID
   - Or message your new bot and note the chat ID from the updates
3. Edit `%USERPROFILE%\Desktop\Aaron_Private\telegram_config.json`:
   ```json
   {
     "bot_token": "YOUR_BOT_TOKEN_HERE",
     "chat_id": "YOUR_CHAT_ID_HERE",
     "friends": {}
   }
   ```
   Replace the placeholder values (no quotes around numbers). Leave "friends" empty for now.

### 6. Train Face Recognition

```cmd
batch\run.bat
```

Choose:
- **Option 1**: Capture faces
  - Follow prompts to capture 150 images (30 samples × 5 head poses)
  - Look straight ahead, then turn left, right, look up, look down
  - Green feedback when pose matches

- **Option 2**: Train model
  - Extracts face embeddings and saves to `private/model_embeddings.json`

- **Option 3**: Recognize (optional demo)
  - Live webcam test of the trained model

Or use **Option 4** (Full pipeline) to do all three at once.

### 7. Start Aaron

From `batch/run.bat`:
- **Option 6**: Start guard NOW
- Or create a desktop shortcut pointing to `batch/run_guard_hidden.vbs`

### 8. Control via Telegram

Send commands to your bot:
- `/wake` - Start Aaron
- `/sleep` - Stop Aaron
- `/status` - Check if running
- `/snapshot` - Get a photo
- `/watch` - Live view (2 min, updates every 2s)
- `/sit` - Pause guarding
- `/guard` - Resume guarding
- `/lock` - Lock PC immediately
- `/help` - List all commands

See [TELEGRAM_COMMANDS.md](TELEGRAM_COMMANDS.md) for complete reference.

## Optional: Voice-Activated Wake

To wake Aaron by saying a phrase:

```cmd
batch\run.bat -> Option 12: Enroll your voice
```

Say "Wake up Aaron" 6 times, then:

```cmd
batch\run.bat -> Option 13: Start voice wake listener
```

Voice_wake.py will now run in the background and start guard_watch.py when it hears you say the phrase.

## Optional: Custom Hand Gestures

Define your own gestures:

```cmd
batch\run.bat -> Option 10: Capture a custom gesture
```

Hold the gesture steady for ~30 frames. Then:

```cmd
batch\run.bat -> Option 11: Train gestures
```

Map gestures to actions in `%USERPROFILE%\Desktop\Aaron_Private\gesture_actions.json`:
```json
{
  "peace_sign": "lock",
  "thumbs_up": "guard"
}
```

Available actions: `sleep`, `lock`, `snapshot`, `sit`, `guard`.

## Architecture Overview

Aaron consists of three independent processes:

1. **guard_watch.py** (Aaron the guard dog):
   - Watches the webcam continuously (headless, no window)
   - Detects and recognizes faces via YuNet + SFace
   - Locks the PC instantly when it sees an unrecognized face
   - Responds to Telegram commands relayed by the listener
   - Responds to hand gestures (built-in + custom)
   - Logs activity to `private/logs/guard_watch.log`
   - Saves evidence photos to `private/evidence/`

2. **aaron_listener.py** (The always-on switchboard):
   - Starts at Windows login (runs via Task Scheduler or manual startup folder shortcut)
   - Long-polls Telegram for commands from you (and forwards others to the owner)
   - Starts/stops guard_watch.py as a subprocess via `/wake` and `/sleep`
   - Relays other commands to guard_watch.py via `private/guard_command.json`
   - Handles friend interactions (play commands, message relay)
   - Logs activity to `private/logs/aaron_listener.log`

3. **voice_wake.py** (Voice-activated listener):
   - Optional, runs in background if voice-activated wake is set up
   - Listens for the wake phrase via Vosk (offline speech-to-text)
   - Verifies the speaker is you via Resemblyzer voice embeddings
   - Starts guard_watch.py if speaker matches your voice profile
   - Logs activity to `private/logs/voice_wake.log`

See [ARCHITECTURE.md](ARCHITECTURE.md) for full process design and file-by-file breakdown.

## Common Issues

**"Could not open webcam"**
- Another process has the camera (guard_watch.py, recognize.py, voice_wake.py)
- Use `batch/stop_guard.bat`, `batch/stop_listener.bat` etc. to release it

**Webcam feed looks corrupted after locking**
- DirectShow/Frame Server sometimes feeds static/garbage after resuming from a lock
- Aaron detects this via Laplacian variance and auto-recovers (closes/reopens the camera)

**Telegram commands not working**
- Verify private folder's `telegram_config.json` has valid bot_token and chat_id (no placeholder strings)
- Check logs: `%USERPROFILE%\Desktop\Aaron_Private\logs\guard_watch.log` and `aaron_listener.log`
- Ensure aaron_listener.py is running (it's the only Telegram poller)

**"config.json not found" error**
- Check that private folder path is correct (default `%USERPROFILE%\Desktop\Aaron_Private`)
- To use a custom location, set environment variable: `set AARON_PRIVATE_DIR=C:\path\to\private`
- Ensure `telegram_config.json` was copied to private folder from `misc/examples/`

**False positives (locking on people you know)**
- Your embeddings might be weak (captured under bad lighting/angle)
- Re-run `capture_faces.py` with better lighting/varied angles
- Raise `TRIAGE_FLOOR` threshold in `src/guard_watch.py` to see triage dialog more often

**Voice wake not triggering**
- Check private folder logs: `logs/voice_wake.log` to see what it's hearing
- Re-run `enroll_voice.py` with clearer pronunciation
- Lower `SPEAKER_THRESHOLD` in `src/voice_wake.py` if rejected too often

## Security Notes

- **Token & Chat IDs**: Never share your telegram_config.json—it contains your bot token and chat IDs
- **Private Folder**: Kept outside the repo by design so it's never accidentally committed
- **Local Processing**: All face, gesture, and voice processing happens offline—nothing sent to third-party APIs except Telegram
- **Evidence Photos**: Security photos saved locally in `private/evidence/` and survive even if Telegram fails

## Dependencies

See `misc/requirements.txt`:
- **opencv-contrib-python**: YuNet + SFace face recognition, webcam capture, head pose estimation
- **numpy**: Numerical operations
- **requests**: Telegram API calls
- **mediapipe**: Hand gesture recognition
- **vosk**: Offline speech-to-text
- **resemblyzer**: Voice speaker verification
- **sounddevice**: Audio input/output device selection
- **psutil**: Process management

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) for a deep dive into process design and file purposes
- Read [CONFIGURATION.md](CONFIGURATION.md) to understand and tune thresholds
- Read [TELEGRAM_COMMANDS.md](TELEGRAM_COMMANDS.md) for complete command reference
- Check [CHANGELOG.md](CHANGELOG.md) for release history
