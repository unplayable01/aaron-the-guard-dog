"""
Download the pretrained models Aaron needs into misc/.

Usage:
    python src/download_models.py

These are third-party models (~170 MB total), kept out of the git repo.
Safe to re-run: files already present and valid are skipped, and a file
that fails verification is downloaded again.
"""

import hashlib
import os
import sys
import tempfile
import urllib.request
import zipfile

import paths

# sha256 is checked where the upstream file is fixed. The MediaPipe URL
# tracks "latest", so only a minimum size is enforced there - a pinned hash
# would break the day Google publishes an update.
MODELS = [
    {
        "name": "face_detection_yunet_2023mar.onnx",
        "purpose": "face detection",
        # media.githubusercontent.com, not raw.githubusercontent.com: the
        # latter serves a ~130-byte Git LFS pointer instead of the model.
        "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    },
    {
        "name": "face_recognition_sface_2021dec.onnx",
        "purpose": "face recognition",
        "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    },
    {
        "name": "lbfmodel.yaml",
        "purpose": "facial landmarks (pose check during face capture)",
        "url": "https://raw.githubusercontent.com/kurnianggoro/GSOC2017/master/data/lbfmodel.yaml",
        "sha256": "70dd8b1657c42d1595d6bd13d97d932877b3bed54a95d3c4733a0f740d1fd66b",
    },
    {
        "name": "gesture_recognizer.task",
        "purpose": "hand gestures",
        "url": "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task",
        "min_bytes": 1_000_000,
    },
]

VOSK = {
    "name": "vosk-model-small-en-us-0.15",
    "purpose": "offline speech recognition (voice wake)",
    "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "required_subdirs": ["am", "conf", "graph"],
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid(path, model):
    if not os.path.isfile(path):
        return False
    if "sha256" in model:
        return sha256_of(path) == model["sha256"]
    return os.path.getsize(path) >= model["min_bytes"]


def download(url, dest):
    """Streams to a .part file and renames at the end, so an interrupted
    download never leaves a half-written file that looks complete."""
    part = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as resp, open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r    {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()
    os.replace(part, dest)


def fetch_file(model):
    dest = paths.misc(model["name"])
    if is_valid(dest, model):
        print(f"[skip] {model['name']} - already present")
        return True

    print(f"[get ] {model['name']} ({model['purpose']})")
    try:
        download(model["url"], dest)
    except OSError as e:
        print(f"    FAILED: {e}")
        return False

    if not is_valid(dest, model):
        print("    FAILED: downloaded file did not pass verification - deleted")
        os.remove(dest)
        return False
    return True


def fetch_vosk():
    target = paths.misc(VOSK["name"])
    if all(os.path.isdir(os.path.join(target, d)) for d in VOSK["required_subdirs"]):
        print(f"[skip] {VOSK['name']} - already present")
        return True

    print(f"[get ] {VOSK['name']} ({VOSK['purpose']})")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "vosk.zip")
        try:
            download(VOSK["url"], zip_path)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(paths.MISC_DIR)
        except (OSError, zipfile.BadZipFile) as e:
            print(f"    FAILED: {e}")
            return False

    if not all(os.path.isdir(os.path.join(target, d)) for d in VOSK["required_subdirs"]):
        print("    FAILED: archive did not contain the expected model folders")
        return False
    return True


def main():
    os.makedirs(paths.MISC_DIR, exist_ok=True)
    print(f"Downloading models into {paths.MISC_DIR}\n")

    results = [fetch_file(m) for m in MODELS] + [fetch_vosk()]

    failed = results.count(False)
    print()
    if failed:
        print(f"{failed} model(s) failed - check your connection and re-run.")
        sys.exit(1)
    print("All models ready.")


if __name__ == "__main__":
    main()
