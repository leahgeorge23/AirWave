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
# but some firmwares swap roles. We'll start by subscribing to FFE4, and if no
# data arrives, we'll switch to FFE9.

CHAR_NOTIFY_PRIMARY = "0000ffe4-0000-1000-8000-00805f9a34fb"
CHAR_NOTIFY_FALLBACK = "0000ffe9-0000-1000-8000-00805f9a34fb"

def parse_wt901_packets(buf: bytearray):
    """
    WT901 BLE packets are typically 20 bytes, starting with 0x55.
    Common packet type 0x61 contains accel+gyro+angle (9x int16).
    """
    out = []
    # Find and extract 20-byte frames starting with 0x55
    i = 0
    while i + 20 <= len(buf):
        if buf[i] != 0x55:
            i += 1
            continue
        frame = bytes(buf[i:i+20])
        out.append(frame)
        i += 20
    # Remove consumed bytes
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

async def main():
    print(f"Connecting to {IMU_MAC} ...")
    async with BleakClient(IMU_MAC) as client:
        print("Connected.")

        # We'll buffer notifications because some firmwares chunk packets.
        buf = bytearray()
        got_any = {"val": False}

        def handler(_, data: bytearray):
            got_any["val"] = True
            buf.extend(data)
            for frame in parse_wt901_packets(buf):
                decoded = decode_frame(frame)
                if decoded:
                    (ax, ay, az), (gx, gy, gz), (r, p, y) = decoded
                    print(
                        f"Accel(g): {ax:+.3f},{ay:+.3f},{az:+.3f} | "
                        f"Gyro(dps): {gx:+.1f},{gy:+.1f},{gz:+.1f} | "
                        f"Angle(deg): roll={r:+.2f} pitch={p:+.2f} yaw={y:+.2f}"
                    )

        # Try primary notify characteristic
        print(f"Subscribing to notifications on {CHAR_NOTIFY_PRIMARY} ...")
        await client.start_notify(CHAR_NOTIFY_PRIMARY, handler)
        await asyncio.sleep(3.0)

        # If no data, try fallback characteristic
        if not got_any["val"]:
            print("No data received on primary notify char. Switching to fallback...")
            await client.stop_notify(CHAR_NOTIFY_PRIMARY)
            await client.start_notify(CHAR_NOTIFY_FALLBACK, handler)

        print("Streaming... Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())
