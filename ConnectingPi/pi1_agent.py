#!/usr/bin/env python3
"""
Pi 1 Agent - MQTT-enabled controller for:
  - Bluetooth IMU gesture detection (built-in below, based on your original IMU script)
  - LED feedback (NeoPixel)
  - Voice commands (voice_commands.py)

Publishes to:
  - home/gestures        : Gesture and voice command events
  - home/pi1/status      : Pi 1 status updates

Subscribes to:
  - home/pi1/commands    : LED control commands from dashboard

Run tips:
- For NeoPixels:   sudo -E python3 pi1_agent.py
- Enable voice:    ENABLE_VOICE=1 sudo -E python3 pi1_agent.py
"""

import asyncio
import json
import os
import socket
import struct
import threading
import time
import math
import queue  
import traceback
from collections import deque
import asyncio
import paho.mqtt.client as mqtt

# Voice mapping (your existing module)
import voice_commands as vc

# BLE client
try:
    from bleak import BleakClient
    BLEAK_AVAILABLE = True
except Exception:
    BLEAK_AVAILABLE = False


# ============================================================================
# CONFIGURATION - EDIT config.py OR SET ENVIRONMENT VARIABLES
# ============================================================================
# To configure for a new computer, either:
#   1. Edit config.py (recommended)
#   2. Set environment variables:
#      export MQTT_BROKER="your-computer.local"
#      export IMU_MAC="XX:XX:XX:XX:XX:XX"
# ============================================================================
try:
    from config import (
        MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE,
        IMU_MAC_ADDRESS, CHAR_NOTIFY_PRIMARY, CHAR_NOTIFY_FALLBACK
    )
except ImportError:
    # Fallback if config.py doesn't exist
    MQTT_BROKER = os.environ.get("MQTT_BROKER", "Leahs-MacBook-Pro.local")  # <-- CHANGE THIS
    MQTT_PORT = 1883
    MQTT_KEEPALIVE = 60
    IMU_MAC_ADDRESS = os.environ.get("IMU_MAC", "D9:41:48:15:5E:FB")  # <-- CHANGE THIS
    CHAR_NOTIFY_PRIMARY = "0000ffe4-0000-1000-8000-00805f9a34fb"
    CHAR_NOTIFY_FALLBACK = "0000ffe9-0000-1000-8000-00805f9a34fb"

TOPIC_GESTURES = "home/gestures"
TOPIC_PI1_STATUS = "home/pi1/status"
TOPIC_PI1_COMMANDS = "home/pi1/commands"

VOICE_ENABLED_AT_START = 0


# ============================================================================
# GLOBAL STATE
# ============================================================================
mqtt_client = None
led_enabled = False
gesture_enabled = True
voice_enabled = False

voice_cmd_queue = None
gesture_cmd_queue = None



# ============================================================================
# LED FEEDBACK MODULE (best-effort; won't crash if not sudo)
# ============================================================================
LED_AVAILABLE = False
pixels = None

try:
    import board
    import neopixel

    LED_PIN = board.D21
    NUM_LEDS = 60
    BRIGHTNESS = 0.5

    pixels = neopixel.NeoPixel(
        LED_PIN,
        NUM_LEDS,
        brightness=BRIGHTNESS,
        auto_write=True,
        pixel_order=neopixel.GRB
    )
    LED_AVAILABLE = True
except Exception:
    LED_AVAILABLE = False
    pixels = None


def _safe_pixels_fill(color):
    """Never let LED writes crash the agent."""
    if not LED_AVAILABLE or pixels is None:
        return
    try:
        pixels.fill(color)
    except Exception:
        # Usually: /dev/mem permission error if not run with sudo
        pass


def led_flash(color=(0, 255, 0), duration=0.2):
    """Flash LEDs with specified color."""
    if not LED_AVAILABLE or not led_enabled:
        return
    _safe_pixels_fill(color)
    time.sleep(duration)
    _safe_pixels_fill((0, 0, 0))


def led_set_color(color):
    """Set LEDs to a solid color."""
    if not LED_AVAILABLE or not led_enabled:
        return
    _safe_pixels_fill(color)


def led_off():
    """Turn off all LEDs."""
    if not LED_AVAILABLE:
        return
    _safe_pixels_fill((0, 0, 0))


def led_volume_bar(level):
    """Display volume level as LED bar (0-100)."""
    if not LED_AVAILABLE or not led_enabled:
        return
    try:
        num_lit = int((level / 100.0) * NUM_LEDS)
        for i in range(NUM_LEDS):
            if i < num_lit:
                green = int(255 * (1 - i / NUM_LEDS))
                red = int(255 * (i / NUM_LEDS))
                pixels[i] = (red, green, 0)
            else:
                pixels[i] = (0, 0, 0)
    except Exception:
        pass


# ============================================================================
# MQTT CALLBACKS (paho-mqtt Callback API v2)
# ============================================================================
def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[MQTT] Connected to broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_PI1_COMMANDS)
        print(f"[MQTT] Subscribed to {TOPIC_PI1_COMMANDS}")
        publish_status("online")
    else:
        print(f"[MQTT] Connection failed (reason_code={reason_code})")


def on_mqtt_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    print(f"[MQTT] Disconnected (reason_code={reason_code})")


def on_mqtt_message(client, userdata, msg):
    """Handle incoming commands from dashboard."""
    global led_enabled, gesture_enabled, voice_enabled

    try:
        payload = json.loads(msg.payload.decode())
        command = payload.get("command", "")
        print(f"[MQTT] Received command: {command}")

        if command == "led_flash":
            color = tuple(payload.get("color", [0, 255, 0]))
            duration = payload.get("duration", 0.3)
            led_flash(color, duration)

        elif command == "led_set":
            color = tuple(payload.get("color", [0, 0, 0]))
            led_set_color(color)

        elif command == "led_off":
            led_off()

        elif command == "led_volume":
            level = payload.get("level", 50)
            led_volume_bar(level)

        elif command == "led_enable":
            led_enabled = payload.get("enabled", True)
            print(f"[LED] Enabled: {led_enabled}")

        elif command == "gesture_enable":
            gesture_enabled = payload.get("enabled", True)
            print(f"[IMU] Enabled: {gesture_enabled}")

        elif command == "voice_enable":
            voice_enabled = payload.get("enabled", True)
            print(f"[VOICE] Enabled: {voice_enabled}")

        elif command == "status":
            publish_status("online")

    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")


def publish_gesture(gesture_type, source="gesture"):
    """Publish gesture/voice command to MQTT."""
    if mqtt_client and mqtt_client.is_connected():
        payload = {
            "type": gesture_type,
            "source": source,   # "gesture" or "voice"
            "timestamp": time.time(),
            "device": "pi1",
        }
        mqtt_client.publish(TOPIC_GESTURES, json.dumps(payload))
        print(f"[MQTT] Published: {gesture_type} ({source})")

    # LED feedback
    if source == "gesture":
        led_flash((0, 255, 0), 0.12)  # green
    else:
        led_flash((0, 0, 255), 0.12)  # blue


def publish_status(status):
    """Publish Pi 1 status."""
    if mqtt_client and mqtt_client.is_connected():
        payload = {
            "status": status,
            "led_enabled": led_enabled,
            "gesture_enabled": gesture_enabled,
            "voice_enabled": voice_enabled,
            "timestamp": time.time(),
        }
        mqtt_client.publish(TOPIC_PI1_STATUS, json.dumps(payload))


# ============================================================================
# COMMAND DISPATCHER (voice first, then gestures)
# ============================================================================
async def dispatch_commands():
    print("[DISPATCH] dispatcher started")
    while True:
        try:
            try:
                voice_cmd = voice_cmd_queue.get_nowait()
                print(f"[DISPATCH] got voice cmd: {voice_cmd}")
                publish_gesture(voice_cmd, "voice")
                await asyncio.sleep(0)
                continue
            except asyncio.QueueEmpty:
                pass

            try:
                gesture_cmd = await asyncio.wait_for(gesture_cmd_queue.get(), timeout=0.25)
                print(f"[DISPATCH] got gesture cmd: {gesture_cmd}")
                publish_gesture(gesture_cmd, "gesture")
            except asyncio.TimeoutError:
                await asyncio.sleep(0.05)

        except Exception as e:
            print("[DISPATCH] CRASHED:", e)
            traceback.print_exc()
            await asyncio.sleep(1.0)  # keep it alive so we can see repeated failures

# ============================================================================
# IMU GESTURE DETECTION (based on your original IMU code)
# ============================================================================
# IMU settings loaded from config.py
IMU_MAC = IMU_MAC_ADDRESS

MODE_IDLE = "IDLE"
MODE_COMMAND = "COMMAND"

# ---------- Wake / Cancel: DOUBLE FLICK ----------
FLICK_GMAG_THR_DPS = 750.0
FLICK_REFRACTORY_S = 0.20
FLICK_PEAK_WINDOW_S = 0.25

DOUBLE_FLICK_REQUIRED = 2
DOUBLE_FLICK_MAX_SPAN_S = 0.85

# ---------- Command timing ----------
COMMAND_TIMEOUT_S = 5.0
COMMAND_READY_DELAY_S = 1.25
REARM_READY_DELAY_S = 0.8
POST_COMMAND_COOLDOWN_S = 0.40
REARM_IDLE_S = 0.25

# ---------- History ----------
GESTURE_WINDOW_S = 0.60
HIST_KEEP_S = 2.0

# ---------- Twist detection ----------
TWIST_GY_THR_DPS = 180.0
TWIST_RIGHT_IS_POSITIVE_GY = False

# ---------- Swipe detection ----------
SWIPE_DAZ_THR_G = 0.55
SWIPE_TWIST_REJECT_GY_DPS = 260.0
SWIPE_UP_IS_POSITIVE_DAZ = True

DEBUG_COMMAND = False


# ---------------- BLE packet parsing ----------------
def parse_wt901_packets(buf: bytearray):
    out = []
    i = 0
    while i + 20 <= len(buf):
        if buf[i] != 0x55:
            i += 1
            continue
        out.append(bytes(buf[i:i + 20]))
        i += 20
    del buf[:i]
    return out


def decode_frame(frame: bytes):
    if len(frame) != 20 or frame[0] != 0x55:
        return None
    if frame[1] == 0x61:
        ax, ay, az, gx, gy, gz, roll, pitch, yaw = struct.unpack_from("<9h", frame, 2)
        accel_g = (ax / 32768.0 * 16.0, ay / 32768.0 * 16.0, az / 32768.0 * 16.0)
        gyro_dps = (gx / 32768.0 * 2000.0, gy / 32768.0 * 2000.0, gz / 32768.0 * 2000.0)
        angle_deg = (roll / 32768.0 * 180.0, pitch / 32768.0 * 180.0, yaw / 32768.0 * 180.0)
        return accel_g, gyro_dps, angle_deg
    return None


def mag3(x, y, z):
    return math.sqrt(x * x + y * y + z * z)


# ---------------- Gesture Engine ----------------
class GestureEngine:
    """
    State machine:
      - IDLE: waits for DOUBLE FLICK to arm
      - COMMAND: after delay, accepts ONE gesture (twist/swipe), then returns to IDLE
      - Re-arm: short idle and automatically re-enters COMMAND mode
    """
    def __init__(self):
        self.mode = MODE_IDLE

        # history: (t, ax, ay, az, gx, gy, gz)
        self.hist = deque()

        # flick bookkeeping
        self.flick_times = deque()
        self.last_flick_t = 0.0

        # command bookkeeping
        self.cmd_start_t = 0.0
        self.last_cmd_t = 0.0
        self.ready_announced = False
        self.entered_via_rearm = False

        # command-mode baseline for az deltas
        self.az0 = None
        self.az0_accum = 0.0
        self.az0_n = 0
        self.az0_target_n = 6

        # re-arm support
        self.pending_rearm = False
        self.rearm_at_t = 0.0

    def clear_history(self):
        self.hist.clear()

    def _reset_command_baselines(self):
        self.az0 = None
        self.az0_accum = 0.0
        self.az0_n = 0
        self.ready_announced = False

    def _enter_command_mode(self, via_rearm: bool = False):
        self.mode = MODE_COMMAND
        self.cmd_start_t = time.time()
        self.entered_via_rearm = via_rearm
        self.clear_history()
        self._reset_command_baselines()

    def push(self, ax, ay, az, gx, gy, gz):
        now = time.time()
        self.hist.append((now, ax, ay, az, gx, gy, gz))
        while self.hist and (now - self.hist[0][0]) > HIST_KEEP_S:
            self.hist.popleft()

    def _window(self, window_s):
        now = time.time()
        return [s for s in self.hist if (now - s[0]) <= window_s]

    def _peak_value(self, window_s, val_fn):
        w = self._window(window_s)
        if not w:
            return None
        return max(val_fn(s) for s in w)

    def _peak_sample(self, window_s, key_fn):
        w = self._window(window_s)
        if not w:
            return None
        return max(w, key=key_fn)

    # ---- flick event ----
    def _detect_flick_event(self):
        now = time.time()
        if now - self.last_flick_t < FLICK_REFRACTORY_S:
            return False

        gmag_peak = self._peak_value(
            FLICK_PEAK_WINDOW_S,
            lambda s: mag3(s[4], s[5], s[6])
        )
        if gmag_peak is not None and gmag_peak >= FLICK_GMAG_THR_DPS:
            self.last_flick_t = now
            return True
        return False

    # ---- double flick detection ----
    def _detect_double_flick(self):
        now = time.time()
        if not self._detect_flick_event():
            return False

        self.flick_times.append(now)

        # keep only within span
        while self.flick_times and (now - self.flick_times[0]) > DOUBLE_FLICK_MAX_SPAN_S:
            self.flick_times.popleft()

        if len(self.flick_times) >= DOUBLE_FLICK_REQUIRED:
            self.flick_times.clear()
            return True
        return False

    # ---- gestures ----
    def _detect_twist(self):
        s = self._peak_sample(GESTURE_WINDOW_S, key_fn=lambda x: abs(x[5]))  # gy
        if not s:
            return None
        gy = s[5]
        if abs(gy) >= TWIST_GY_THR_DPS:
            if TWIST_RIGHT_IS_POSITIVE_GY:
                return "NEXT_TRACK" if gy > 0 else "PREV_TRACK"
            else:
                return "NEXT_TRACK" if gy < 0 else "PREV_TRACK"
        return None

    def _update_command_baseline(self):
        if self.az0 is not None:
            return True
        if not self.hist:
            return False
        az = self.hist[-1][3]
        self.az0_accum += az
        self.az0_n += 1
        if self.az0_n >= self.az0_target_n:
            self.az0 = self.az0_accum / self.az0_n
            return True
        return False

    def _detect_swipe_by_daz(self):
        if self.az0 is None:
            return None

        # reject swipe if twist is too strong
        gy_peak = self._peak_value(GESTURE_WINDOW_S, lambda s: abs(s[5]))
        if gy_peak is not None and gy_peak > SWIPE_TWIST_REJECT_GY_DPS:
            return None

        w = self._window(GESTURE_WINDOW_S)
        if not w:
            return None

        daz_vals = [(s[3] - self.az0) for s in w]
        daz_peak = max(daz_vals)
        daz_trough = min(daz_vals)
        daz_best = daz_peak if abs(daz_peak) >= abs(daz_trough) else daz_trough

        if DEBUG_COMMAND:
            print(f"[dbg] az0={self.az0:+.3f} daz_best={daz_best:+.3f} | gy_peak={gy_peak if gy_peak is not None else -1:+.1f}")

        if abs(daz_best) >= SWIPE_DAZ_THR_G:
            if SWIPE_UP_IS_POSITIVE_DAZ:
                return "PAUSE" if daz_best > 0 else "PLAY"
            else:
                return "PAUSE" if daz_best < 0 else "PLAY"
        return None

    async def step(self):
        now = time.time()

        # Handle pending re-arm
        if self.pending_rearm and now >= self.rearm_at_t:
            self.pending_rearm = False
            self._enter_command_mode(via_rearm=True)
            return "REENTER_COMMAND_MODE"

        # -------- IDLE --------
        if self.mode == MODE_IDLE:
            if self._detect_double_flick():
                self._enter_command_mode(via_rearm=False)
                return "ENTER_COMMAND_MODE"
            return None

        # -------- COMMAND --------
        # double flick cancels back to idle
        if self._detect_double_flick():
            self.mode = MODE_IDLE
            self.clear_history()
            return "CANCEL_TO_IDLE"

        elapsed = now - self.cmd_start_t
        ready_delay = REARM_READY_DELAY_S if self.entered_via_rearm else COMMAND_READY_DELAY_S

        # ready delay
        if elapsed < ready_delay:
            return None

        if not self.ready_announced:
            self.ready_announced = True
            return "READY_FOR_GESTURE"

        # timeout
        if elapsed > COMMAND_TIMEOUT_S:
            self.mode = MODE_IDLE
            self.clear_history()
            return "COMMAND_TIMEOUT"

        if now - self.last_cmd_t < POST_COMMAND_COOLDOWN_S:
            return None

        if not self._update_command_baseline():
            return None

        # detect gesture
        g = self._detect_twist()
        if g:
            self.last_cmd_t = now
            self.mode = MODE_IDLE
            self.clear_history()
            self.pending_rearm = True
            self.rearm_at_t = now + REARM_IDLE_S
            return g

        g = self._detect_swipe_by_daz()
        if g:
            self.last_cmd_t = now
            self.mode = MODE_IDLE
            self.clear_history()
            self.pending_rearm = True
            self.rearm_at_t = now + REARM_IDLE_S
            return g

        return None


# ---------------- BLE runner ----------------
async def imu_run(client: "BleakClient", notify_uuid: str, label: str):
    """
    Reads WT901 packets from notify UUID, decodes accel/gyro,
    feeds the GestureEngine, and queues recognized gestures.
    """
    sample_queue: asyncio.Queue = asyncio.Queue(maxsize=800)
    buf = bytearray()
    engine = GestureEngine()

    def handler(_sender, data: bytearray):
        buf.extend(data)
        for frame in parse_wt901_packets(buf):
            decoded = decode_frame(frame)
            if decoded:
                try:
                    sample_queue.put_nowait(decoded)
                except asyncio.QueueFull:
                    pass

    print(f"\n[{label}] Subscribing to notifications on {notify_uuid} ...")
    await client.start_notify(notify_uuid, handler)
    await asyncio.sleep(1.0)

    print("\nIDLE: DOUBLE FLICK to arm command mode.")
    print("COMMAND: one of {NEXT_TRACK, PREV_TRACK, PAUSE, PLAY}.")
    print("COMMAND: DOUBLE FLICK again cancels.\n")

    try:
        while True:
            (accel_g, gyro_dps, _angle_deg) = await sample_queue.get()
            (ax, ay, az) = accel_g
            (gx, gy, gz) = gyro_dps

            engine.push(ax, ay, az, gx, gy, gz)
            evt = await engine.step()

            # If gestures disabled, keep engine running but skip publishes
            if evt and not gesture_enabled:
                continue

            if evt == "ENTER_COMMAND_MODE":
                print(f"\n>>> COMMAND MODE ARMED <<<")
                print(f"    Waiting {COMMAND_READY_DELAY_S:.2f}s... then do ONE gesture.")
            elif evt == "REENTER_COMMAND_MODE":
                print(f"\n>>> COMMAND MODE RE-ARMED <<<")
                print(f"    Waiting {REARM_READY_DELAY_S:.2f}s... then do ONE gesture.")
            elif evt == "READY_FOR_GESTURE":
                print("\n>>> READY: do your gesture now! <<<")
            elif evt == "CANCEL_TO_IDLE":
                print("\n>>> CANCELLED -> Back to IDLE mode <<<")
            elif evt == "COMMAND_TIMEOUT":
                print("\n>>> TIMEOUT -> Back to IDLE mode <<<")
            elif evt in ("NEXT_TRACK", "PREV_TRACK", "PAUSE", "PLAY"):
                print(f"\nGESTURE: {evt}")
                print(">>> Back to IDLE mode <<<")
                await gesture_cmd_queue.put(evt)

    finally:
        try:
            await client.stop_notify(notify_uuid)
        except Exception:
            pass


async def run_gesture_detection():
    """Connects to IMU and runs primary notify UUID, then fallback on error."""
    if not BLEAK_AVAILABLE:
        print("[IMU] Bleak not installed; gesture detection disabled")
        return

    print(f"[IMU] Connecting to {IMU_MAC}...")
    try:
        async with BleakClient(IMU_MAC) as client:
            print("[IMU] Connected.")

            try:
                await imu_run(client, CHAR_NOTIFY_PRIMARY, "PRIMARY")
            except Exception as e:
                print(f"[PRIMARY] Error: {e}")

            print("\nSwitching to fallback notify characteristic...\n")
            await imu_run(client, CHAR_NOTIFY_FALLBACK, "FALLBACK")

    except Exception as e:
        print(f"[IMU] Connection error: {e}")


# ============================================================================
# VOICE COMMAND DETECTION (runs in a thread)
# ============================================================================
def run_voice_detection(loop: asyncio.AbstractEventLoop):
    def get_input_devices():
        """Return list of (index, name, max_inputs) using PyAudio if possible."""
        try:
            import pyaudio

            pa = pyaudio.PyAudio()
            devices = []
            try:
                count = pa.get_device_count()
                for i in range(count):
                    info = pa.get_device_info_by_index(i)
                    devices.append((i, info.get("name", "?"), info.get("maxInputChannels", 0)))
            finally:
                pa.terminate()
            return devices
        except Exception:
            return None

    def list_microphones():
        """Print available input devices with indexes to help select DEVICE_INDEX."""
        print("[VOICE] Listing input devices...")
        devices = get_input_devices()
        if devices:
            for i, name, inputs in devices:
                print(f"  {i}: {name} inputs={inputs}")
            return

        # Fallback if PyAudio path fails
        try:
            import speech_recognition as sr

            names = sr.Microphone.list_microphone_names()
            for i, name in enumerate(names):
                print(f"  {i}: {name}")
        except Exception as e2:
            print(f"[VOICE] Could not list microphones: {e2}")

    try:
        import speech_recognition as sr
    except ImportError:
        print("[VOICE] SpeechRecognition not installed, voice detection disabled")
        return

    r = sr.Recognizer()

    # Choose a microphone: prefer first device with inputs>0; otherwise fallback
    mic_index = vc.DEVICE_INDEX
    devices_info = get_input_devices()
    chosen_name = None

    if devices_info:
        input_devices = [(i, name, ins) for (i, name, ins) in devices_info if ins and ins > 0]
        all_devices = devices_info
        list_microphones()

        def valid(idx):
            return 0 <= idx < len(all_devices) and all_devices[idx][2] and all_devices[idx][2] > 0

        if not valid(mic_index):
            if input_devices:
                mic_index = input_devices[0][0]
                print(f"[VOICE] Auto-selecting first input-capable device: {mic_index} -> {input_devices[0][1]}")
            else:
                print("[VOICE] No input-capable devices found")
                return
        chosen_name = all_devices[mic_index][1]
    else:
        # Fallback to SpeechRecognition list (names only)
        try:
            devices = sr.Microphone.list_microphone_names()
            if not devices:
                print("[VOICE] No microphones found")
                return
            list_microphones()
            if mic_index < 0 or mic_index >= len(devices):
                mic_index = 0
                print(f"[VOICE] Auto-selecting DEVICE_INDEX={mic_index} -> {devices[mic_index]}")
            chosen_name = devices[mic_index]
        except Exception as e:
            print(f"[VOICE] Could not validate microphone list: {e}")
            mic_index = vc.DEVICE_INDEX

    if chosen_name:
        print(f"[VOICE] Using DEVICE_INDEX={mic_index} -> {chosen_name}")

    try:
        with sr.Microphone(
            device_index=mic_index,
            sample_rate=vc.SAMPLE_RATE,
            chunk_size=vc.CHUNK,
        ) as source:
            print(f"[VOICE] Microphone opened (device={mic_index}, rate={vc.SAMPLE_RATE}, chunk={vc.CHUNK})")
            print("[VOICE] Calibrating for ambient noise...")
            try:
                r.adjust_for_ambient_noise(source, duration=1.0)
            except Exception as e:
                print(f"[VOICE] Calibration error: {e}")
                return
            print("[VOICE] Voice detection active; listening for commands")

            while True:
                if not voice_enabled:
                    time.sleep(0.1)
                    continue

                try:
                    print("[VOICE] Listening...")
                    audio = r.listen(source, phrase_time_limit=3.0)
                    try:
                        text = r.recognize_google(audio, language="en-US")
                        print(f"[VOICE] Heard: {text}")

                        cmd = vc.map_command(text)
                        if cmd:
                            print(f"[VOICE] Recognized command: {cmd}")
                            loop.call_soon_threadsafe(voice_cmd_queue.put_nowait, cmd)

                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError as e:
                        print(f"[VOICE] Google STT error: {e}")

                except Exception as e:
                    print(f"[VOICE] Listen error: {e}")
                    time.sleep(1.0)

    except Exception as e:
        print(f"[VOICE] Microphone error: {e}")
        print("[VOICE] Voice detection disabled")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
async def main():
    global mqtt_client

    print("=" * 60)
    print("Pi 1 Agent - Starting")
    print("=" * 60)

    # ---- MQTT setup ----
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pi1_agent")
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.on_disconnect = on_mqtt_disconnect

    mqtt_client.will_set(
        TOPIC_PI1_STATUS,
        json.dumps({"status": "offline", "timestamp": time.time(), "device": "pi1"}),
    )

    try:
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[MQTT] Failed to connect: {e}")
        print("[MQTT] Running in offline mode")

    loop = asyncio.get_running_loop()
    global voice_cmd_queue, gesture_cmd_queue
    voice_cmd_queue = asyncio.Queue()
    gesture_cmd_queue = asyncio.Queue()
    print("[DISPATCH] queues created on running loop")
    
    # ---- Voice thread (optional) ----
    if VOICE_ENABLED_AT_START:
        voice_thread = threading.Thread(target=run_voice_detection, args=(loop,), daemon=True)
        voice_thread.start()
    else:
        print("[VOICE] Skipping voice detection (ENABLE_VOICE=0)")

    # ---- Dispatcher (voice priority) ----
    dispatcher_task = asyncio.create_task(dispatch_commands())

    try:
        while True:
            await run_gesture_detection()
            print("[IMU] gesture task ended; retrying in 2s...")
            await asyncio.sleep(2.0)

    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down...")

    finally:
        dispatcher_task.cancel()
        try:
            publish_status("offline")
        except Exception:
            pass
        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        except Exception:
            pass
        led_off()
        print("[MAIN] Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping.")