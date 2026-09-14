# aaron-the-guard-dog

Aaron is a webcam guard dog for Windows: he recognizes your face, locks the
PC when a stranger sits down, and reports to you over Telegram. He can be
woken by your voice, put to sleep with a hand gesture, and checked on
remotely from your phone.

## Documentation

- [Overview and first-time setup](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration and tuning](docs/CONFIGURATION.md)
- [Telegram commands](docs/TELEGRAM_COMMANDS.md)
- [Changelog](docs/CHANGELOG.md)

## License

The code in this repository is released under the [MIT License](LICENSE).

The pretrained models fetched by `src/download_models.py` are not part of
this repository and are not covered by that license. Each is a separate work
under its own license - check its source before redistributing:

- YuNet and SFace face models - [opencv/opencv_zoo](https://github.com/opencv/opencv_zoo)
- `lbfmodel.yaml` facial landmarks - [kurnianggoro/GSOC2017](https://github.com/kurnianggoro/GSOC2017)
- Gesture recognizer - [MediaPipe](https://github.com/google-ai-edge/mediapipe)
- Vosk speech model - [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models)
