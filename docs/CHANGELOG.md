# Aaron - Changelog

## 2026-09-14

**Public open-source release preparation.** Repository refactored for safe public publication on GitHub.

### Changes

- **New src/paths.py**: Single source of truth for file locations. Personal data (Telegram config, face/voice embeddings, gesture data, evidence photos, logs, guard_command.json) moved OUT of repo into private folder (default `%USERPROFILE%\Desktop\Aaron_Private`, override with `AARON_PRIVATE_DIR` environment variable).
- **New src/download_models.py**: Automated model downloader for all five third-party models (YuNet detector, SFace recognizer, MediaPipe gesture recognizer, facial landmarks, Vosk speech model). Verifies integrity via sha256 or minimum size, skips files already valid, and re-downloads corrupted ones. Safe to re-run.
- **New misc/examples/**: Template config files (`telegram_config.example.json`, `gesture_actions.example.json`) for cloners to copy into private folder.
- **Updated .gitignore**: Excludes all private data, logs, third-party models (downloaded separately), venv, and pycache.
- **Updated batch/ launchers**: All .bat and .vbs scripts now resolve paths relative to their own location (no hardcoded user-specific paths).
- **Updated README.md**: First-time setup now directs users to run `python src/download_models.py` instead of manual model download instructions.
- **Comprehensive documentation**: All docs updated to reflect new private folder structure, added "First-time Setup" guide, and removed personal information (usernames, personal names, hardcoded paths).

### Current Feature Set

**Face Recognition & Security**
- Modern embedding-based face recognition (YuNet detector + SFace embeddings)
- Automatic PC lock on unrecognized face detection
- Triage system: borderline matches get a Telegram button prompt (10s to respond) before auto-lock
- Distinguishes between "might be someone you know under bad lighting" (triage) vs. "definitely a stranger" (instant lock)
- Lock-state tracking: suppresses alerts while PC is locked, sends exactly one notification with photo on unlock
- Consecutive-frame validation: requires 3 frames of unknown face before triggering (avoids single-frame glitches)
- Evidence photos: timestamped, organized by day in private folder

**Telegram Remote Control**
- Single always-on listener process (aaron_listener.py) exclusively polls Telegram (prevents command-race bugs)
- Owner commands: `/wake`, `/sleep`, `/status`, `/sit`, `/guard`, `/snapshot`, `/watch`, `/stopwatch`, `/lock`, `/help`, `/fetch`
- Triage buttons: "I know them" / "Lock now" when uncertain face detected
- Friend handling: separate "play-only" keyboard (/pet, /treat, /goodboy) for non-owners; text/sticker/photo/GIF relay to owner
- Wake notification: friends are notified exactly once when Aaron wakes after sleeping
- Pseudo-live view: `/watch` refreshes the same photo every 2 seconds (up to 2 minutes) for near-real-time monitoring

**Voice-Activated Wake**
- Offline speech-to-text (Vosk) listens for custom wake phrase
- Speaker verification (Resemblyzer voice embeddings) confirms it's your voice, not just anyone
- Fuzzy phrase matching handles speech recognition errors
- 5-second cooldown prevents double-triggering on echoes

**Hand Gestures**
- Built-in gesture recognition (MediaPipe): sleep trigger (Open_Palm by default, configurable)
- Custom gesture support: capture your own gestures, map to actions (sleep, lock, snapshot, sit, guard)
- Normalized hand-shape matching (translation + scale invariant) for robust recognition
- Post-unlock grace period (10s) to ignore accidental gestures while entering password

**Training & Capture Tools**
- Face capture with head-pose validation (5 poses: straight, left, right, up, down; 30 samples each)
- Automatic face alignment via SFace model
- Simple model training: extract embeddings, save to JSON (no real "training", just feature extraction)
- Custom gesture capture and training
- Voice enrollment (6 samples minimum)

**Live Demo & Testing**
- `recognize.py`: Live webcam demo showing face recognition with temporal smoothing
- `security_watch.py`: Alternative with visible window + Telegram alerts (no auto-lock)
- Temporal smoothing: prevents label flicker (requires 6 of 10 frames to agree)
- Pose visualization: on-screen feedback during face capture

**Robustness & Reliability**
- Camera reconnect on frame corruption (Laplacian variance detection for post-lock DirectShow glitches)
- Static frame filtering prevents garbage frames from triggering false detections
- Temporal smoothing over 10 frames + 3-frame consecutive validation minimizes false alarms
- Local logging: activity tracked in private folder logs/
- Configurable thresholds: all matching/timing constants can be tuned via source constants

**Architecture**
- Three independent processes: guard_watch.py (main guard), aaron_listener.py (always-on Telegram switchboard), voice_wake.py (optional voice listener)
- Lightweight IPC via local JSON files (guard_command.json) instead of competing for Telegram API (avoids race conditions)
- Subprocess management: listener can start/stop guard regardless of how it was launched
- Clean separation: listener never touches camera, voice_wake never touches Telegram polling

**Deployment**
- Windows batch/VBS launchers for all operations (no manual Python invocation needed)
- Main menu (run.bat) provides options for all workflows
- Hidden-window startup via pythonw.exe (no console popups)
- Desktop shortcuts available for quick access
- Process-specific stop scripts (distinguish guard_watch from listener from voice_wake)

**Configuration**
- All constants documented with current values and tuning guidance
- Separate config file for secrets (telegram_config.json, never committed)
- Device selection by name (microphone, speaker) for stable operation across audio device changes
- Offline processing: nothing sent to third-party APIs except Telegram (all face/voice/gesture processing local)

### Documentation

Four comprehensive markdown files in `docs/`:
- **README.md**: Overview, feature list, quickstart, common issues
- **ARCHITECTURE.md**: Deep dive into process design, file purposes, IPC flow
- **CONFIGURATION.md**: Every tunable constant with current value and tuning guidance
- **TELEGRAM_COMMANDS.md**: Complete bot command & button reference
- **CHANGELOG.md**: This file

### Known Limitations

- Single person training only (each clone trains their own face embeddings)
- Custom gesture training requires manual configuration (no automatic action mapping)
- Gesture matching is shape-only (no motion/trajectory analysis)
- Voice recognition tuned for single speaker (Resemblyzer doesn't handle multiple enrolled speakers in same profile)
- Pseudo-live view limited to ~2 minute timeout (Telegram API throttle protection)
- Evidence photos are JPEG only (no video recording)
- Windows-only deployment (uses Windows-specific APIs: LockWorkStation, tasklist, Task Scheduler)

### Dependencies

- **opencv-contrib-python**: YuNet, SFace, MSMF webcam backend
- **numpy**: Numerical operations
- **requests**: Telegram API
- **mediapipe**: Hand gesture recognition
- **vosk**: Offline speech-to-text
- **resemblyzer**: Voice embeddings
- **sounddevice**: Audio I/O device selection
- **psutil**: Process management

See `misc/requirements.txt` for exact pinned versions.

### Project Structure

```
CV/
├── src/           (16 Python modules)
├── batch/         (5 .bat, 3 .vbs launchers)
├── misc/          (Models, configs, datasets, logs, evidence)
└── docs/          (This documentation)
```

### Future Enhancements

- Multiple person support (capture & train different people, display face label not just "Known")
- Motion-based gesture recognition (speed/trajectory, not just shape)
- Multi-speaker voice profiles
- Video evidence recording
- Desktop GUI (instead of batch menu)
- Web dashboard for remote monitoring
- Integration with other smart home/security systems
- Linux/Mac support (abstract OS-specific APIs)
