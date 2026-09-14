"""
Single source of truth for where files live.

Two roots, deliberately separate so the repo can be published safely:
  MISC_DIR    - shareable assets inside the repo: downloaded models,
                requirements.txt, the generated alarm sound.
  PRIVATE_DIR - everything personal, kept OUTSIDE the repo: Telegram bot
                token and chat IDs, face/voice biometrics, gesture data,
                evidence photos, logs, runtime state.

PRIVATE_DIR defaults to Desktop/Aaron_Private; set the AARON_PRIVATE_DIR
environment variable to put it anywhere else.
"""

import os

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
MISC_DIR = os.path.join(PROJECT_DIR, "misc")

PRIVATE_DIR = os.environ.get("AARON_PRIVATE_DIR") or os.path.join(
    os.path.expanduser("~"), "Desktop", "Aaron_Private"
)
LOGS_DIR = os.path.join(PRIVATE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


def misc(*parts):
    return os.path.join(MISC_DIR, *parts)


def private(*parts):
    return os.path.join(PRIVATE_DIR, *parts)


def log_file(name):
    return os.path.join(LOGS_DIR, name)
