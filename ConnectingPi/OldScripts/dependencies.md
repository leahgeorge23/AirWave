# AirWave Mac Dependencies

## Required Software

### 1. Python 3.7+
Check if installed:
```bash
python3 --version
```

If not installed, download from: https://www.python.org/downloads/

---

## Required Python Packages

### Install all dependencies at once:
```bash
pip3 install requests paho-mqtt urllib3
```

### Or install individually:

#### 1. **requests** (for Spotify API calls)
```bash
pip3 install requests
```

#### 2. **paho-mqtt** (for MQTT communication - dashboard only, not launcher)
```bash
pip3 install paho-mqtt
```

#### 3. **urllib3** (for HTTP requests, usually comes with requests)
```bash
pip3 install urllib3
```

---

## Required System Tools

### 1. **mosquitto** (MQTT broker)
```bash
brew install mosquitto
```

**Configure mosquitto for WebSocket support:**
```bash
# Edit the config file
nano /opt/homebrew/etc/mosquitto/mosquitto.conf
```

Add these lines if not present:
```
listener 1883
listener 9001
protocol websockets
allow_anonymous true
```

**Test mosquitto:**
```bash
mosquitto -c /opt/homebrew/etc/mosquitto/mosquitto.conf
# Should start without errors. Press Ctrl+C to stop.
```

### 2. **sshpass** (for SSH password authentication to Pis)
```bash
brew install hudochenkov/sshpass/sshpass
```

**Test sshpass:**
```bash
sshpass -V
# Should show version number
```

---

## Built-in Python Modules (No Installation Needed)

These are part of Python's standard library and require no installation:
- `os`
- `sys`
- `subprocess`
- `signal`
- `time`
- `socket`
- `argparse`
- `re`
- `json`
- `webbrowser`
- `http.server`
- `threading`
- `urllib.parse`
- `base64`
- `pathlib`

---

## Quick Installation Script

Save this as `install_dependencies.sh` and run it:

```bash
#!/bin/bash
echo "🔧 Installing AirWave Mac Dependencies..."

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install from python.org"
    exit 1
fi
echo "✓ Python 3 found"

# Check Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew not found. Install from https://brew.sh"
    exit 1
fi
echo "✓ Homebrew found"

# Install Python packages
echo "📦 Installing Python packages..."
pip3 install requests paho-mqtt urllib3

# Install mosquitto
echo "🦟 Installing mosquitto..."
brew install mosquitto

# Install sshpass
echo "🔑 Installing sshpass..."
brew tap hudochenkov/sshpass
brew install hudochenkov/sshpass/sshpass

echo ""
echo "✅ All dependencies installed!"
echo ""
echo "Next steps:"
echo "  1. Configure mosquitto: /opt/homebrew/etc/mosquitto/mosquitto.conf"
echo "  2. Run: python3 launcher.py"
```

Make it executable and run:
```bash
chmod +x install_dependencies.sh
./install_dependencies.sh
```

---

## Verification Checklist

After installation, verify everything is ready:

```bash
# Python packages
python3 -c "import requests; print('✓ requests')"
python3 -c "import paho.mqtt.client; print('✓ paho-mqtt')"
python3 -c "import urllib3; print('✓ urllib3')"

# System tools
mosquitto --help | head -1
sshpass -V

# All good? You're ready!
echo "✅ All dependencies verified!"
```

---

## Troubleshooting

### "pip3: command not found"
```bash
# Install pip
python3 -m ensurepip --upgrade
```

### "brew: command not found"
Install Homebrew:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### "mosquitto config not found"
The path depends on your Mac architecture:
- **Apple Silicon (M1/M2/M3):** `/opt/homebrew/etc/mosquitto/mosquitto.conf`
- **Intel Mac:** `/usr/local/etc/mosquitto/mosquitto.conf`

Find it with:
```bash
brew --prefix mosquitto
```

### "sshpass installation fails"
Try the alternative tap:
```bash
brew untap hudochenkov/sshpass
brew tap hudochenkov/sshpass
brew install sshpass
```

---

## Summary

**Minimum requirements for Mac:**
1. ✅ Python 3.7+
2. ✅ `requests` (pip3)
3. ✅ `paho-mqtt` (pip3, for dashboard)
4. ✅ `mosquitto` (brew)
5. ✅ `sshpass` (brew)

**Total installation time:** ~5 minutes

**One-command install:**
```bash
pip3 install requests paho-mqtt urllib3 && brew install mosquitto hudochenkov/sshpass/sshpass
```