#!/usr/bin/env python3
"""
Pi 2 Agent - MQTT-enabled controller based on person_tracker_with_mood.py
"""

import cv2
import pantilthat
import time
import subprocess
import numpy as np
import random
import threading
import json
import paho.mqtt.client as mqtt

# ============================================================================
# MQTT CONFIGURATION
# ============================================================================
MQTT_BROKER = "169.254.34.179"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

TOPIC_GESTURES = "home/gestures"
TOPIC_PI2_STATUS = "home/pi2/status"
TOPIC_PI2_COMMANDS = "home/pi2/commands"

# ============================================================================
# TRACKING CONFIGURATION (from person_tracker_with_mood.py)
# ============================================================================
VOL_NEAR = 70
VOL_MID = 80
VOL_FAR = 100
REF_DISTANCE_FEET = 5.0
BOUND_NEAR_MID = 4.0
BOUND_MID_FAR = 6.0
VOLUME_SMOOTH_ALPHA = 0.3
DIST_SMOOTH_ALPHA = 0.15
MAX_DIST_STEP_FT = 0.5

Kp_pan = 0.02
Kd_pan = 0.015
dead_zone = 10.0
max_step = 3.0
error_smooth = 0.3
VOL_STEP = 10

MOOD_CHECK_INTERVAL = 60

FACE_CASCADE = "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"
PROFILE_CASCADE = "/usr/share/opencv/haarcascades/haarcascade_profileface.xml"
UPPER_BODY_CASCADE = "/usr/share/opencv/haarcascades/haarcascade_upperbody.xml"
EYE_CASCADE = "/usr/share/opencv/haarcascades/haarcascade_eye.xml"
SMILE_CASCADE = "/usr/share/opencv/haarcascades/haarcascade_smile.xml"

# ============================================================================
# GLOBAL STATE
# ============================================================================
mqtt_client = None
current_volume = VOL_FAR
manual_volume_override = None
tracking_enabled = True
auto_volume_enabled = True
is_tracking = False
current_distance = REF_DISTANCE_FEET
pan_angle = 0.0
tilt_angle = 0.0
current_mood = "neutral"

# ============================================================================
# VOLUME CONTROL
# ============================================================================
def set_volume(percent):
    global current_volume
    percent = max(0, min(100, int(percent)))
    current_volume = percent
    try:
        subprocess.run(
            ["amixer", "sset", "Headphone", f"{percent}%"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except:
        try:
            subprocess.run(
                ["amixer", "-D", "bluealsa", "sset", "F8:7D:76:AA:A8:8C - A2DP", f"{percent}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"[VOLUME] Error: {e}")

def adjust_volume(delta):
    global manual_volume_override
    new_vol = max(0, min(100, current_volume + delta))
    manual_volume_override = new_vol
    set_volume(new_vol)
    
    def clear_override():
        global manual_volume_override
        time.sleep(10)
        if manual_volume_override == new_vol:
            manual_volume_override = None
    threading.Thread(target=clear_override, daemon=True).start()

# ============================================================================
# MQTT CALLBACKS
# ============================================================================
def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connected to broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_GESTURES)
        client.subscribe(TOPIC_PI2_COMMANDS)
        print(f"[MQTT] Subscribed to {TOPIC_GESTURES}, {TOPIC_PI2_COMMANDS}")
        publish_status()
    else:
        print(f"[MQTT] Connection failed with code {rc}")

def on_mqtt_message(client, userdata, msg):
    global tracking_enabled, auto_volume_enabled, manual_volume_override, pan_angle, tilt_angle
    try:
        payload = json.loads(msg.payload.decode())
        
        if msg.topic == TOPIC_GESTURES:
            gesture_type = payload.get("type", "")
            if gesture_type in ["SWIPE_UP", "VOL_UP"]:
                adjust_volume(VOL_STEP)
            elif gesture_type in ["SWIPE_DOWN", "VOL_DOWN"]:
                adjust_volume(-VOL_STEP)
                
        elif msg.topic == TOPIC_PI2_COMMANDS:
            command = payload.get("command", "")
            print(f"[COMMAND] {command}")
            
            if command == "set_volume":
                level = payload.get("level", 50)
                manual_volume_override = level
                set_volume(level)
            elif command == "volume_up":
                adjust_volume(VOL_STEP)
            elif command == "volume_down":
                adjust_volume(-VOL_STEP)
            elif command == "tracking_enable":
                tracking_enabled = payload.get("enabled", True)
            elif command == "auto_volume_enable":
                auto_volume_enabled = payload.get("enabled", True)
                if auto_volume_enabled:
                    manual_volume_override = None
            elif command == "pan":
                angle = payload.get("angle", 0)
                pan_angle = max(-90, min(90, angle))
                pantilthat.pan(pan_angle)
            elif command == "tilt":
                angle = payload.get("angle", 0)
                tilt_angle = max(-90, min(90, angle))
                pantilthat.tilt(tilt_angle)
            elif command == "center":
                pan_angle = 0
                tilt_angle = 0
                pantilthat.pan(0)
                pantilthat.tilt(0)
            elif command == "status":
                publish_status()
                
    except Exception as e:
        print(f"[MQTT] Error: {e}")

def on_mqtt_disconnect(client, userdata, rc):
    print(f"[MQTT] Disconnected (rc={rc})")

def publish_status():
    if mqtt_client and mqtt_client.is_connected():
        payload = {
            "volume": current_volume,
            "distance_ft": round(current_distance, 1),
            "is_tracking": is_tracking,
            "tracking_enabled": tracking_enabled,
            "auto_volume_enabled": auto_volume_enabled,
            "manual_override": manual_volume_override is not None,
            "pan_angle": round(pan_angle, 1),
            "tilt_angle": round(tilt_angle, 1),
            "mood": current_mood,
            "timestamp": time.time()
        }
        mqtt_client.publish(TOPIC_PI2_STATUS, json.dumps(payload))

# ============================================================================
# TRACKING FUNCTIONS (from person_tracker_with_mood.py)
# ============================================================================
def create_tracker():
    try:
        return cv2.TrackerCSRT.create()
    except:
        pass
    try:
        return cv2.TrackerCSRT_create()
    except:
        pass
    if hasattr(cv2, 'legacy'):
        try:
            return cv2.legacy.TrackerCSRT_create()
        except:
            pass
        try:
            return cv2.legacy.TrackerKCF_create()
        except:
            pass
    try:
        return cv2.TrackerMIL.create()
    except:
        pass
    return None

def detect_person(frame, face_cascade, profile_cascade, upper_body_cascade):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))
    if len(faces) > 0:
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        expand = int(w * 0.3)
        x = max(0, x - expand)
        y = max(0, y - expand)
        w = min(frame.shape[1] - x, w + expand * 2)
        h = min(frame.shape[0] - y, h + expand * 2)
        return (x, y, w, h)
    if not profile_cascade.empty():
        profiles = profile_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))
        if len(profiles) > 0:
            x, y, w, h = max(profiles, key=lambda f: f[2] * f[3])
            expand = int(w * 0.3)
            x = max(0, x - expand)
            y = max(0, y - expand)
            w = min(frame.shape[1] - x, w + expand * 2)
            h = min(frame.shape[0] - y, h + expand * 2)
            return (x, y, w, h)
        flipped = cv2.flip(gray, 1)
        profiles = profile_cascade.detectMultiScale(flipped, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))
        if len(profiles) > 0:
            x, y, w, h = max(profiles, key=lambda f: f[2] * f[3])
            x = frame.shape[1] - x - w
            expand = int(w * 0.3)
            x = max(0, x - expand)
            y = max(0, y - expand)
            w = min(frame.shape[1] - x, w + expand * 2)
            h = min(frame.shape[0] - y, h + expand * 2)
            return (x, y, w, h)
    if not upper_body_cascade.empty():
        bodies = upper_body_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(80, 80))
        if len(bodies) > 0:
            x, y, w, h = max(bodies, key=lambda f: f[2] * f[3])
            return (x, y, w, h)
    return None

def analyze_mood(frame, face_bbox, eye_cascade, smile_cascade):
    x, y, w, h = [int(v) for v in face_bbox]
    x = max(0, x)
    y = max(0, y)
    w = min(frame.shape[1] - x, w)
    h = min(frame.shape[0] - y, h)
    
    if w <= 0 or h <= 0:
        return "neutral", 0
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    face_roi = gray[y:y+h, x:x+w]
    face_color = frame[y:y+h, x:x+w]
    
    eye_region = face_roi[0:h//2, :]
    eyes = eye_cascade.detectMultiScale(eye_region, 1.1, 10)
    
    mouth_region = face_roi[h//2:, :]
    smiles = smile_cascade.detectMultiScale(mouth_region, scaleFactor=1.8, minNeighbors=20, minSize=(25, 25))
    
    has_smile = len(smiles) > 0
    eyes_detected = len(eyes)
    brightness = np.mean(face_roi)
    contrast = np.std(face_roi)
    b, g, r = cv2.split(face_color)
    warmth = np.mean(r) - np.mean(b)
    
    mood_scores = {"happy": 0, "sad": 0, "energetic": 0, "calm": 0, "neutral": 0}
    
    if has_smile:
        mood_scores["happy"] += 3
        mood_scores["energetic"] += 1
    else:
        mood_scores["sad"] += 1
        mood_scores["calm"] += 1
    
    if brightness > 140:
        mood_scores["happy"] += 1
        mood_scores["energetic"] += 1
    elif brightness < 100:
        mood_scores["sad"] += 1
        mood_scores["calm"] += 1
    
    if contrast > 50:
        mood_scores["energetic"] += 1
        mood_scores["happy"] += 1
    else:
        mood_scores["calm"] += 2
    
    if eyes_detected >= 2:
        mood_scores["energetic"] += 1
        mood_scores["happy"] += 1
    elif eyes_detected < 2:
        mood_scores["calm"] += 1
        mood_scores["sad"] += 1
    
    if warmth > 20:
        mood_scores["happy"] += 1
    elif warmth < 0:
        mood_scores["sad"] += 1
    
    dominant_mood = max(mood_scores, key=mood_scores.get)
    total = sum(mood_scores.values())
    confidence = mood_scores[dominant_mood] / total * 100 if total > 0 else 0
    
    return dominant_mood, confidence

def lock_onto_person(cap, face_cascade, profile_cascade, upper_body_cascade):
    print("[TRACKING] Looking for person...")
    while tracking_enabled:
        ret, frame = cap.read()
        if not ret:
            continue
        bbox = detect_person(frame, face_cascade, profile_cascade, upper_body_cascade)
        if bbox is not None:
            x, y, w, h = bbox
            print(f"[TRACKING] Locked on at ({x}, {y}) size {w}x{h}")
            tracker = create_tracker()
            if tracker is None:
                print("[TRACKING] Using detection-only mode")
                return None, bbox, w * h
            try:
                success = tracker.init(frame, (x, y, w, h))
                if not success:
                    return None, bbox, w * h
            except Exception as e:
                print(f"[TRACKING] Tracker init error: {e}")
                return None, bbox, w * h
            print("[TRACKING] Started!")
            return tracker, bbox, w * h
        time.sleep(0.1)
    return None, None, 0

# ============================================================================
# MAIN TRACKING LOOP
# ============================================================================
def run_tracking():
    global is_tracking, current_distance, pan_angle, current_volume, manual_volume_override, current_mood
    
    LAST_MOOD_CHECK = time.time()
    
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    if not cap.isOpened():
        print("[CAMERA] Could not open - running MQTT-only mode")
        while True:
            time.sleep(5)
            publish_status()
    
    face_cascade = cv2.CascadeClassifier(FACE_CASCADE)
    profile_cascade = cv2.CascadeClassifier(PROFILE_CASCADE)
    upper_body_cascade = cv2.CascadeClassifier(UPPER_BODY_CASCADE)
    eye_cascade = cv2.CascadeClassifier(EYE_CASCADE)
    smile_cascade = cv2.CascadeClassifier(SMILE_CASCADE)
    
    tracker, bbox, ref_area = lock_onto_person(cap, face_cascade, profile_cascade, upper_body_cascade)
    use_tracker = tracker is not None
    
    pan = 0.0
    error_filtered = 0.0
    prev_error = 0.0
    vol_current = VOL_FAR
    distance_ft = REF_DISTANCE_FEET
    
    lost_frames = 0
    MAX_LOST_FRAMES = 45
    detect_interval = 3
    frame_count = 0
    status_count = 0
    
    set_volume(vol_current)
    
    try:
        while True:
            if not tracking_enabled:
                is_tracking = False
                time.sleep(0.1)
                status_count += 1
                if status_count % 50 == 0:
                    publish_status()
                continue
            
            ret, frame = cap.read()
            if not ret:
                continue
            
            h, w = frame.shape[:2]
            center_x = w / 2.0
            
            success = False
            
            if use_tracker and tracker is not None:
                success, bbox = tracker.update(frame)
            else:
                frame_count += 1
                if frame_count % detect_interval == 0:
                    detected = detect_person(frame, face_cascade, profile_cascade, upper_body_cascade)
                    if detected:
                        bbox = detected
                        success = True
            
            if success and bbox is not None:
                x, y, bw, bh = [int(v) for v in bbox]
                cx = x + bw / 2.0
                area = bw * bh
                lost_frames = 0
                is_tracking = True
                
                # Mood check
                now = time.time()
                if now - LAST_MOOD_CHECK >= MOOD_CHECK_INTERVAL:
                    faces = face_cascade.detectMultiScale(
                        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                        scaleFactor=1.2, minNeighbors=5, minSize=(50, 50)
                    )
                    if len(faces) > 0:
                        face_bbox = max(faces, key=lambda f: f[2] * f[3])
                        current_mood, conf = analyze_mood(frame, face_bbox, eye_cascade, smile_cascade)
                        print(f"[MOOD] Detected: {current_mood} ({conf:.0f}%)")
                    LAST_MOOD_CHECK = now
                
                # Pan control with PD
                raw_error = center_x - cx
                error_filtered = (1 - error_smooth) * error_filtered + error_smooth * raw_error
                error_deriv = error_filtered - prev_error
                prev_error = error_filtered
                
                if abs(error_filtered) > dead_zone:
                    delta = (error_filtered * Kp_pan) + (error_deriv * Kd_pan)
                    delta = max(-max_step, min(max_step, delta))
                    pan += delta
                    pan = max(-90.0, min(90.0, pan))
                    pantilthat.pan(pan)
                    pan_angle = pan
                
                # Distance estimation
                size_ratio = ref_area / float(area) if area > 0 else 1.0
                distance_raw = REF_DISTANCE_FEET * np.sqrt(size_ratio)
                
                delta_d = distance_raw - distance_ft
                if delta_d > MAX_DIST_STEP_FT:
                    distance_raw = distance_ft + MAX_DIST_STEP_FT
                elif delta_d < -MAX_DIST_STEP_FT:
                    distance_raw = distance_ft - MAX_DIST_STEP_FT
                
                distance_ft = (1.0 - DIST_SMOOTH_ALPHA) * distance_ft + DIST_SMOOTH_ALPHA * distance_raw
                distance_ft = max(1.0, min(15.0, distance_ft))
                current_distance = distance_ft
                
                # Auto-volume
                if auto_volume_enabled and manual_volume_override is None:
                    if distance_ft <= BOUND_NEAR_MID:
                        zone_vol = VOL_NEAR
                    elif distance_ft <= BOUND_MID_FAR:
                        zone_vol = VOL_MID
                    else:
                        zone_vol = VOL_FAR
                    
                    vol_current = (1.0 - VOLUME_SMOOTH_ALPHA) * vol_current + VOLUME_SMOOTH_ALPHA * zone_vol
                    set_volume(vol_current)
                
                print(f"pan={pan:.1f} dist={distance_ft:.1f}ft vol={current_volume}% mood={current_mood}")
                
            else:
                lost_frames += 1
                error_filtered *= 0.9
                prev_error *= 0.9
                is_tracking = False
                
                if lost_frames % 10 == 0:
                    print(f"[TRACKING] Lost ({lost_frames}/{MAX_LOST_FRAMES})")
                
                if lost_frames > MAX_LOST_FRAMES:
                    print("[TRACKING] Re-acquiring target...")
                    tracker, bbox, ref_area = lock_onto_person(cap, face_cascade, profile_cascade, upper_body_cascade)
                    use_tracker = tracker is not None
                    lost_frames = 0
                    error_filtered = 0.0
                    prev_error = 0.0
            
            # Publish status
            status_count += 1
            if status_count % 30 == 0:
                publish_status()
    
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        pantilthat.pan(0)
        print("[TRACKING] Stopped")

# ============================================================================
# MAIN
# ============================================================================
def main():
    global mqtt_client
    
    print("=" * 60)
    print("Pi 2 Agent - Starting")
    print("=" * 60)
    
    mqtt_client = mqtt.Client(client_id="pi2_agent")
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.on_disconnect = on_mqtt_disconnect
    
    mqtt_client.will_set(TOPIC_PI2_STATUS, json.dumps({
        "status": "offline",
        "timestamp": time.time()
    }))
    
    try:
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[MQTT] Failed to connect: {e}")
        print("[MQTT] Running offline")
    
    set_volume(VOL_FAR)
    
    try:
        run_tracking()
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down...")
    finally:
        publish_status()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("[MAIN] Goodbye!")

if __name__ == "__main__":
    main()
