import time
import numpy as np
import subprocess
import shutil

import board
import neopixel

PIXEL_PIN = board.D21
N_PIXELS = 60
BRIGHTNESS = 0.2
ORDER = neopixel.GRB

# Use 48k by default (most Bluetooth sinks run 48k)
RATE = 48000
CHUNK = 2048
CHANNELS = 1

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

def visualize_frame(energy: float, low: float, mid: float, high: float, is_beat: bool):
    energy = clamp01(energy)
    low = clamp01(low)
    mid = clamp01(mid)
    high = clamp01(high)

    seg = max(1, N_PIXELS // 3)

    for i in range(N_PIXELS):
        if i < seg:
            base = (low, 0.0, 0.0)
        elif i < 2 * seg:
            base = (0.0, mid, 0.0)
        else:
            base = (0.0, 0.0, high)

        r = int(255 * base[0] * energy)
        g = int(255 * base[1] * energy)
        b = int(255 * base[2] * energy)

        if is_beat:
            r = min(255, r + 80)
            g = min(255, g + 80)
            b = min(255, b + 80)

        pixels[i] = (r, g, b)

    pixels.show()

def run_cmd(cmd_list) -> str:
    return subprocess.check_output(cmd_list, text=True).strip()

def ensure_tools():
    if shutil.which("pactl") is None:
        raise RuntimeError("pactl not found. Install Pulse tools: sudo apt-get install pulseaudio-utils")
    if shutil.which("parec") is None:
        raise RuntimeError("parec not found. Install: sudo apt-get install pulseaudio-utils")

def get_default_sink() -> str:
    return run_cmd(["pactl", "get-default-sink"])

def get_monitor_for_sink(default_sink: str) -> str:
    sources = run_cmd(["pactl", "list", "short", "sources"]).splitlines()

    # First try: exact match on "<sink>.monitor"
    want = default_sink + ".monitor"
    for line in sources:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == want:
            return parts[1]

    # Second try: startswith sink and endswith .monitor
    for line in sources:
        parts = line.split()
        if len(parts) >= 2:
            name = parts[1]
            if name.startswith(default_sink) and name.endswith(".monitor"):
                return name

    # Fallback: any monitor source
    for line in sources:
        parts = line.split()
        if len(parts) >= 2 and parts[1].endswith(".monitor"):
            return parts[1]

    raise RuntimeError("No monitor source found. Is PulseAudio/PipeWire-Pulse running and is there an active sink?")

def open_parec(monitor: str):
    cmd = [
        "parec",
        f"--device={monitor}",
        "--format=s16le",
        f"--rate={RATE}",
        f"--channels={CHANNELS}",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=0)

def compute_features(samples: np.ndarray, prev_energy_smooth: float, prev_beat_level: float):
    if samples.size == 0:
        return 0.0, 0.0, 0.0, 0.0, False, prev_energy_smooth, prev_beat_level

    rms = float(np.sqrt(np.mean(samples * samples)) + 1e-12)
    energy_smooth = 0.85 * prev_energy_smooth + 0.15 * rms

    window = np.hanning(samples.size).astype(np.float32)
    X = np.fft.rfft(samples * window)
    mag = np.abs(X).astype(np.float32)
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / RATE)

    def band_energy(f_lo, f_hi):
        idx = np.where((freqs >= f_lo) & (freqs < f_hi))[0]
        if idx.size == 0:
            return 0.0
        return float(np.mean(mag[idx]))

    low_e = band_energy(20, 200)
    mid_e = band_energy(200, 2000)
    high_e = band_energy(2000, 8000)

    total = low_e + mid_e + high_e + 1e-9
    low = low_e / total
    mid = mid_e / total
    high = high_e / total

    energy = clamp01((energy_smooth - 0.01) / 0.08)

    beat_level = 0.8 * prev_beat_level + 0.2 * low_e
    is_beat = (low_e > 1.6 * beat_level) and (energy > 0.12)

    return energy, low, mid, high, is_beat, energy_smooth, beat_level

def main():
    ensure_tools()

    print("Bluetooth Spotify light-dancing (Pulse monitor). Ctrl+C to stop.")
    default_sink = get_default_sink()
    monitor = get_monitor_for_sink(default_sink)
    print("Default sink :", default_sink)
    print("Using monitor:", monitor)
    print(f"Capture rate : {RATE} Hz")

    prev_energy_smooth = 0.0
    prev_beat_level = 0.0

    bytes_per_sample = 2  # s16le
    frame_bytes = CHUNK * bytes_per_sample * CHANNELS

    p = open_parec(monitor)

    try:
        while True:
            if p.poll() is not None:
                raise RuntimeError("parec exited unexpectedly. Check PulseAudio/PipeWire and the monitor source.")

            raw = p.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                time.sleep(0.005)
                continue

            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            energy, low, mid, high, is_beat, prev_energy_smooth, prev_beat_level = compute_features(
                x, prev_energy_smooth, prev_beat_level
            )
            visualize_frame(energy, low, mid, high, is_beat)

    except KeyboardInterrupt:
        pass
    finally:
        try:
            p.terminate()
        except:
            pass
        clear_pixels()
        print("Stopped.")

if __name__ == "__main__":
    main()
