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
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "2efb0a500cd74fc294cefa026a4bf374"
SPOTIFY_REFRESH_TOKEN = "AQBF0twQ8qFKk-OCfoNkoKcPAjGtf9Sd-gZeOSpRxAOZSjPyQ6Cho3x1alTmBzC8qvR1perxMTfCyD43SL5aTXd-68x9wJqgT5vXv2-2f728K52g2-onqge5TqjloGU87oQ"


# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "2efb0a500cd74fc294cefa026a4bf374"
SPOTIFY_REFRESH_TOKEN = "AQAJJO-ftiuUKtHMfmEef_JrSvt4w_2iQ3oa94Qscv0TSm0dT70AnfXjARhTJOIglbFGL_t84KlifpDJGvaPDreOzZROkQ2PUkGww7-sitMcFMD7e2ZZ3XTC5yLL1F-at0E"


# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "2efb0a500cd74fc294cefa026a4bf374"
SPOTIFY_REFRESH_TOKEN = "AQALuQSwu9o2hcrmpMhWAMJ_0mcLvfPVNMqhdsV1F0zljeG118iw-R-PM3ByIPHvRE67_938A9nssj3Qw92Qh_4sbBBt2AIZYe-1eDyTRrI7FePk3-3GJi-q4LzYvFaSoDk"


# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "2efb0a500cd74fc294cefa026a4bf374"
SPOTIFY_REFRESH_TOKEN = "AQAPUF8GYClUZVyxnGH1cPcdYuv2VovRMZKocyLnVmtN6nIVRqgdujWDgmHdytKc8qM9uNn4op6Zcy9q0n8gPLJW9vX7jCJouERp10e2-vk_6JIutQax_KLuy-jfzQw3AdY"


# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "4aba9f25c3cd451a9c883fcd6157156a"
SPOTIFY_REFRESH_TOKEN = "AQAORtomnAI860xodY9BjvJUDotoOsLAtL-rEj6-5U2EHVEz2de4NnPssQxDb9qwEjXzRApuvNLmIV6MGbfuERflpuEN8Ui-k7sc11z8aIVdvlYtyH1eAGUkkGeyImXEhu8"


# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "4aba9f25c3cd451a9c883fcd6157156a"
SPOTIFY_REFRESH_TOKEN = "AQD7zjyXgfy2Cz8Npiys6qx8fQKsuAF216UQsSLbqwiYLrrwRVaVZuxv_8NScr7wmHie3x2EMS_sM6FrGPtBrGmgohUmHlS6lXMeCZqes9zwVfV2olHCrUGoifpOxFoSjO4"


# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "4aba9f25c3cd451a9c883fcd6157156a"
SPOTIFY_REFRESH_TOKEN = "AQBaoJsbSLwSbwJZJ7rjrltKqRmNXSk62TQSUv4eK7wkRcJ3d8nmsfwRjwdsqZimIe64vR4dDJq93bykPsWun8ahIBtCc8hHwlR2ZskkpuCI5qMJXhapSwxfwolyyxT-k0o"


# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "ccd684a80e494761a074ad250bfd3e9d"
SPOTIFY_CLIENT_SECRET = "4aba9f25c3cd451a9c883fcd6157156a"
SPOTIFY_REFRESH_TOKEN = "AQDlKO0DF4D5u2wlHaAwpQUye_3bOt5ImJdmzC6vBK0AXmfkzfFe4yOxTmXPPIEJirYEmrcFRlu3zxeX5p3Hbtu4ct9l_i9_dF-jiuXjHmTq3Y5hg0CLhptPNd4I9P8Oreo"
