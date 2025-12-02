#!/usr/bin/env python3
import time
from smbus2 import SMBus

# -------------------------
# CONFIGURATION
# -------------------------

MPU6050_ADDR = 0x68   # I2C address from i2cdetect

# How many samples to average at startup to establish baseline each cycle
BASELINE_SAMPLES = 100

# ---- Gesture thresholds (relative to baseline) ----
# We found from your data:
#   - Swipes: big |dgz|, small/moderate |gx|
#   - Twists: HUGE |gx| (often saturating), plus noticeable |dy|

# Minimum motion to even consider it (any axis)
MOTION_START_THRESHOLD = 1000    # min(|dy| or |dgz| or |gx|)

# A swipe is mostly rotation about Z:
SWIPE_GZ_THRESHOLD = 1800        # |gz - baseline_gz| for swipe

# A twist is mostly large rotation on X (gx):
GX_TWIST_THRESHOLD = 8000        # |gx| must exceed this to call it a twist
TWIST_AY_THRESHOLD = 1500        # |dy| should be at least this so it's not just noise

# Safety limits (quite generous)
AY_DURING_SWIPE_LIMIT = 20000    # allow plenty of ay during swipes
GZ_DURING_TWIST_LIMIT = 30000    # ignore insane gz when calling twist

# Time to wait after a gesture before starting the next calibration (seconds)
GESTURE_COOLDOWN = 0.8

# -------------------------
# MPU6050 REGISTERS
# -------------------------
PWR_MGMT_1   = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H  = 0x43


def read_word(bus, reg):
    """Read a signed 16-bit value from the given register."""
    high = bus.read_byte_data(MPU6050_ADDR, reg)
    low = bus.read_byte_data(MPU6050_ADDR, reg + 1)
    value = (high << 8) | low
    if value >= 0x8000:
        value = -((65535 - value) + 1)
    return value


def init_mpu6050(bus):
    """Wake up the MPU6050 from sleep."""
    bus.write_byte_data(MPU6050_ADDR, PWR_MGMT_1, 0)
    time.sleep(0.1)


def calibrate_baseline(bus):
    """
    Measure baseline ay and gz while sensor is at rest.
    Called at the start of EACH gesture cycle.
    """
    print("\nSTEP 1: Collecting starting point data.")
    print("  -> Hold the sensor still. Calibrating baseline...")

    sum_ay = 0
    sum_gz = 0
    for i in range(BASELINE_SAMPLES):
        ay = read_word(bus, ACCEL_XOUT_H + 2)
        gz = read_word(bus, GYRO_XOUT_H + 4)
        sum_ay += ay
        sum_gz += gz
        time.sleep(0.01)  # 10 ms per sample

    baseline_ay = sum_ay / BASELINE_SAMPLES
    baseline_gz = sum_gz / BASELINE_SAMPLES

    print(f"  Baseline set: ay={baseline_ay:.1f}, gz={baseline_gz:.1f}")
    return baseline_ay, baseline_gz


def detect_single_gesture(bus, baseline_ay, baseline_gz):
    """
    Wait for exactly ONE gesture, then return its label.
       Final logic:

      1) Ignore small motion (all |dy|, |dgz|, |gx| below MOTION_START_THRESHOLD).

      2) Prefer classifying as a TWIST if:
           - |gx| > GX_TWIST_THRESHOLD
           - |dy| > TWIST_AY_THRESHOLD
           - |dgz| not insane
         Direction from gx:
           - gx < 0 => TWIST_RIGHT
           - gx > 0 => TWIST_LEFT

      3) If not a twist, classify as SWIPE if:
           - |dgz| > SWIPE_GZ_THRESHOLD
           - |dy| < AY_DURING_SWIPE_LIMIT
         Direction from dgz:
           - dgz > 0 => SWIPE_UP
           - dgz < 0 => SWIPE_DOWN
    """
    print("\nSTEP 2: You may now make ONE gesture.")
    print("  -> Valid gestures: TWIST_RIGHT, TWIST_LEFT, SWIPE_UP, SWIPE_DOWN")
    print("  -> Perform ONE clear gesture now...")

    gesture = None
    while gesture is None:
        # Read current values
        ax = read_word(bus, ACCEL_XOUT_H)
        ay = read_word(bus, ACCEL_XOUT_H + 2)
        az = read_word(bus, ACCEL_XOUT_H + 4)

        gx = read_word(bus, GYRO_XOUT_H)
        gy = read_word(bus, GYRO_XOUT_H + 2)
        gz = read_word(bus, GYRO_XOUT_H + 4)

        # Relative to baseline for ay, gz
        dy = ay - baseline_ay
        dgz = gz - baseline_gz

        abs_dy = abs(dy)
        abs_dgz = abs(dgz)
        abs_gx = abs(gx)

        # Ignore very small movement
        if (
            abs_dy < MOTION_START_THRESHOLD
            and abs_dgz < MOTION_START_THRESHOLD
            and abs_gx < MOTION_START_THRESHOLD
        ):
            time.sleep(0.01)
            continue

        # --- 1) Try TWIST first (gx-dominated) ---
        if (
            abs_gx > GX_TWIST_THRESHOLD
            and abs_dy > TWIST_AY_THRESHOLD
            and abs_dgz < GZ_DURING_TWIST_LIMIT
        ):
            if gx < 0:
                gesture = "TWIST_RIGHT"
            else:
                gesture = "TWIST_LEFT"

        # --- 2) If no twist, try SWIPE (gz-dominated) ---
        if (
            gesture is None
            and abs_dgz > SWIPE_GZ_THRESHOLD
            and abs_dy < AY_DURING_SWIPE_LIMIT
        ):
            if dgz > 0:
                gesture = "SWIPE_UP"
            else:
                gesture = "SWIPE_DOWN"

        # Uncomment this to keep tuning / debugging:
        # print(f"ax={ax} ay={ay} az={az} | gx={gx} gy={gy} gz={gz} | dy={dy} dgz={dgz}")

        time.sleep(0.01)  # ~100 Hz loop

    return gesture

def main():
    bus = SMBus(1)
    init_mpu6050(bus)

    print("MPU6050 gesture program started.")
    print("This program will:")
    print("  1) Collect starting point data (baseline)")
    print("  2) Tell you to make ONE gesture")
    print("  3) Detect and print the gesture")
    print("  4) Cool down, then recalibrate and repeat.\n")

    try:
        while True:
            # 1) Collect starting point data (baseline) for this cycle
            baseline_ay, baseline_gz = calibrate_baseline(bus)

            # 2 & 3) Wait for exactly one gesture and print it
            gesture = detect_single_gesture(bus, baseline_ay, baseline_gz)
            print(f"\nGESTURE DETECTED: {gesture}")

            # 5) Cooldown
            print(f"Cooldown for {GESTURE_COOLDOWN} seconds...")
            time.sleep(GESTURE_COOLDOWN)

            # 6) Recalibrate base position happens automatically on next loop
            print("Recalibrating for a new gesture cycle...")

    except KeyboardInterrupt:
        print("\nStopping gesture program.")
    finally:
        bus.close()


if __name__ == "__main__":
    main()

