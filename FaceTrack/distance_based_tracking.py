import cv2
import numpy as np
import subprocess
import time

VOL_NEAR = 40
VOL_MID = 70
VOL_FAR = 100

REF_DISTANCE_FEET = 5.0
BOUND_NEAR_MID = 4.0
BOUND_MID_FAR = 6.0

SMOOTH_ALPHA = 0.3
CAMERA_INDEX = 0
CONTROL_NAME = "Headphone"
MAX_MISS_FRAMES = 10

def set_system_volume(vol_percent):
    vol_percent = int(np.clip(vol_percent, 0, 150))
    subprocess.run(
        ["amixer", "set", CONTROL_NAME, f"{vol_percent}%"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print("Error: Cannot open camera")
    exit(1)

cap.set(3, 640)
cap.set(4, 480)

cascade_path = "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(cascade_path)
if face_cascade.empty():
    print("Error: failed to load cascade:", cascade_path)
    cap.release()
    exit(1)

print("Calibrating: stand about 5 feet from the camera and hold still")
ref_vals = []
start_time = time.time()
while time.time() - start_time < 3.0:
    ret, frame = cap.read()
    if not ret:
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.2,
        minNeighbors=5,
        minSize=(40, 40)
    )
    if len(faces) > 0:
        _, _, _, h = max(faces, key=lambda f: f[2] * f[3])
        ref_vals.append(h)
        print("Calib faces:", len(faces), "h:", h)
    else:
        print("Calib: no face")

if not ref_vals:
    print("Calibration failed: no face detected")
    cap.release()
    exit(1)

ref_face_height = float(sum(ref_vals) / len(ref_vals))
print("Calibrated face height:", ref_face_height)
print("Assuming that is", REF_DISTANCE_FEET, "feet")

smoothed_vol = VOL_MID
last_h = ref_face_height
miss_frames = 0
no_face_long = False

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(40, 40)
        )

        if len(faces) > 0:
            _, _, _, h = max(faces, key=lambda f: f[2] * f[3])
            last_h = h
            miss_frames = 0
            no_face_long = False
        else:
            miss_frames += 1
            if miss_frames <= MAX_MISS_FRAMES:
                h = last_h
                no_face_long = False
            else:
                no_face_long = True

        if not no_face_long:
            dist_factor = ref_face_height / float(h + 1e-6)
            est_distance_feet = REF_DISTANCE_FEET * dist_factor
        else:
            est_distance_feet = BOUND_MID_FAR + 1.0

        if est_distance_feet < BOUND_NEAR_MID:
            target_vol = VOL_NEAR
        elif est_distance_feet < BOUND_MID_FAR:
            target_vol = VOL_MID
        else:
            target_vol = VOL_FAR

        smoothed_vol = (1.0 - SMOOTH_ALPHA) * smoothed_vol + SMOOTH_ALPHA * target_vol
        final_vol = int(round(smoothed_vol / 5.0) * 5.0)

        set_system_volume(final_vol)
        print(
            f"dist≈{est_distance_feet:4.2f} ft, zone_vol={target_vol}%, vol={final_vol}%, miss={miss_frames}, no_face_long={no_face_long}",
            end="\r",
        )
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nStopping")
finally:
    cap.release()
