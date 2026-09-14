"""
Consolidate every captured gesture sample into gesture_model.json.

Usage:
    python train_gestures.py

Reads every subfolder of gesture_dataset/ (each *.json a normalized hand-
shape vector from capture_gesture.py) and writes gesture_model.json as
{name: [[...63 floats...], ...]}. No real "training" happens - matching is
just nearest-neighbor distance against these saved examples.
"""

import os
import json

import paths

DATASET_DIR = paths.private("gesture_dataset")
MODEL_PATH = paths.private("gesture_model.json")


def main():
    if not os.path.isdir(DATASET_DIR):
        print(f"No '{DATASET_DIR}' folder found. Run capture_gesture.py first.")
        return

    names = sorted(
        d for d in os.listdir(DATASET_DIR)
        if os.path.isdir(os.path.join(DATASET_DIR, d))
    )
    if not names:
        print(f"No gesture folders found inside '{DATASET_DIR}'. Run capture_gesture.py first.")
        return

    model = {}
    for name in names:
        person_dir = os.path.join(DATASET_DIR, name)
        vectors = []
        for filename in os.listdir(person_dir):
            path = os.path.join(person_dir, filename)
            try:
                with open(path) as f:
                    vectors.append(json.load(f))
            except (OSError, json.JSONDecodeError):
                continue

        if not vectors:
            print(f"Warning: no usable samples for '{name}', skipping.")
            continue

        model[name] = vectors
        print(f"{name}: {len(vectors)} samples")

    if not model:
        print("No gesture samples found.")
        return

    with open(MODEL_PATH, "w") as f:
        json.dump(model, f)

    total = sum(len(v) for v in model.values())
    print(f"Saved {total} samples across {len(model)} gestures to {MODEL_PATH}")


if __name__ == "__main__":
    main()
