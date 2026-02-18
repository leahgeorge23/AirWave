# 🐛 AirWave Debug Mode

Debug mode provides detailed logging to help troubleshoot issues with the launcher.

## How to Enable Debug Mode

### Option 1: Command-line flag (recommended)
```bash
python3 launcher.py --debug
```

### Option 2: Environment variable
```bash
export AIRWAVE_DEBUG=1
python3 launcher.py
```

Or as a one-liner:
```bash
AIRWAVE_DEBUG=1 python3 launcher.py
```

## What Debug Mode Shows

When enabled, you'll see cyan `[DEBUG HH:MM:SS]` messages showing:

### File Sync Operations
- Local file paths and whether they exist
- Which authentication method is used (password vs SSH key)
- Full scp commands (with passwords obscured)
- Success/failure for each file transfer
- Transfer errors with full stdout/stderr

Example:
```
  [DEBUG 14:32:15] Starting file sync to Pis
  [DEBUG 14:32:15] Mac script directory: /Users/leah/Team6/ConnectingPi
  [DEBUG 14:32:15] Files to sync: 6 files
  [DEBUG 14:32:15] Syncing pi1_agent.py to pi1.local:~/FinalVersion/Team6/ConnectingPi/
  [DEBUG 14:32:15]   Local file: /Users/leah/Team6/ConnectingPi/pi1_agent.py
  [DEBUG 14:32:15]   Exists: True
  [DEBUG 14:32:15]   Using Pi1 password authentication
  [DEBUG 14:32:15]   Command: sshpass -p *** scp /Users/.../pi1_agent.py pi@pi1.local:~/FinalVersion/...
  [DEBUG 14:32:16]   Return code: 0
  [DEBUG 14:32:16]   ✓ Successfully synced pi1_agent.py to pi1.local
```

### SSH Process Startup
- Target host, user, and command
- Whether password or SSH key auth is used
- Full SSH command (with passwords obscured)
- Process ID after successful start
- Detailed error messages if startup fails

Example:
```
  [DEBUG 14:32:20] Starting SSH process: Pi1 Agent
  [DEBUG 14:32:20]   Host: pi1.local
  [DEBUG 14:32:20]   User: pi
  [DEBUG 14:32:20]   Remote command: ~/FinalVersion/Team6/ConnectingPi/pi1_agent.py
  [DEBUG 14:32:20]   MQTT broker: Leahs-MacBook-Pro.local
  [DEBUG 14:32:20]   Using password: True
  [DEBUG 14:32:20]   Using password authentication
  [DEBUG 14:32:20]   SSH command: sshpass -p *** ssh -o StrictHostKeyChecking=no ...
  [DEBUG 14:32:21]   Process started with PID: 12345
```

### Configuration and Setup
- Whether it's a first run or existing installation
- Config file contents
- Setup choices (web vs terminal)
- MQTT broker configuration
- Environment variables

Example:
```
  [DEBUG 14:32:10] === AirWave Launcher Starting ===
  [DEBUG 14:32:10] Python version: 3.11.5 (main, Aug 24 2023, 15:18:16)
  [DEBUG 14:32:10] Script directory: /Users/leah/Team6/ConnectingPi
  [DEBUG 14:32:10] Arguments: {'setup': False, 'dashboard': False, 'pi1': False, ...}
  [DEBUG 14:32:10] Environment variables:
  [DEBUG 14:32:10]   AIRWAVE_DEBUG = 1
  [DEBUG 14:32:10]   MQTT_BROKER = not set
  [DEBUG 14:32:10]   HOME = /Users/leah
  [DEBUG 14:32:10]   USER = leah
```

## Common Debugging Scenarios

### Files Not Syncing to Pis
Enable debug mode and look for:
- `Local file: ... Exists: False` — file missing on Mac
- `Return code: 1` or higher — scp failed
- `stderr: ...` — error message from scp

Common causes:
- Wrong password in `PI1_PASSWORD` / `PI2_PASSWORD`
- Pi not reachable (`ping pi1.local` to test)
- Wrong remote path

### Pi Agents Not Starting
Enable debug mode and look for:
- `FileNotFoundError: sshpass` — sshpass not installed
- `Return code: 255` — SSH connection failed
- Remote command path — check if it matches where files were synced

Common causes:
- Pi not on network
- Wrong password
- Wrong script path (`PI1_SCRIPT_PATH` / `PI2_SCRIPT_PATH`)

### MQTT Issues
Check debug output for:
- MQTT broker value being passed to Pi agents
- Whether environment variable is set correctly

### First-Time Setup Issues
Debug mode shows:
- Whether `.airwave_config.json` exists
- Which setup flow was chosen (web vs terminal)
- Spotify authentication steps

## Disable Debug Mode

### If using --debug flag:
Just remove it:
```bash
python3 launcher.py  # No debug output
```

### If using environment variable:
```bash
unset AIRWAVE_DEBUG
python3 launcher.py
```

Or just run without it:
```bash
python3 launcher.py  # AIRWAVE_DEBUG not set = no debug
```

## Debug Output Location

Debug output goes to stdout (your terminal) along with normal output.

To save to a file:
```bash
python3 launcher.py --debug 2>&1 | tee airwave_debug.log
```

This shows output on screen AND saves it to `airwave_debug.log`.

## Privacy Note

Debug mode obscures passwords with `***` in output, so it's safe to share debug logs without exposing credentials.

However, it may show:
- Your Mac's hostname
- Pi hostnames
- File paths
- Network configuration

Review logs before sharing publicly.