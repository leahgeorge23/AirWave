#!/usr/bin/env python3
import asyncio
import struct
import time
import math
from collections import deque
import threading
from bleak import BleakClient

# LED feedback (your file defines flash_green)
from led_feedback import flash_green

IMU_MAC = "D9:41:48:15:5E:FB"
CHAR_NOTIFY_PRIMARY = "0000ffe4-0000-1000-8000-00805f9a34fb"
CHAR_NOTIFY_FALLBACK = "0000ffe9-0000-1000-8000-00805f9a34fb"

MODE_IDLE = "IDLE"
MODE_COMMAND = "COMMAND"

# ---------- Wake / Cancel: DOUBLE FLICK ----------
FLICK_GMAG_THR_DPS = 750.0
FLICK_REFRACTORY_S = 0.20
FLICK_PEAK_WINDOW_S = 0.25

DOUBLE_FLICK_REQUIRED = 2
DOUBLE_FLICK_MAX_SPAN_S = 0.85  # time from 1st->2nd flick

# ---------- Command timing ----------
COMMAND_TIMEOUT_S = 5.0
COMMAND_READY_DELAY_S = 1.25       # initial arm delay
REARM_READY_DELAY_S = 0.8          # shorter delay when re-armed
POST_COMMAND_COOLDOWN_S = 0.40

# Delay before re-arming command mode after a gesture (briefly returns to IDLE first)
REARM_IDLE_S = 0.25

# ---------- History ----------
GESTURE_WINDOW_S = 0.60
HIST_KEEP_S = 2.0

# ---------- Twist detection ----------
TWIST_GY_THR_DPS = 180.0
TWIST_RIGHT_IS_POSITIVE_GY = False  # you flipped this to fix labels

# ---------- Swipe detection (ACCEL Z delta during command mode) ----------
SWIPE_DAZ_THR_G = 0.55
SWIPE_TWIST_REJECT_GY_DPS = 260.0
SWIPE_UP_IS_POSITIVE_DAZ = True

DEBUG_COMMAND = False


# ---------------- Controller-compatibility layer ----------------
_last_gesture_cmd = None
_lock = threading.Lock()
_thread = None


def get_gesture_command():
    global _last_gesture_cmd
    with _lock:
        cmd = _last_gesture_cmd
        _last_gesture_cmd = None
    return cmd


def start_gesture_listener():
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run_async, daemon=True)
    _thread.start()


def _run_async():
    asyncio.run(main())


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
    def __init__(self):
        self.mode = MODE_IDLE

        # history: (t, ax,ay,az, gx,gy,gz)
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

    def _detect_double_flick(self):
        now = time.time()
        if not self._detect_flick_event():
            return False

        self.flick_times.append(now)

        while self.flick_times and (now - self.flick_times[0]) > DOUBLE_FLICK_MAX_SPAN_S:
            self.flick_times.popleft()

        if len(self.flick_times) >= DOUBLE_FLICK_REQUIRED:
            self.flick_times.clear()
            return True
        return False

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
            flash_green()
            if SWIPE_UP_IS_POSITIVE_DAZ:
                return "PAUSE" if daz_best > 0 else "PLAY"
            else:
                return "PAUSE" if daz_best < 0 else "PLAY"
        return None

    async def step(self):
        now = time.time()

        if self.pending_rearm and now >= self.rearm_at_t:
            self.pending_rearm = False
            self._enter_command_mode(via_rearm=True)
            return "REENTER_COMMAND_MODE"

        if self.mode == MODE_IDLE:
            if self._detect_double_flick():
                self._enter_command_mode(via_rearm=False)
                return "ENTER_COMMAND_MODE"
            return None

        if self._detect_double_flick():
            self.mode = MODE_IDLE
            self.clear_history()
            return "CANCEL_TO_IDLE"

        elapsed = now - self.cmd_start_t
        ready_delay = REARM_READY_DELAY_S if self.entered_via_rearm else COMMAND_READY_DELAY_S

        if elapsed < ready_delay:
            return None

        if not self.ready_announced:
            self.ready_announced = True
            return "READY_FOR_GESTURE"

        if elapsed > COMMAND_TIMEOUT_S:
            self.mode = MODE_IDLE
            self.clear_history()
            return "COMMAND_TIMEOUT"

        if now - self.last_cmd_t < POST_COMMAND_COOLDOWN_S:
            return None

        if not self._update_command_baseline():
            return None

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
async def run(client: BleakClient, notify_uuid: str, label: str):
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
    await asyncio.sleep(2.0)

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
                global _last_gesture_cmd
                with _lock:
                    _last_gesture_cmd = evt

                print(f"\nGESTURE: {evt}")
                print(">>> Back to IDLE mode <<<")

    finally:
        try:
            await client.stop_notify(notify_uuid)
        except Exception:
            pass


async def main():
    print(f"Connecting to {IMU_MAC} ...")
    async with BleakClient(IMU_MAC) as client:
        print("Connected.")
        try:
            await run(client, CHAR_NOTIFY_PRIMARY, "PRIMARY")
        except Exception as e:
            print(f"[PRIMARY] Error: {e}")
        print("\nSwitching to fallback notify characteristic...\n")
        await run(client, CHAR_NOTIFY_FALLBACK, "FALLBACK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping.")
