#!/usr/bin/env python3
"""
=============================================================================
SHARED CONFIGURATION FILE
=============================================================================
Edit this file when transferring code to a new computer/setup.
Both pi1_agent.py and pi2_agent.py import settings from here.

For new users: Run 'python3 launcher.py' and follow the setup wizard!
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

MQTT_BROKER_DEFAULT = "Leahs-MacBook-Pro.local"  # <-- CHANGE THIS
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

try:
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
except ImportError:
    # OpenCV not installed - set default paths (Pi 2 only needs these)
    _cascade_dir = "/usr/share/opencv/haarcascades/"
    FACE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_frontalface_default.xml")
    PROFILE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_profileface.xml")
    UPPER_BODY_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_upperbody.xml")
    EYE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_eye.xml")
    SMILE_CASCADE_PATH = os.path.join(_cascade_dir, "haarcascade_smile.xml")

# ============================================================================
# SPOTIFY API CREDENTIALS
# ============================================================================
# These are automatically configured by running: python3 launcher.py --setup
# 
# If you need to manually set them:
#   1. Go to: https://developer.spotify.com/dashboard
#   2. Create an app with redirect URI: http://127.0.0.1:8888/callback
#   3. Copy your Client ID, Client Secret, and get a Refresh Token
#
# OR just run the setup wizard: python3 launcher.py --setup

# Placeholder values - will be replaced by launcher during setup
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN", "")

# Note: The launcher will append actual credentials here when you run setup.
# The above lines are just fallbacks for environment variable support.

# ============================================================================
# QUICK SETUP INSTRUCTIONS
# ============================================================================
# NEW USERS: Just run 'python3 launcher.py' and follow the interactive setup!
#
# The launcher will:
#   1. Ask for your Mac's hostname (for MQTT broker)
#   2. Guide you through Spotify Developer App creation
#   3. Open your browser to authorize Spotify
#   4. Automatically save all credentials to this file
#   5. Start AirWave!
#
# MANUAL SETUP (if needed):
#
# 1. Find your computer's hostname:
#    - Mac: echo "$(scutil --get LocalHostName).local"
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
#    export SPOTIFY_CLIENT_ID="your_client_id"
#    export SPOTIFY_CLIENT_SECRET="your_client_secret"
#    export SPOTIFY_REFRESH_TOKEN="your_refresh_token"
# ============================================================================

# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ca36b53326bb4d309a48603af9f0be8d"
SPOTIFY_CLIENT_SECRET = "dd70d34f38e84e5fbea1345cfd636389"
SPOTIFY_REFRESH_TOKEN = "AQDqA2qZST6fDN-_D4So36WG1Xbj8nqUz7ps8hR4uDBS-uV86_QUOD0rGkznwJWudVWtCB4R-GDiXJhUsPR2dbSRYHJfgpZP1OAWaaMyHITZUlw2-TIGOxKdaOJygmCtydA"
