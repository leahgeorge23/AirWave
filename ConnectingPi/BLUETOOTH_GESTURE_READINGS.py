#!/usr/bin/env python3
import asyncio
import struct
from bleak import BleakClient

IMU_MAC = "D9:41:48:15:5E:FB"

# From your bluetoothctl output:
# Service: 0000ffe5-0000-1000-8000-00805f9a34fb
# Notify characteristic (data): 0000ffe4-0000-1000-8000-00805f9a34fb  (has CCCD)
# Other characteristic: 0000ffe9-0000-1000-8000-00805f9a34fb
#
# In many WT901BLE units, FFE4 is NOTIFY (data out) and FFE9 is WRITE (commands),
# but some firmwares swap roles. We'll:
#  1) try subscribing on FFE4
#  2) if no *decoded* frames arrive, switch to FFE9
#  3) include debug prints so you can see whether bytes arrive and whether 0x55 frames are detected

CHAR_NOTIFY_PRIMARY = "0000ffe4-0000-1000-8000-00805f9a34fb"
CHAR_NOTIFY_FALLBACK = "0000ffe9-0000-1000-8000-00805f9a34fb"

# -------------------------
# OLD LOGIC CONFIG (same intent, converted to BLE units)
# -------------------------
BASELINE_SAMPLES = 100

def raw_accel_to_g(raw):
    return raw / 32768.0 * 16.0

def raw_gyro_to_dps(raw):
    return raw / 32768.0 * 2000.0

MOTION_START_THRESHOLD_AY_G  = raw_accel_to_g(1000)    # ~0.488 g
MOTION_START_THRESHOLD_GYRO  = raw_gyro_to_dps(1000)   # ~61.0 dps

SWIPE_GZ_THRESHOLD_DPS       = raw_gyro_to_dps(1800)   # ~109.9 dps

GX_TWIST_THRESHOLD_DPS       = raw_gyro_to_dps(8000)   # ~488.3 dps
TWIST_AY_THRESHOLD_G         = raw_accel_to_g(1500)    # ~0.732 g

AY_DURING_SWIPE_LIMIT_G      = raw_accel_to_g(20000)   # ~9.77 g (very generous)
GZ_DURING_TWIST_LIMIT_DPS    = raw_gyro_to_dps(30000)  # ~1831 dps

GESTURE_COOLDOWN = 0.8

# -------------------------
# YOUR EXISTING BLE PACKET LOGIC (unchanged)
# -------------------------
def parse_wt901_packets(buf: bytearray):
    """
    WT901 BLE packets are typically 20 bytes, starting with 0x55.
    Common packet type 0x61 contains accel+gyro+angle (9x int16).
    """
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

# -------------------------
# GESTURE LOGIC (Bluetooth version of your old flow)
# -------------------------
async def calibrate_baseline(sample_queue: asyncio.Queue):
    """
    Measure baseline ay and gz while sensor is at rest.
    Called at the start of EACH gesture cycle.
    Uses BLE decoded units: ay in g, gz in dps.
    """
    print("\nSTEP 1: Collecting starting point data.")
    print("  -> Hold the sensor still. Calibrating baseline...")

    sum_ay = 0.0
    sum_gz = 0.0

    # Drain old samples so baseline uses "now"
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

    print(f"  Baseline set: ay={baseline_ay:.4f} g, gz={baseline_gz:.2f} dps")
    return baseline_ay, baseline_gz

async def detect_single_gesture(sample_queue: asyncio.Queue, baseline_ay: float, baseline_gz: float):
    """
    Wait for exactly ONE gesture, then return its label.
    Same logic as your old code.
    """
    print("\nSTEP 2: You may now make ONE gesture.")
    print("  -> Valid gestures: TWIST_RIGHT, TWIST_LEFT, SWIPE_UP, SWIPE_DOWN")
    print("  -> Perform ONE clear gesture now...")

    while True:
        (ax, ay, az), (gx, gy, gz), _angles = await sample_queue.get()

        dy = ay - baseline_ay
        dgz = gz - baseline_gz

        abs_dy  = abs(dy)
        abs_dgz = abs(dgz)
        abs_gx  = abs(gx)

        # Ignore very small movement
        if (
            abs_dy  < MOTION_START_THRESHOLD_AY_G and
            abs_dgz < MOTION_START_THRESHOLD_GYRO and
            abs_gx  < MOTION_START_THRESHOLD_GYRO
        ):
            continue

        # --- 1) Try TWIST first (gx-dominated) ---
        if (
            abs_gx  > GX_TWIST_THRESHOLD_DPS and
            abs_dy  > TWIST_AY_THRESHOLD_G and
            abs_dgz < GZ_DURING_TWIST_LIMIT_DPS
        ):
            return "TWIST_RIGHT" if gx < 0 else "TWIST_LEFT"

        # --- 2) If no twist, try SWIPE (gz-dominated) ---
        if (
            abs_dgz > SWIPE_GZ_THRESHOLD_DPS and
            abs_dy  < AY_DURING_SWIPE_LIMIT_G
        ):
            return "SWIPE_UP" if dgz > 0 else "SWIPE_DOWN"

async def run_gesture_loop(client: BleakClient, notify_uuid: str, label: str):
   """
    Subscribes to notifications, pushes decoded samples into a queue,
    then runs the old baseline->one gesture->cooldown loop forever.
    Includes debug prints to show whether data arrives and whether frames decode.
    """
    sample_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    buf = bytearray()

    stats = {
        "notif_calls": 0,
        "notif_bytes": 0,
        "frames_seen": 0,
        "frames_decoded": 0,
        "last_first_byte": None,
    }

    def handler(_sender, data: bytearray):
        # DEBUG: prove we're receiving bytes
        stats["notif_calls"] += 1
        stats["notif_bytes"] += len(data)
        if len(data) > 0:
            stats["last_first_byte"] = data[0]

        buf.extend(data)

        # Extract frames and decode
        frames = parse_wt901_packets(buf)
        if frames:
            stats["frames_seen"] += len(frames)
        for frame in frames:
            decoded = decode_frame(frame)
            if decoded:
                stats["frames_decoded"] += 1
                try:
                    sample_queue.put_nowait(decoded)
                except asyncio.QueueFull:
                    pass

    print(f"\n[{label}] Subscribing to notifications on {notify_uuid} ...")
    await client.start_notify(notify_uuid, handler)

    # Wait briefly to see if anything arrives/decodes
    await asyncio.sleep(2.0)
    print(
        f"[{label}] After 2s: notif_calls={stats['notif_calls']}, "
        f"notif_bytes={stats['notif_bytes']}, "
        f"last_first_byte={stats['last_first_byte']}, "
        f"frames_seen={stats['frames_seen']}, "
        f"frames_decoded={stats['frames_decoded']}"
    )

    # If we are getting notifications but decoding none, you likely have a different packet format.
    # If no notifications at all, this UUID isn't streaming.
    if stats["frames_decoded"] == 0:
        print(f"[{label}] WARNING: No decoded frames yet on {notify_uuid}.")
        print(f"[{label}] If notif_calls==0: this char isn't notifying.")
        print(f"[{label}] If notif_calls>0 but frames_decoded==0: format/size may differ.")

    print("\nGesture loop running (BLE). Press Ctrl+C to stop.")

    try:
        while True:
            baseline_ay, baseline_gz = await calibrate_baseline(sample_queue)
            gesture = await detect_single_gesture(sample_queue, baseline_ay, baseline_gz)
            print(f"\nGESTURE DETECTED: {gesture}")

            print(f"Cooldown for {GESTURE_COOLDOWN} seconds...")
            await asyncio.sleep(GESTURE_COOLDOWN)

            print("Recalibrating for a new gesture cycle...")

    finally:
        try:
            await client.stop_notify(notify_uuid)
        except Exception:
            pass

async def main():
    print(f"Connecting to {IMU_MAC} ...")
    async with BleakClient(IMU_MAC) as client:
        print("Connected.")

        # Try primary notify characteristic
        try:
            await run_gesture_loop(client, CHAR_NOTIFY_PRIMARY, "PRIMARY")
        except Exception as e:
            print(f"[PRIMARY] Error or no usable data: {e}")

        # If primary didn't work, try fallback
        print("\nSwitching to fallback notify characteristic...\n")
        await run_gesture_loop(client, CHAR_NOTIFY_FALLBACK, "FALLBACK")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping.")
