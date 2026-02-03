#!/usr/bin/env python3
"""
=============================================================================
SHARED CONFIGURATION FILE
=============================================================================
Edit this file when transferring code to a new computer/setup.
Both pi1_agent.py and pi2_agent.py import settings from here.
=============================================================================
"""

import os

# ============================================================================
# MQTT BROKER SETTINGS
# ============================================================================
# Option 1: Set via environment variable (highest priority)
#   export MQTT_BROKER="your-computer.local"
#
# Option 2: Edit this default value directly
#   Change "YOUR-COMPUTER-NAME.local" to your computer's hostname
#   Examples: "Drews-MacBook-Pro.local", "raspberrypi.local", "192.168.1.100"

MQTT_BROKER_DEFAULT = "Drews-MacBook-Pro.local"  # <-- CHANGE THIS
MQTT_BROKER = os.environ.get("MQTT_BROKER", MQTT_BROKER_DEFAULT)
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# ============================================================================
# BLUETOOTH DEVICE SETTINGS (Pi 1 - IMU Sensor)
# ============================================================================
# The MAC address of your Bluetooth IMU sensor
# Find it by running: bluetoothctl devices

IMU_MAC_ADDRESS = "D9:41:48:15:5E:FB"  # <-- CHANGE THIS to your IMU's MAC

# BLE Characteristic UUIDs (usually don't need to change)
CHAR_NOTIFY_PRIMARY = "0000ffe4-0000-1000-8000-00805f9a34fb"
CHAR_NOTIFY_FALLBACK = "0000ffe9-0000-1000-8000-00805f9a34fb"

# ============================================================================
# BLUETOOTH SPEAKER SETTINGS (Pi 2 - Audio Output)
# ============================================================================
# The MAC address and name of your Bluetooth speaker
# Find it by running: bluetoothctl devices

BLUETOOTH_SPEAKER_MAC = "F8:7D:76:AA:A8:8C"  # <-- CHANGE THIS to your speaker's MAC
BLUETOOTH_SPEAKER_NAME = "A2DP"  # Usually "A2DP" for most speakers

# ============================================================================
# OPENCV CASCADE PATHS
# ============================================================================
# These are the default paths on Raspberry Pi OS
# On other systems, you may need to update these paths
# Common alternative: cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

import cv2
_cascade_dir = "/usr/share/opencv/haarcascades/"

# Try to use cv2.data.haarcascades if available (works on most systems)
try:
    if hasattr(cv2, 'data') and cv2.data.haarcascades:
        _cascade_dir = cv2.data.haarcascades
except:
    pass

FACE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_frontalface_default.xml")
PROFILE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_profileface.xml")
UPPER_BODY_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_upperbody.xml")
EYE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_eye.xml")
SMILE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_smile.xml")

# ============================================================================
# QUICK SETUP INSTRUCTIONS
# ============================================================================
# 1. Find your computer's hostname:
#    - Mac: System Preferences > Sharing > Computer Name
#    - Linux: hostname
#    - Or use IP address: ifconfig | grep "inet "
#
# 2. Find Bluetooth devices:
#    bluetoothctl
#    devices
#
# 3. Set via environment variables (alternative to editing this file):
#    export MQTT_BROKER="your-computer.local"
#    export IMU_MAC="XX:XX:XX:XX:XX:XX"
#    export SPEAKER_MAC="XX:XX:XX:XX:XX:XX"
# ============================================================================
