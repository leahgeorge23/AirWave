#!/usr/bin/env python3

import cv2
import pantilthat
import time
import subprocess
import numpy as np
import random
import threading
import json
import re
import shutil
import os
import paho.mqtt.client as mqtt
import spotify_controller as spotify

# ============================================================================
# CONFIGURATION - EDIT config.py OR SET ENVIRONMENT VARIABLES
# ============================================================================
# To configure for a new computer, either:
#   1. Edit config.py (recommended)
#   2. Set environment variables:
#      export MQTT_BROKER="your-computer.local"
#      export SPEAKER_MAC="XX:XX:XX:XX:XX:XX"
# ============================================================================
try:
    from config import (
        MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE,
        BLUETOOTH_SPEAKER_MAC, BLUETOOTH_SPEAKER_NAME,
        FACE_CASCADE_PATH, PROFILE_CASCADE_PATH, UPPER_BODY_CASCADE_PATH,
        EYE_CASCADE_PATH, SMILE_CASCADE_PATH
    )
except ImportError:
    # Fallback if config.py doesn't exist
    MQTT_BROKER_DEFAULT = "localhost"
    MQTT_BROKER = os.environ.get("MQTT_BROKER", MQTT_BROKER_DEFAULT)
    MQTT_PORT = 1883
    MQTT_KEEPALIVE = 60
    BLUETOOTH_SPEAKER_MAC = os.environ.get("SPEAKER_MAC", "F8:7D:76:AA:A8:8C")  # <-- CHANGE THIS
    BLUETOOTH_SPEAKER_NAME = "A2DP"
    _cascade_dir = cv2.data.haarcascades if hasattr(cv2, 'data') else "/usr/share/opencv/haarcascades/"
    FACE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_frontalface_default.xml")
    PROFILE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_profileface.xml")
    UPPER_BODY_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_upperbody.xml")
    EYE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_eye.xml")
    SMILE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_smile.xml")

TOPIC_GESTURES = "home/gestures"
TOPIC_PI2_STATUS = "home/pi2/status"
TOPIC_PI2_COMMANDS = "home/pi2/commands"
TOPIC_MOOD = "home/mood"


mqtt_client = None
manual_volume_override = None
tracking_enabled = True
auto_volume_enabled = True
ref_area = None
recalibrate_requested = False

# Global state for dashboard
current_volume = 100
current_distance = 5.0
current_pan = 0.0
current_tilt = 0.0
home_pan = 0.0
home_tilt = 0.0
is_tracking = False
current_mood = "neutral"

VOL_NEAR = 70
VOL_MID = 80
VOL_FAR = 100
REF_DISTANCE_FEET = 5.0
BOUND_NEAR_MID = 4.0
BOUND_MID_FAR = 6.0
VOLUME_SMOOTH_ALPHA = 0.3
DIST_SMOOTH_ALPHA = 0.15
MAX_DIST_STEP_FT = 0.5

GESTURE_VOLUME_STEP = 13
MEDIA_SEEK_SECONDS = 10

Kp_pan = 0.02
Kd_pan = 0.015
dead_zone = 10.0
max_step = 3.0
error_smooth = 0.3

MOOD_CHECK_INTERVAL = 15
LAST_MOOD_CHECK = 0

USE_DEEPFACE = 0
DEEPFACE_MAX_SECONDS = 0.6
DEEPFACE_AVAILABLE = False
deepface_enabled = USE_DEEPFACE
RESET_PAN_ON_EXIT = os.environ.get("RESET_PAN_ON_EXIT", "0") == "1"
TILT_INVERT = 0
PAN_INVERT = os.environ.get("PAN_INVERT", "1") == "0"

if USE_DEEPFACE:
    try:
        from deepface import DeepFace
        DEEPFACE_AVAILABLE = True
    except Exception:
        DEEPFACE_AVAILABLE = False

# Cascade paths loaded from config.py
FACE_CASCADE = FACE_CASCADE_PATH
PROFILE_CASCADE = PROFILE_CASCADE_PATH
UPPER_BODY_CASCADE = UPPER_BODY_CASCADE_PATH
EYE_CASCADE = EYE_CASCADE_PATH
SMILE_CASCADE = SMILE_CASCADE_PATH

PLAYLISTS = {
    "happy": [
        ("Happy Hits", "https://open.spotify.com/playlist/37i9dQZF1DXdPec7aLTmlC"),
        ("Feel Good Friday", "https://open.spotify.com/playlist/37i9dQZF1DX3rxVfibe1L0"),
        ("Mood Booster", "https://open.spotify.com/playlist/37i9dQZF1DX3rxVfibe1L0"),
    ],
    "sad": [
        ("Sad Songs", "https://open.spotify.com/playlist/37i9dQZF1DX7qK8ma5wgG1"),
        ("Life Sucks", "https://open.spotify.com/playlist/37i9dQZF1DX3YSRoSdA634"),
        ("Melancholy", "https://open.spotify.com/playlist/37i9dQZF1DX64Y3du11rR1"),
    ],
    "calm": [
        ("Peaceful Piano", "https://open.spotify.com/playlist/37i9dQZF1DX4sWSpwq3LiO"),
        ("Deep Focus", "https://open.spotify.com/playlist/37i9dQZF1DWZeKCadgRdKQ"),
        ("Chill Vibes", "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6"),
    ],
    "neutral": [
        ("Today's Top Hits", "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"),
        ("All Out 2020s", "https://open.spotify.com/playlist/37i9dQZF1DX2M1RktxUUHG"),
        ("Discover Weekly", "https://open.spotify.com/playlist/37i9dQZF1EIUb849WSMPqL"),
    ],
}

# ============================================================================
# MQTT CALLBACKS
# ============================================================================
def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connected to broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_GESTURES)
        client.subscribe(TOPIC_PI2_COMMANDS)
        print(f"[MQTT] Subscribed to topics")
    else:
        print(f"[MQTT] Connection failed with code {rc}")

def on_mqtt_message(client, userdata, msg):
    global tracking_enabled, auto_volume_enabled, manual_volume_override, current_pan, current_tilt
    try:
        payload = json.loads(msg.payload.decode())
        
        if msg.topic in (TOPIC_GESTURES):
            gesture_type = payload.get("type", "")
            if not gesture_type:
                return
            print(f"[GESTURE] Received: {gesture_type}")
            if gesture_type in ["SWIPE_UP", "VOL_UP"]:
                adjust_volume(GESTURE_VOLUME_STEP)
                print(f"[GESTURE] Action: volume +{GESTURE_VOLUME_STEP}")
            elif gesture_type in ["SWIPE_DOWN", "VOL_DOWN"]:
                adjust_volume(-GESTURE_VOLUME_STEP)
                print(f"[GESTURE] Action: volume -{GESTURE_VOLUME_STEP}")
            elif gesture_type == "NEXT_TRACK":
                if playback_next():
                    print("[GESTURE] Action: next track/seek forward")
                else:
                    print("[GESTURE] Action failed: next track/seek forward")
            elif gesture_type == "PREV_TRACK":
                if playback_previous():
                    print("[GESTURE] Action: previous track/seek backward")
                else:
                    print("[GESTURE] Action failed: previous track/seek backward")
            elif gesture_type == "PAUSE":
                if playback_pause():
                    print("[GESTURE] Action: pause")
                else:
                    print("[GESTURE] Action failed: pause")
            elif gesture_type == "PLAY":
                if playback_play():
                    print("[GESTURE] Action: play")
                else:
                    print("[GESTURE] Action failed: play")
                
        elif msg.topic == TOPIC_PI2_COMMANDS:
            command = payload.get("command", "")
            print(f"[COMMAND] Received: {command} with payload: {payload}")
            
            if command == "set_volume":
                level = payload.get("level", 50)
                print(f"[VOLUME] Setting volume to {level}%")
                manual_volume_override = level
                set_volume(level)
            elif command == "tracking_enable":
                tracking_enabled = payload.get("enabled", True)
            elif command == "auto_volume_enable":
                auto_volume_enabled = payload.get("enabled", True)
                if auto_volume_enabled:
                    manual_volume_override = None
            elif command == "pan":
                angle = payload.get("angle", 0)
                current_pan = max(-90, min(90, angle))
                pantilthat.pan(current_pan)
            elif command == "tilt":
                angle = payload.get("angle", 0)
                current_tilt = max(-90, min(90, angle))
                pantilthat.tilt(apply_tilt(current_tilt))
            elif command == "center":
                current_pan = home_pan
                current_tilt = home_tilt
                pantilthat.pan(home_pan)
                pantilthat.tilt(apply_tilt(home_tilt))
            elif command == "recalibrate":
                recalibrate_requested = True
                print("[COMMAND] Recalibration requested")
            elif command == "status":
                publish_status()
                
    except Exception as e:
        print(f"[MQTT] Error: {e}")

def on_mqtt_disconnect(client, userdata, rc):
    print(f"[MQTT] Disconnected (rc={rc})")

def publish_status():
    global mqtt_client
    if mqtt_client and mqtt_client.is_connected():
        payload = {
            "volume": current_volume,
            "distance_ft": round(current_distance, 1),
            "is_tracking": is_tracking,
            "tracking_enabled": tracking_enabled,
            "auto_volume_enabled": auto_volume_enabled,
            "manual_override": manual_volume_override is not None,
            "pan_angle": round(current_pan, 1),
            "tilt_angle": round(current_tilt, 1),
            "mood": current_mood,
            "timestamp": time.time()
        }
        mqtt_client.publish(TOPIC_PI2_STATUS, json.dumps(payload))

def publish_mood(mood, playlist_name, playlist_url):
    global mqtt_client
    if mqtt_client and mqtt_client.is_connected():
        payload = {
            "mood": mood,
            "playlist_name": playlist_name,
            "playlist_url": playlist_url,
            "timestamp": time.time()
        }
        mqtt_client.publish(TOPIC_MOOD, json.dumps(payload))
        print(f"[MQTT] Published mood: {mood} -> {playlist_name}")

def adjust_volume(delta):
    global manual_volume_override, current_volume
    new_vol = max(0, min(100, current_volume + delta))
    manual_volume_override = new_vol
    set_volume(new_vol)
    
    def clear_override():
        global manual_volume_override
        time.sleep(10)
        if manual_volume_override == new_vol:
            manual_volume_override = None
    threading.Thread(target=clear_override, daemon=True).start()


def _run_playerctl(args):
    if shutil.which("playerctl") is None:
        print("[MEDIA] playerctl not found; cannot control playback")
        return False
    result = subprocess.run(
        ["playerctl"] + args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def _run_bluetoothctl_player(command):
    if shutil.which("bluetoothctl") is None:
        print("[MEDIA] bluetoothctl not found; cannot control Bluetooth playback")
        return False

    def _try_family(subcmd):
        try:
            list_result = subprocess.run(
                ["bluetoothctl", subcmd, "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if list_result.returncode != 0:
                return False
            match = re.search(r"Player\s+(\S+)", list_result.stdout)
            if not match:
                return False
            player_path = match.group(1)
            select_result = subprocess.run(
                ["bluetoothctl", subcmd, "select", player_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if select_result.returncode != 0:
                return False
            result = subprocess.run(
                ["bluetoothctl", subcmd, command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return result.returncode == 0
        except Exception:
            return False

    # BlueZ has used both "player" and "media-player" in different releases.
    if _try_family("player"):
        return True
    if _try_family("media-player"):
        return True

    print("[MEDIA] bluetoothctl control failed (no AVRCP player?)")
    return False


def media_next():
    if _run_playerctl(["next"]):
        return True
    if _run_bluetoothctl_player("next"):
        return True
    return _run_playerctl(["position", f"{MEDIA_SEEK_SECONDS}+"])


def media_previous():
    if _run_playerctl(["previous"]):
        return True
    if _run_bluetoothctl_player("previous"):
        return True
    return _run_playerctl(["position", f"{MEDIA_SEEK_SECONDS}-"])


def media_pause():
    if _run_playerctl(["pause"]):
        return True
    if _run_bluetoothctl_player("pause"):
        return True
    return _run_playerctl(["play-pause"])


def media_play():
    if _run_playerctl(["play"]):
        return True
    if _run_bluetoothctl_player("play"):
        return True
    return _run_playerctl(["play-pause"])


def playback_play():
    if spotify.play():
        return True
    return media_play()


def playback_pause():
    if spotify.pause():
        return True
    return media_pause()


def playback_next():
    if spotify.next_track():
        return True
    return media_next()


def playback_previous():
    if spotify.previous_track():
        return True
    return media_previous()

def setup_mqtt():
    global mqtt_client
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


def set_volume(percent):
    global current_volume
    percent = max(0, min(100, percent))
    current_volume = int(percent)
    
    # Apply exponential curve for better perceived volume scaling
    # This makes 50% on slider = ~71% actual volume (comfortable listening)
    # Formula: actual = (slider/100)^2 * 100
    # Result: 0→0%, 25→6%, 50→25%, 75→56%, 100→100%
    actual_percent = (percent / 100.0) ** 1.5 * 100
    actual_percent = int(max(0, min(100, actual_percent)))
    
    try:
        # Get all available BlueALSA controls dynamically
        result = subprocess.run(
            ["amixer", "-D", "bluealsa", "scontrols"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout:
            # Parse output like: Simple mixer control 'F8:7D:76:AA:A8:8C - A2DP',0
            import re
            controls = re.findall(r"Simple mixer control '([^']+)'", result.stdout)
            
            # Set volume on ALL connected Bluetooth devices
            for control in controls:
                subprocess.run(
                    ["amixer", "-D", "bluealsa", "sset", control, f"{actual_percent}%"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        else:
            # Fallback to configured device if scontrols fails
            device_name = f"{BLUETOOTH_SPEAKER_MAC} - {BLUETOOTH_SPEAKER_NAME}"
            subprocess.run(
                ["amixer", "-D", "bluealsa", "sset", device_name, f"{actual_percent}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except Exception as e:
        print("Volume set error:", e)

    # Keep Spotify app volume aligned with physical output volume.
    try:
        threading.Thread(target=spotify.set_volume, args=(int(percent),), daemon=True).start()
    except Exception:
        pass


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


def map_deepface_emotion(emotion):
    if emotion == "happy":
        return "happy"
    if emotion == "surprise":
        return "happy"
    if emotion in ("sad", "angry", "fear", "disgust"):
        return "sad"
    if emotion == "neutral":
        return "calm"
    return "calm"


def analyze_mood_heuristic(frame, face_bbox, eye_cascade, smile_cascade):
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
    
    mood_scores = {"happy": 0, "sad": 0, "calm": 0, "neutral": 1}

    # Smile is the strongest happy signal in your calibration set
    if has_smile:
        mood_scores["happy"] += 6
        mood_scores["calm"] += 0.5
    else:
        mood_scores["sad"] += 1
        mood_scores["calm"] += 1
        mood_scores["neutral"] += 1

    # Brightness bands tuned to your calibration stats
    # Chill mean ~101, Sad mean ~92
    if brightness < 90:
        mood_scores["sad"] += 2
    elif brightness < 98:
        mood_scores["sad"] += 1
        mood_scores["neutral"] += 1
    elif brightness < 115:
        mood_scores["calm"] += 2
    else:
        mood_scores["happy"] += 1

    # Contrast: chill lower (~42), sad higher (~48)
    if contrast > 47:
        mood_scores["sad"] += 2
    elif contrast > 44:
        mood_scores["sad"] += 1
        mood_scores["neutral"] += 1
    elif contrast < 40:
        mood_scores["calm"] += 2
    else:
        mood_scores["calm"] += 1

    # Eyes: sad tends to have fewer detected eyes
    if eyes_detected == 0:
        mood_scores["sad"] += 1
    elif eyes_detected == 1:
        mood_scores["neutral"] += 1
    else:
        mood_scores["calm"] += 1

    # Warmth: sad lower (~22), chill/happy higher (~24-26)
    if warmth < 22.5:
        mood_scores["sad"] += 2
    elif warmth < 24.0:
        mood_scores["sad"] += 1
        mood_scores["neutral"] += 1
    else:
        mood_scores["calm"] += 1
    
    dominant_mood = max(mood_scores, key=mood_scores.get)
    total = sum(mood_scores.values())
    confidence = mood_scores[dominant_mood] / total * 100 if total > 0 else 0
    
    return dominant_mood, confidence


def analyze_mood(frame, face_bbox, eye_cascade, smile_cascade):
    global deepface_enabled
    if deepface_enabled and DEEPFACE_AVAILABLE:
        x, y, w, h = [int(v) for v in face_bbox]
        x = max(0, x)
        y = max(0, y)
        w = min(frame.shape[1] - x, w)
        h = min(frame.shape[0] - y, h)
        face_color = frame[y:y + h, x:x + w]
        try:
            start = time.time()
            result = DeepFace.analyze(
                face_color,
                actions=["emotion"],
                enforce_detection=False
            )
            if isinstance(result, list) and result:
                result = result[0]
            emotion = result.get("dominant_emotion") if isinstance(result, dict) else None
            if emotion:
                mood = map_deepface_emotion(emotion)
                duration = time.time() - start
                if duration > DEEPFACE_MAX_SECONDS:
                    deepface_enabled = False
                    print(f"[MOOD] DeepFace slow ({duration:.2f}s); falling back to heuristic")
                return mood, 100
        except Exception as e:
            print(f"[MOOD] DeepFace error, using heuristic: {e}")
    return analyze_mood_heuristic(frame, face_bbox, eye_cascade, smile_cascade)


def get_current_pan_tilt():
    """Best-effort read of current pan/tilt to avoid snapping on start."""
    try:
        return float(pantilthat.get_pan()), float(pantilthat.get_tilt())
    except Exception:
        return 0.0, 0.0


def normalize_tilt(physical_tilt):
    return -physical_tilt if TILT_INVERT else physical_tilt


def apply_tilt(tilt_angle):
    return -tilt_angle if TILT_INVERT else tilt_angle


def capture_home_position(sample_count=5, delay_s=0.05):
    pans = []
    tilts = []
    for _ in range(sample_count):
        pan, tilt = get_current_pan_tilt()
        pans.append(pan)
        tilts.append(tilt)
        time.sleep(delay_s)
    avg_pan = sum(pans) / len(pans)
    avg_tilt = sum(tilts) / len(tilts)
    return avg_pan, normalize_tilt(avg_tilt)


def recommend_playlist(mood):
    playlists = PLAYLISTS.get(mood, PLAYLISTS["neutral"])
    return random.choice(playlists)


def check_mood_and_recommend(frame, face_bbox, eye_cascade, smile_cascade):
    print("\n" + "=" * 50)
    print("MOOD CHECK")
    print("=" * 50)
    
    mood, confidence = analyze_mood(frame, face_bbox, eye_cascade, smile_cascade)
    if confidence < 45 and mood != "happy":
        mood = "calm"
    print(f"Detected mood: {mood.upper()} ({confidence:.0f}% confidence)")
    
    playlist_name, playlist_url = recommend_playlist(mood)
    print(f"\nRECOMMENDATION: {playlist_name}")
    print(f"{playlist_url}")
    print("=" * 50 + "\n")
    
    # Publish mood and playlist to dashboard
    publish_mood(mood, playlist_name, playlist_url)
    
    return mood


def lock_onto_person(cap, face_cascade, profile_cascade, upper_body_cascade):
    print("Looking for a person to lock onto...")
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        bbox = detect_person(frame, face_cascade, profile_cascade, upper_body_cascade)
        if bbox is not None:
            x, y, w, h = bbox
            print(f"Locked on at ({x}, {y}) size {w}x{h}")
            tracker = create_tracker()
            if tracker is None:
                print("Failed to create tracker, will use detection-only mode")
                return None, bbox, w * h
            try:
                success = tracker.init(frame, (x, y, w, h))
                if not success:
                    print("Tracker init returned False")
                    return None, bbox, w * h
            except Exception as e:
                print(f"Tracker init error: {e}")
                return None, bbox, w * h
            ref_area = w * h
            print(f"Reference area: {ref_area}")
            print("Tracking started!")
            return tracker, bbox, ref_area
        time.sleep(0.1)


def release_camera():
    """Kill any processes using the camera before we start."""
    import os as _os
    my_pid = str(_os.getpid())
    try:
        # Force release /dev/video0 (but not our own process)
        result = subprocess.run(
            ["sudo", "fuser", "/dev/video0"],
            capture_output=True,
            text=True
        )
        if result.stdout:
            pids = result.stdout.strip().split()
            for pid in pids:
                if pid != my_pid:
                    subprocess.run(["sudo", "kill", "-9", pid], 
                                   stdout=subprocess.DEVNULL, 
                                   stderr=subprocess.DEVNULL)
        time.sleep(0.5)
    except Exception as e:
        print(f"[CAMERA] Cleanup warning: {e}")


def main():
    global LAST_MOOD_CHECK, is_tracking, current_distance, current_pan, current_mood, manual_volume_override, auto_volume_enabled, ref_area, recalibrate_requested
    
    # Warm up Spotify token/session once at startup.
    spotify.warmup()
    
    # Make Pi 2 discoverable for Bluetooth pairing
    print("[BLUETOOTH] Enabling discoverable mode for device pairing...")
    try:
        subprocess.run(
            ["sudo", "bluetoothctl", "discoverable", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        subprocess.run(
            ["sudo", "bluetoothctl", "pairable", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        print("[BLUETOOTH] Pi 2 is now discoverable for new device pairing")
    except Exception as e:
        print(f"[BLUETOOTH] Could not enable discoverable mode: {e}")
    
    # Release camera from any other processes first
    print("[CAMERA] Releasing camera from other processes...")
    release_camera()
    
    # Open camera FIRST before anything else
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("Could not open camera - trying again after reset...")
        # Try once more after a brief wait
        time.sleep(1)
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            print("Could not open camera")
            return
    
    print("[CAMERA] Opened successfully")
    
    # Now setup MQTT after camera is working
    setup_mqtt()

    face_cascade = cv2.CascadeClassifier(FACE_CASCADE)
    profile_cascade = cv2.CascadeClassifier(PROFILE_CASCADE)
    upper_body_cascade = cv2.CascadeClassifier(UPPER_BODY_CASCADE)
    eye_cascade = cv2.CascadeClassifier(EYE_CASCADE)
    smile_cascade = cv2.CascadeClassifier(SMILE_CASCADE)

    tracker, bbox, ref_area = lock_onto_person(cap, face_cascade, profile_cascade, upper_body_cascade)
    print(f"[CALIBRATION] Initial reference area: {ref_area} (at {REF_DISTANCE_FEET} ft)")

    use_tracker = tracker is not None
    if not use_tracker:
        print("Falling back to detection-only mode (slower)")

    pan, tilt = capture_home_position()
    current_pan = pan
    current_tilt = tilt
    home_pan = pan
    home_tilt = tilt
    error_filtered = 0.0
    prev_error = 0.0
    vol_current = VOL_FAR
    set_volume(vol_current)

    distance_ft = REF_DISTANCE_FEET

    lost_frames = 0
    MAX_LOST_FRAMES = 45
    detect_interval = 3
    frame_count = 0
    
    LAST_MOOD_CHECK = time.time()
    current_mood = "neutral"

    print(f"\nMood detection enabled - checking every {MOOD_CHECK_INTERVAL} seconds")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            h, w = frame.shape[:2]
            center_x = w / 2.0

            success = False

            if use_tracker:
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

                # Handle recalibration request
                if recalibrate_requested:
                    ref_area = area
                    current_distance = REF_DISTANCE_FEET
                    distance_ft = REF_DISTANCE_FEET
                    recalibrate_requested = False
                    print(f"[CALIBRATION] Recalibrated! New reference area: {ref_area}")
                    publish_status()

                now = time.time()
                if now - LAST_MOOD_CHECK >= MOOD_CHECK_INTERVAL:
                    faces = face_cascade.detectMultiScale(
                        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                        scaleFactor=1.2,
                        minNeighbors=5,
                        minSize=(50, 50)
                    )
                    if len(faces) > 0:
                        face_bbox = max(faces, key=lambda f: f[2] * f[3])
                        current_mood = check_mood_and_recommend(frame, face_bbox, eye_cascade, smile_cascade)
                    else:
                        print("\nMood check skipped - no clear face detected")
                    LAST_MOOD_CHECK = now

                raw_error = center_x - cx
                error_filtered = (1 - error_smooth) * error_filtered + error_smooth * raw_error
                
                error_deriv = error_filtered - prev_error
                prev_error = error_filtered

                if abs(error_filtered) > dead_zone:
                    delta = (error_filtered * Kp_pan) + (error_deriv * Kd_pan)
                    delta = max(-max_step, min(max_step, delta))
                    if PAN_INVERT:
                        delta = -delta
                    pan += delta
                    pan = max(-90.0, min(90.0, pan))
                    pantilthat.pan(pan)
                    current_pan = pan

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

                if distance_ft <= BOUND_NEAR_MID:
                    zone_vol = VOL_NEAR
                elif distance_ft <= BOUND_MID_FAR:
                    zone_vol = VOL_MID
                else:
                    zone_vol = VOL_FAR

                if auto_volume_enabled and manual_volume_override is None:
                    vol_current = (1.0 - VOLUME_SMOOTH_ALPHA) * vol_current + VOLUME_SMOOTH_ALPHA * zone_vol
                    set_volume(vol_current)

                #print(f"pan={pan:.1f} dist={distance_ft:.1f}ft vol={vol_current:.0f}% mood={current_mood}")
                
                # Publish status to dashboard
                if frame_count % 30 == 0:
                    publish_status()
            else:
                lost_frames += 1
                error_filtered *= 0.9
                prev_error *= 0.9
                is_tracking = False

                if lost_frames % 10 == 0:
                    print(f"Tracking lost ({lost_frames}/{MAX_LOST_FRAMES})")

                if lost_frames > MAX_LOST_FRAMES:
                    print("Re-acquiring target...")
                    tracker, bbox, ref_area = lock_onto_person(cap, face_cascade, profile_cascade, upper_body_cascade)
                    use_tracker = tracker is not None
                    lost_frames = 0
                    error_filtered = 0.0
                    prev_error = 0.0

    except KeyboardInterrupt:
        pass

    cap.release()
    if RESET_PAN_ON_EXIT:
        pantilthat.pan(0.0)
    if mqtt_client:
        publish_status()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    print("Stopped.")


if __name__ == "__main__":
    main()