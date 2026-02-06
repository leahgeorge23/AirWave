#!/usr/bin/env python3

import time
import json
import signal
import sys

import cv2
import numpy as np

try:
    from deepface import DeepFace
except Exception as e:
    print(f"DeepFace import error: {e}")
    sys.exit(1)

try:
    from config import FACE_CASCADE_PATH
except ImportError:
    _cascade_dir = cv2.data.haarcascades if hasattr(cv2, "data") else "/usr/share/opencv/haarcascades/"
    FACE_CASCADE_PATH = _cascade_dir + "haarcascade_frontalface_default.xml"


PRINT_EVERY_S = 2.0
MIN_FACE_SIZE = (50, 50)


def detect_face(frame, face_cascade):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.2,
        minNeighbors=5,
        minSize=MIN_FACE_SIZE,
    )
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def summarize(values):
    if not values:
        return {"count": 0}
    arr = np.array(values, dtype=float)
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
    }


def main():
    face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print("Could not open camera")
        return

    metrics = {
        "deepface_dominant": [],
        "deepface_neutral": [],
        "deepface_happy": [],
        "deepface_sad": [],
        "deepface_surprise": [],
    }

    last_print = 0.0
    print("DeepFace calibration running. Press Ctrl+C to stop.\n")

    def handle_exit(_sig, _frame):
        print("\nSummary:")
        summary = {
            "dominant_counts": {
                "neutral": metrics["deepface_dominant"].count("neutral"),
                "happy": metrics["deepface_dominant"].count("happy"),
                "sad": metrics["deepface_dominant"].count("sad"),
                "surprise": metrics["deepface_dominant"].count("surprise"),
            },
            "neutral_score": summarize(metrics["deepface_neutral"]),
            "happy_score": summarize(metrics["deepface_happy"]),
            "sad_score": summarize(metrics["deepface_sad"]),
            "surprise_score": summarize(metrics["deepface_surprise"]),
        }
        print(json.dumps(summary, indent=2))
        cap.release()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        face_bbox = detect_face(frame, face_cascade)
        if face_bbox is None:
            continue

        x, y, w, h = [int(v) for v in face_bbox]
        x = max(0, x)
        y = max(0, y)
        w = min(frame.shape[1] - x, w)
        h = min(frame.shape[0] - y, h)
        if w <= 0 or h <= 0:
            continue

        face_color = frame[y : y + h, x : x + w]
        try:
            result = DeepFace.analyze(
                face_color,
                actions=["emotion"],
                enforce_detection=False
            )
            if isinstance(result, list) and result:
                result = result[0]
            emotion = result.get("dominant_emotion") if isinstance(result, dict) else None
            scores = result.get("emotion", {}) if isinstance(result, dict) else {}
        except Exception:
            continue

        if emotion:
            metrics["deepface_dominant"].append(emotion)
        for key in ("neutral", "happy", "sad", "surprise"):
            if key in scores:
                metrics[f"deepface_{key}"].append(float(scores[key]))

        now = time.time()
        if now - last_print >= PRINT_EVERY_S:
            last_print = now
            print(
                f"dominant={emotion} "
                f"neutral={scores.get('neutral', 0):.1f} "
                f"happy={scores.get('happy', 0):.1f} "
                f"sad={scores.get('sad', 0):.1f} "
                f"surprise={scores.get('surprise', 0):.1f}"
            )


if __name__ == "__main__":
    main()
