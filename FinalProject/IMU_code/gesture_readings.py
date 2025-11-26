#!/usr/bin/env python3
import time
from smbus2 import SMBus

# I2C address of MPU6050
MPU6050_ADDR = 0x68

# MPU6050 register addresses
PWR_MGMT_1   = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H  = 0x43

def read_word(bus, reg):
    high = bus.read_byte_data(MPU6050_ADDR, reg)
    low = bus.read_byte_data(MPU6050_ADDR, reg + 1)
    value = (high << 8) | low
    # Convert from unsigned to signed 16-bit
    if value >= 0x8000:
        value = -((65535 - value) + 1)
    return value

def main():
    bus = SMBus(1)

    # Wake up MPU6050 (clear sleep mode)
    bus.write_byte_data(MPU6050_ADDR, PWR_MGMT_1, 0)
    time.sleep(0.1)

    print("Reading MPU6050 values... Press CTRL+C to stop.\n")

    try:
        while True:
            # Read accelerometer
            ax = read_word(bus, ACCEL_XOUT_H)
            ay = read_word(bus, ACCEL_XOUT_H + 2)
            az = read_word(bus, ACCEL_XOUT_H + 4)

            # Read gyroscope
            gx = read_word(bus, GYRO_XOUT_H)
            gy = read_word(bus, GYRO_XOUT_H + 2)
            gz = read_word(bus, GYRO_XOUT_H + 4)

            print(f"Accel: ax={ax}, ay={ay}, az={az} | Gyro: gx={gx}, gy={gy}, gz={gz}")

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        bus.close()

if __name__ == "__main__":
    main()

