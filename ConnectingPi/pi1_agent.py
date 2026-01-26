#!/usr/bin/env python3
"""
Pi 1 Agent - MQTT-enabled controller for:
  - Bluetooth IMU gesture detection (BLUETOOTH_GESTURE_READINGS.py)
  - LED feedback (led_feedback.py)
  - Voice commands (voice_commands.py)

Publishes to:
  - home/gestures        : Gesture and voice command events
  - home/pi1/status      : Pi 1 status updates

Subscribes to:
  - home/pi1/commands    : LED control commands from dashboard

Requirements (Pi):
  pip3 install paho-mqtt bleak SpeechRecognition rpi_ws281x adafruit-circuitpython-neopixel
"""

import asyncio
import json
import struct
import threading
import time
import sys

import paho.mqtt.client as mqtt

# ============================================================================
# CONFIGURATION - Update MQTT_BROKER to your Mac's IP address
# ============================================================================
MQTT_BROKER = "172.22.172.152"  # Your Mac's IP
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# Topics
TOPIC_GESTURES = "home/gestures"
TOPIC_PI1_STATUS = "home/pi1/status"
TOPIC_PI1_COMMANDS = "home/pi1/commands"

# IMU Configuration
IMU_MAC = "D9:41:48:15:5E:FB"
CHAR_NOTIFY_PRIMARY = "0000ffe4-0000-1000-8000-00805f9a34fb"
CHAR_NOTIFY_FALLBACK = "0000ffe9-0000-1000-8000-00805f9a34fb"

# Gesture detection thresholds (from original code)
BASELINE_SAMPLES = 100
GESTURE_COOLDOWN = 0.8

def raw_accel_to_g(raw):
    return raw / 32768.0 * 16.0

def raw_gyro_to_dps(raw):
    return raw / 32768.0 * 2000.0

MOTION_START_THRESHOLD_AY_G = raw_accel_to_g(1000)
MOTION_START_THRESHOLD_GYRO = raw_gyro_to_dps(1000)
SWIPE_GZ_THRESHOLD_DPS = raw_gyro_to_dps(1800)
GX_TWIST_THRESHOLD_DPS = raw_gyro_to_dps(8000)
TWIST_AY_THRESHOLD_G = raw_accel_to_g(1500)
AY_DURING_SWIPE_LIMIT_G = raw_accel_to_g(20000)
GZ_DURING_TWIST_LIMIT_DPS = raw_gyro_to_dps(30000)

# ============================================================================
# GLOBAL STATE
# ============================================================================
mqtt_client = None
led_enabled = True
gesture_enabled = True
voice_enabled = True

# ============================================================================
# LED FEEDBACK MODULE
# ============================================================================
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
except ImportError:
    print("[LED] NeoPixel not available (not running on Pi?)")
    LED_AVAILABLE = False
    pixels = None

def led_flash(color=(0, 255, 0), duration=0.3):
    """Flash LEDs with specified color."""
    if not LED_AVAILABLE or not led_enabled:
        print(f"[LED] Flash {color} (simulated)")
        return
    pixels.fill(color)
    time.sleep(duration)
    pixels.fill((0, 0, 0))

def led_set_color(color):
    """Set LEDs to a solid color."""
    if not LED_AVAILABLE or not led_enabled:
        print(f"[LED] Set color {color} (simulated)")
        return
    pixels.fill(color)

def led_off():
    """Turn off all LEDs."""
    if not LED_AVAILABLE:
        return
    pixels.fill((0, 0, 0))

def led_volume_bar(level):
    """Display volume level as LED bar (0-100)."""
    if not LED_AVAILABLE or not led_enabled:
        print(f"[LED] Volume bar {level}% (simulated)")
        return
    num_lit = int((level / 100.0) * NUM_LEDS)
    for i in range(NUM_LEDS):
        if i < num_lit:
            # Green to red gradient
            green = int(255 * (1 - i / NUM_LEDS))
            red = int(255 * (i / NUM_LEDS))
            pixels[i] = (red, green, 0)
        else:
            pixels[i] = (0, 0, 0)

# ============================================================================
# MQTT CALLBACKS AND PUBLISHING
# ============================================================================
def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connected to broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_PI1_COMMANDS)
        print(f"[MQTT] Subscribed to {TOPIC_PI1_COMMANDS}")
        
        # Publish online status
        publish_status("online")
    else:
        print(f"[MQTT] Connection failed with code {rc}")

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
            print(f"[GESTURE] Enabled: {gesture_enabled}")
            
        elif command == "voice_enable":
            voice_enabled = payload.get("enabled", True)
            print(f"[VOICE] Enabled: {voice_enabled}")
            
        elif command == "status":
            publish_status("online")
            
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

def on_mqtt_disconnect(client, userdata, rc):
    print(f"[MQTT] Disconnected (rc={rc})")

def publish_gesture(gesture_type, source="gesture"):
    """Publish gesture/voice command to MQTT."""
    if mqtt_client and mqtt_client.is_connected():
        payload = {
            "type": gesture_type,
            "source": source,  # "gesture" or "voice"
            "timestamp": time.time(),
            "device": "pi1"
        }
        mqtt_client.publish(TOPIC_GESTURES, json.dumps(payload))
        print(f"[MQTT] Published: {gesture_type} ({source})")
        
        # Flash LED on gesture detection
        if source == "gesture":
            led_flash((0, 255, 0), 0.2)  # Green for gesture
        else:
            led_flash((0, 0, 255), 0.2)  # Blue for voice

def publish_status(status):
    """Publish Pi 1 status."""
    if mqtt_client and mqtt_client.is_connected():
        payload = {
            "status": status,
            "led_enabled": led_enabled,
            "gesture_enabled": gesture_enabled,
            "voice_enabled": voice_enabled,
            "timestamp": time.time()
        }
        mqtt_client.publish(TOPIC_PI1_STATUS, json.dumps(payload))

# ============================================================================
# IMU GESTURE DETECTION (from BLUETOOTH_GESTURE_READINGS.py)
# ============================================================================
def parse_wt901_packets(buf: bytearray):
    out = []
    i = 0
    while i + 20 <= len(buf):
        if buf[i] != 0x55:
            i += 1
            continue
        frame = bytes(buf[i:i+20])
        out.append(frame)
        i += 20
    del buf[:i]
    return out

def decode_frame(frame: bytes):
    if len(frame) != 20 or frame[0] != 0x55:
        return None
    flag = frame[1]
    if flag == 0x61:
        ax, ay, az, gx, gy, gz, roll, pitch, yaw = struct.unpack_from("<9h", frame, 2)
        accel_g = (ax/32768.0*16.0, ay/32768.0*16.0, az/32768.0*16.0)
        gyro_dps = (gx/32768.0*2000.0, gy/32768.0*2000.0, gz/32768.0*2000.0)
        angle_deg = (roll/32768.0*180.0, pitch/32768.0*180.0, yaw/32768.0*180.0)
        return accel_g, gyro_dps, angle_deg
    return None

async def calibrate_baseline(sample_queue: asyncio.Queue):
    print("[IMU] Calibrating baseline...")
    sum_ay = 0.0
    sum_gz = 0.0
    
    try:
        while True:
            sample_queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    
    for _ in range(BASELINE_SAMPLES):
        (ax, ay, az), (gx, gy, gz), _angles = await sample_queue.get()
        sum_ay += ay
        sum_gz += gz
    
    baseline_ay = sum_ay / BASELINE_SAMPLES
    baseline_gz = sum_gz / BASELINE_SAMPLES
    print(f"[IMU] Baseline: ay={baseline_ay:.4f}g, gz={baseline_gz:.2f}dps")
    return baseline_ay, baseline_gz

async def detect_single_gesture(sample_queue: asyncio.Queue, baseline_ay: float, baseline_gz: float):
    while True:
        if not gesture_enabled:
            await asyncio.sleep(0.1)
            continue
            
        (ax, ay, az), (gx, gy, gz), _angles = await sample_queue.get()
        
        dy = ay - baseline_ay
        dgz = gz - baseline_gz
        
        abs_dy = abs(dy)
        abs_dgz = abs(dgz)
        abs_gx = abs(gx)
        
        if (abs_dy < MOTION_START_THRESHOLD_AY_G and
            abs_dgz < MOTION_START_THRESHOLD_GYRO and
            abs_gx < MOTION_START_THRESHOLD_GYRO):
            continue
        
        # Twist detection (gx-dominated)
        if (abs_gx > GX_TWIST_THRESHOLD_DPS and
            abs_dy > TWIST_AY_THRESHOLD_G and
            abs_dgz < GZ_DURING_TWIST_LIMIT_DPS):
            return "TWIST_RIGHT" if gx < 0 else "TWIST_LEFT"
        
        # Swipe detection (gz-dominated)
        if (abs_dgz > SWIPE_GZ_THRESHOLD_DPS and
            abs_dy < AY_DURING_SWIPE_LIMIT_G):
            return "SWIPE_UP" if dgz > 0 else "SWIPE_DOWN"

async def run_gesture_detection():
    """Main gesture detection loop using BLE IMU."""
    try:
        from bleak import BleakClient
    except ImportError:
        print("[IMU] Bleak not installed, gesture detection disabled")
        return
    
    print(f"[IMU] Connecting to {IMU_MAC}...")
    
    try:
        async with BleakClient(IMU_MAC) as client:
            print("[IMU] Connected to IMU")
            
            sample_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
            buf = bytearray()
            
            def handler(_sender, data: bytearray):
                buf.extend(data)
                frames = parse_wt901_packets(buf)
                for frame in frames:
                    decoded = decode_frame(frame)
                    if decoded:
                        try:
                            sample_queue.put_nowait(decoded)
                        except asyncio.QueueFull:
                            pass
            
            # Try primary characteristic
            notify_uuid = CHAR_NOTIFY_PRIMARY
            try:
                await client.start_notify(notify_uuid, handler)
            except Exception:
                notify_uuid = CHAR_NOTIFY_FALLBACK
                await client.start_notify(notify_uuid, handler)
            
            print(f"[IMU] Subscribed to {notify_uuid}")
            await asyncio.sleep(1.0)
            
            print("[IMU] Gesture detection active")
            
            while True:
                try:
                    baseline_ay, baseline_gz = await calibrate_baseline(sample_queue)
                    gesture = await detect_single_gesture(sample_queue, baseline_ay, baseline_gz)
                    
                    print(f"[IMU] Detected: {gesture}")
                    publish_gesture(gesture, "gesture")
                    
                    await asyncio.sleep(GESTURE_COOLDOWN)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[IMU] Error in gesture loop: {e}")
                    await asyncio.sleep(1.0)
                    
    except Exception as e:
        print(f"[IMU] Connection error: {e}")

# ============================================================================
# VOICE COMMAND DETECTION (from voice_commands.py)
# ============================================================================
def map_voice_command(text: str):
    """Map recognized text to command string."""
    t = text.lower()
    
    if "next" in t or "skip" in t:
        return "NEXT_TRACK"
    if "previous" in t or "back" in t or "prior" in t or "last" in t:
        return "PREV_TRACK"
    if "pause" in t or "stop" in t:
        return "PAUSE"
    if "resume" in t or ("play" in t and "playlist" not in t):
        return "PLAY"
    if "volume up" in t or "turn up" in t or "louder" in t or "higher" in t:
        return "VOL_UP"
    if "volume down" in t or "turn down" in t or "quieter" in t or "softer" in t:
        return "VOL_DOWN"
    
    return None

def run_voice_detection():
    """Voice command detection loop (runs in separate thread)."""
    try:
        import speech_recognition as sr
    except ImportError:
        print("[VOICE] SpeechRecognition not installed, voice detection disabled")
        return
    
    DEVICE_INDEX = 9
    SAMPLE_RATE = 48000
    CHUNK = 1024
    
    r = sr.Recognizer()
    
    try:
        with sr.Microphone(device_index=DEVICE_INDEX,
                          sample_rate=SAMPLE_RATE,
                          chunk_size=CHUNK) as source:
            print("[VOICE] Calibrating for ambient noise...")
            r.adjust_for_ambient_noise(source, duration=1.0)
            print("[VOICE] Voice detection active")
            
            while True:
                if not voice_enabled:
                    time.sleep(0.1)
                    continue
                
                try:
                    audio = r.listen(source, phrase_time_limit=3.0)
                    
                    try:
                        text = r.recognize_google(audio, language="en-US")
                        print(f"[VOICE] Heard: {text}")
                        
                        cmd = map_voice_command(text)
                        if cmd:
                            print(f"[VOICE] Command: {cmd}")
                            publish_gesture(cmd, "voice")
                            
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
    
    # Setup MQTT client
    mqtt_client = mqtt.Client(client_id="pi1_agent")
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.on_disconnect = on_mqtt_disconnect
    
    # Set last will (offline status)
    mqtt_client.will_set(TOPIC_PI1_STATUS, json.dumps({
        "status": "offline",
        "timestamp": time.time()
    }))
    
    try:
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[MQTT] Failed to connect: {e}")
        print("[MQTT] Running in offline mode")
    
    # Start voice detection in separate thread
    voice_thread = threading.Thread(target=run_voice_detection, daemon=True)
    voice_thread.start()
    
    # Run gesture detection in main async loop
    try:
        await run_gesture_detection()
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down...")
    finally:
        publish_status("offline")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        led_off()
        print("[MAIN] Goodbye!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping.")
