# requires:
#   sudo pip3 install adafruit-circuitpython-neopixel
#   only demo - to be integrated with Raspotify

import time
import math
import random

import board
import neopixel

# LED config
PIXEL_PIN = board.D21      # GPIO21, physical pin 40
N_PIXELS = 60              # your 60-LED strip
BRIGHTNESS = 0.2
ORDER = neopixel.GRB

pixels = neopixel.NeoPixel(
    PIXEL_PIN,
    N_PIXELS,
    brightness=BRIGHTNESS,
    auto_write=False,
    pixel_order=ORDER,
)


def clear_pixels():
    pixels.fill((0, 0, 0))
    pixels.show()


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def visualize_frame(energy: float,
                    low: float,
                    mid: float,
                    high: float,
                    is_beat: bool):

    energy = clamp01(energy)
    low = clamp01(low)
    mid = clamp01(mid)
    high = clamp01(high)

    seg = max(1, N_PIXELS // 3)

    for i in range(N_PIXELS):
        if i < seg:
            base = (low, 0.0, 0.0)      # low - red
        elif i < 2 * seg:
            base = (0.0, mid, 0.0)      # mid - green
        else:
            base = (0.0, 0.0, high)     # high - blue

        r = int(255 * base[0] * energy)
        g = int(255 * base[1] * energy)
        b = int(255 * base[2] * energy)

        if is_beat:
            r = min(255, r + 80)
            g = min(255, g + 80)
            b = min(255, b + 80)

        pixels[i] = (r, g, b)

    pixels.show()


# currently demo only (without Raspotify)
# When Raspotify is integrated:
#   -delete get_fake_features() and run_fake_light_dancing()
#   -Replace main() loop with real audio→features pipeline
#   -audio code should call visualize_frame(...)

def get_fake_features(t: float):
#for demo only (before Raspotify integration)
    energy = 0.55 + 0.45 * math.sin(2 * math.pi * 0.5 * t)
    energy += 0.15 * (random.random() - 0.5)
    energy = clamp01(energy)

    low = 0.5 + 0.5 * math.sin(2 * math.pi * 0.7 * t)
    mid = 0.5 + 0.5 * math.sin(2 * math.pi * 1.1 * t + 1.3)
    high = 0.5 + 0.5 * math.sin(2 * math.pi * 1.7 * t + 0.4)

    low += 0.2 * (random.random() - 0.5)
    mid += 0.2 * (random.random() - 0.5)
    high += 0.2 * (random.random() - 0.5)

    low = clamp01(low)
    mid = clamp01(mid)
    high = clamp01(high)

    beat_period = 0.6
    phase = (t % beat_period) / beat_period
    is_beat = phase < 0.05

    if random.random() < 0.01:
        is_beat = not is_beat

    return energy, low, mid, high, is_beat


def run_fake_light_dancing():
    print("light-dancing demo (no real audio) Ctrl+C to stop")
    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            energy, low, mid, high, is_beat = get_fake_features(t)
            visualize_frame(energy, low, mid, high, is_beat)
            time.sleep(0.03)
    except KeyboardInterrupt:
        print("\n stopping")
    finally:
        clear_pixels()


def main():
    run_fake_light_dancing()


if __name__ == "__main__":
    main()

