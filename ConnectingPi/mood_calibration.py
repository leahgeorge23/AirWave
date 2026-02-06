#!/usr/bin/env python3

import time
import json
import signal
import sys

import cv2
import numpy as np

try:
    from config import FACE_CASCADE_PATH, EYE_CASCADE_PATH, SMILE_CASCADE_PATH
except ImportError:
    _cascade_dir = cv2.data.haarcascades if hasattr(cv2, "data") else "/usr/share/opencv/haarcascades/"
    FACE_CASCADE_PATH = _cascade_dir + "haarcascade_frontalface_default.xml"
    EYE_CASCADE_PATH = _cascade_dir + "haarcascade_eye.xml"
    SMILE_CASCADE_PATH = _cascade_dir + "haarcascade_smile.xml"


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
    # biggest face
    return max(faces, key=lambda f: f[2] * f[3])


def analyze_face(frame, face_bbox, eye_cascade, smile_cascade):
    x, y, w, h = [int(v) for v in face_bbox]
    x = max(0, x)
    y = max(0, y)
    w = min(frame.shape[1] - x, w)
    h = min(frame.shape[0] - y, h)
    if w <= 0 or h <= 0:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    face_roi = gray[y : y + h, x : x + w]
    face_color = frame[y : y + h, x : x + w]

    eye_region = face_roi[0 : h // 2, :]
    eyes = eye_cascade.detectMultiScale(eye_region, 1.1, 10)

    mouth_region = face_roi[h // 2 :, :]
    smiles = smile_cascade.detectMultiScale(
        mouth_region, scaleFactor=1.8, minNeighbors=20, minSize=(25, 25)
    )

    has_smile = len(smiles) > 0
    eyes_detected = len(eyes)
    brightness = float(np.mean(face_roi))
    contrast = float(np.std(face_roi))
    b, g, r = cv2.split(face_color)
    warmth = float(np.mean(r) - np.mean(b))

    return {
        "brightness": brightness,
        "contrast": contrast,
        "warmth": warmth,
        "eyes_detected": eyes_detected,
        "has_smile": has_smile,
        "face_box": [x, y, w, h],
    }


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
    eye_cascade = cv2.CascadeClassifier(EYE_CASCADE_PATH)
    smile_cascade = cv2.CascadeClassifier(SMILE_CASCADE_PATH)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print("Could not open camera")
        return

    metrics = {
        "brightness": [],
        "contrast": [],
        "warmth": [],
        "eyes_detected": [],
        "has_smile": [],
    }

    last_print = 0.0
    print("Mood calibration running. Press Ctrl+C to stop.\n")

    def handle_exit(_sig, _frame):
        print("\nSummary:")
        summary = {
            "brightness": summarize(metrics["brightness"]),
            "contrast": summarize(metrics["contrast"]),
            "warmth": summarize(metrics["warmth"]),
            "eyes_detected": summarize(metrics["eyes_detected"]),
            "smile_rate": summarize(metrics["has_smile"]),
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

        data = analyze_face(frame, face_bbox, eye_cascade, smile_cascade)
        if not data:
            continue

        metrics["brightness"].append(data["brightness"])
        metrics["contrast"].append(data["contrast"])
        metrics["warmth"].append(data["warmth"])
        metrics["eyes_detected"].append(data["eyes_detected"])
        metrics["has_smile"].append(1 if data["has_smile"] else 0)

        now = time.time()
        if now - last_print >= PRINT_EVERY_S:
            last_print = now
            print(
                f"brightness={data['brightness']:.1f} "
                f"contrast={data['contrast']:.1f} "
                f"warmth={data['warmth']:.1f} "
                f"eyes={data['eyes_detected']} "
                f"smile={data['has_smile']}"
            )


if __name__ == "__main__":
    main()
