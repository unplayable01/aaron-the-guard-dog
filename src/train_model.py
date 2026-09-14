"""
Step 2: Compute SFace embeddings for every image in dataset/<name>/.

Usage:
    python train_model.py

Reads every subfolder of dataset/ (each image already an aligned face crop
saved by capture_faces.py), extracts a 128-d embedding per image, and writes
them to model_embeddings.json as {name: [[...128 floats...], ...]}.
Recognition later just finds the closest stored embedding by cosine
similarity - no "training" step in the LBPH sense, just feature extraction.
"""

import os
import json
import cv2

from face_engine import create_recognizer

import paths

DATASET_DIR = paths.private("dataset")
EMBEDDINGS_PATH = paths.private("model_embeddings.json")


def main():
    if not os.path.isdir(DATASET_DIR):
        print(f"No '{DATASET_DIR}' folder found. Run capture_faces.py first.")
        return

    names = sorted(
        d for d in os.listdir(DATASET_DIR)
        if os.path.isdir(os.path.join(DATASET_DIR, d))
    )
    if not names:
        print(f"No face folders found inside '{DATASET_DIR}'. Run capture_faces.py first.")
        return

    recognizer = create_recognizer()
    embeddings = {}

    for name in names:
        person_dir = os.path.join(DATASET_DIR, name)
        vectors = []
        for filename in os.listdir(person_dir):
            path = os.path.join(person_dir, filename)
            img = cv2.imread(path)
            if img is None:
                continue
            feature = recognizer.feature(img)
            vectors.append(feature.flatten().tolist())

        if not vectors:
            print(f"Warning: no usable images for '{name}', skipping.")
            continue

        embeddings[name] = vectors
        print(f"{name}: {len(vectors)} embeddings")

    if not embeddings:
        print("No embeddings computed.")
        return

    with open(EMBEDDINGS_PATH, "w") as f:
        json.dump(embeddings, f)

    total = sum(len(v) for v in embeddings.values())
    print(f"Saved {total} embeddings across {len(embeddings)} people to {EMBEDDINGS_PATH}")


if __name__ == "__main__":
    main()
