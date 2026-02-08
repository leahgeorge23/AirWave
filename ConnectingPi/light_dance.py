#!/usr/bin/env python3
import time
import math
import threading
import json
import subprocess

import numpy as np
import board
import neopixel
import paho.mqtt.client as mqtt

# ============================
# LED CONFIG (GPIO21 = physical pin 40)
# ============================
NUM_LEDS = 60
PIXEL_PIN = board.D21
ORDER = neopixel.GRB

# Brightness modulated by music
MIN_BRIGHT = 0.02
MAX_BRIGHT = 0.7

pixels = neopixel.NeoPixel(
    PIXEL_PIN,
    NUM_LEDS,
    brightness=0.2,
    auto_write=False,
    pixel_order=ORDER
)

# ============================
# MIC CONFIG (USB mic: card 1, device 0)
# ============================
RATE = 16000
N = 1024
DEVICE = "hw:1,0"

# ============================
# FFT + VISUAL TUNING
# ============================
ALPHA = 0.18        # smoothing (0.12 smoother, 0.25 snappier)
GATE = 0.04         # raise if always-on, lower if too dead
DECAY = 0.985       # peak tracker decay (closer to 1 = slower)
FRAME_DT = 0.03

BASS = (30, 180)
MIDS = (180, 1500)
HIGHS = (1500, 6000)

window = np.hanning(N).astype(np.float32)

# ============================
# MQTT (flash overrides from pi1_agent)
# ============================
MQTT_BROKER = json.loads(json.dumps(
    # prefer same env var pattern as pi1_agent
    __import__("os").environ.get("MQTT_BROKER", "Leahs-MacBook-Pro.local")
))
MQTT_PORT = int(__import__("os").environ.get("MQTT_PORT", "1883"))

TOPIC_PI1_COMMANDS = "home/pi1/commands"   # pi1_agent already uses this
led_enabled = True

flash_until = 0.0
flash_rgb = (255, 255, 255)
flash_brightness = 1.0
flash_lock = threading.Lock()


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def band_mean(freqs, mags, f_lo, f_hi):
    idx = np.where((freqs >= f_lo) & (freqs < f_hi))[0]
    if idx.size == 0:
        return 0.0
    return float(np.mean(mags[idx]))


def render_bars(b, m, h):
    # b,m,h are 0..1
    pixels.fill((0, 0, 0))

    nb = int(b * NUM_LEDS)
    nm = int(m * NUM_LEDS)
    nh = int(h * NUM_LEDS)

    # Bass bar from left (red)
    for i in range(nb):
        if i < NUM_LEDS:
            pixels[i] = (255, 0, 0)

    # Highs bar from right (blue)
    for k in range(nh):
        j = NUM_LEDS - 1 - k
        if j >= 0:
            pixels[j] = (0, 0, 255)

    # Mids centered (green)
    center = NUM_LEDS // 2
    half = nm // 2
    for i in range(center - half, center + half):
        if 0 <= i < NUM_LEDS:
            pixels[i] = (0, 255, 0)

    overall = (b + m + h) / 3.0
    pixels.brightness = MIN_BRIGHT + (MAX_BRIGHT - MIN_BRIGHT) * overall
    pixels.show()


def do_flash(rgb=(255, 255, 255), dur=0.20, bright=1.0):
    global flash_until, flash_rgb, flash_brightness
    with flash_lock:
        flash_rgb = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        flash_brightness = float(bright)
        flash_until = time.time() + float(dur)


def mqtt_on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe(TOPIC_PI1_COMMANDS)
        print(f"[MQTT] Connected, subscribed to {TOPIC_PI1_COMMANDS}")
    else:
        print(f"[MQTT] Connect failed: {reason_code}")


def mqtt_on_message(client, userdata, msg):
    global led_enabled
    try:
        payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
    except Exception:
        return

    cmd = payload.get("command", "")

    if cmd == "led_enable":
        led_enabled = bool(payload.get("enabled", True))
        if not led_enabled:
            pixels.fill((0, 0, 0))
            pixels.show()
        print(f"[LED] Enabled: {led_enabled}")

    elif cmd == "led_off":
        pixels.fill((0, 0, 0))
        pixels.show()

    elif cmd == "led_flash":
        # Accept both 'color' (your pi1_agent uses color/duration) and rgb/dur
        color = payload.get("color", payload.get("rgb", [255, 255, 255]))
        dur = payload.get("duration", payload.get("dur", 0.20))
        # Make it VERY noticeable over dancing:
        do_flash(color, dur, bright=1.0)


def start_mqtt():
    # This runs inside the sudo process. Use sudo -E so MQTT_BROKER env passes through if you set it.
    client = mqtt.Client()
    client.on_connect = mqtt_on_connect
    client.on_message = mqtt_on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client


def main():
    print("[FFT] Starting light_dance.py")
    print(f"[FFT] Mic device: {DEVICE}")
    print(f"[MQTT] Broker: {MQTT_BROKER}:{MQTT_PORT}")

    start_mqtt()

    # Start mic capture
    cmd = ["arecord", "-D", DEVICE, "-f", "S16_LE", "-r", str(RATE), "-c", "1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # Smoothed values + adaptive peaks
    sb = sm = sh = 0.0
    pb = pm = ph = 1e-6

    try:
        while True:
            # Flash override takes priority
            with flash_lock:
                flash_active = time.time() < flash_until
                frgb = flash_rgb
                fbright = flash_brightness

            if flash_active:
                if led_enabled:
                    old_bright = pixels.brightness
                    pixels.brightness = fbright
                    pixels.fill(frgb)
                    pixels.show()
                    pixels.brightness = old_bright
                time.sleep(0.02)
                continue

            if not led_enabled:
                time.sleep(0.05)
                continue

            data = proc.stdout.read(N * 2)
            if not data or len(data) < N * 2:
                continue

            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            x = samples * window
            mags = np.abs(np.fft.rfft(x))
            freqs = np.fft.rfftfreq(N, d=1.0 / RATE)

            rb = band_mean(freqs, mags, BASS[0], BASS[1])
            rm = band_mean(freqs, mags, MIDS[0], MIDS[1])
            rh = band_mean(freqs, mags, HIGHS[0], HIGHS[1])

            pb = max(rb, pb * DECAY)
            pm = max(rm, pm * DECAY)
            ph = max(rh, ph * DECAY)

            nb = clamp01(rb / (pb + 1e-6))
            nm = clamp01(rm / (pm + 1e-6))
            nh = clamp01(rh / (ph + 1e-6))

            nb = 0.0 if nb < GATE else nb
            nm = 0.0 if nm < GATE else nm
            nh = 0.0 if nh < GATE else nh

            sb = (1 - ALPHA) * sb + ALPHA * nb
            sm = (1 - ALPHA) * sm + ALPHA * nm
            sh = (1 - ALPHA) * sh + ALPHA * nh

            render_bars(sb, sm, sh)
            time.sleep(FRAME_DT)

    except KeyboardInterrupt:
        pixels.fill((0, 0, 0))
        pixels.show()
        print("\n[FFT] Stopped")


if __name__ == "__main__":
    main()

