# ConnectingPi README

## What this code does

The `ConnectingPi` section runs the Raspberry Pi side of the AirWave system.
It connects camera/gesture inputs, MQTT messaging, Bluetooth audio control, and a web dashboard so the robot can:

- detect and track a person with OpenCV,
- move pan/tilt motors to keep the person centered,
- estimate distance from face/body size and adjust volume automatically,
- react to gesture and dashboard commands over MQTT,
- detect mood (heuristic, with optional DeepFace), and
- recommend/publish Spotify playlists based on mood.

Main files:

- `pi1_agent.py`: gesture/voice side and command publishing.
- `pi2_agent.py`: tracking, auto-volume, mood detection, playback control, and status publishing.
- `spotify_controller.py`: Spotify API helpers.
- `launcher.py`: setup/sync/launch orchestration.
- `dashboard/`: embedded UI to monitor status and send commands.
- `config.py`: hostnames, ports, cascade paths, and device configuration.

## High-level behavior in `pi2_agent.py`

`pi2_agent.py` is the control loop for Pi 2:

1. warms Spotify session and enables Bluetooth discoverable mode,
2. releases/open camera, then starts MQTT,
3. locks onto a person using Haar cascades and a tracker (CSRT/KCF/MIL fallback),
4. continuously updates pan angle with a smoothed PD-style control step,
5. estimates distance from tracked bounding-box area and smooths/clamps updates,
6. maps distance to volume zones (near/mid/far) unless manual override is active,
7. periodically runs mood analysis and publishes mood + playlist recommendation, and
8. publishes system status for the dashboard (`home/pi2/status`).

## Code sources and attribution

This module appears to be team-authored integration code, built around standard APIs and tools:

- OpenCV Haar cascades/tracker APIs (`cv2`),
- Paho MQTT client (`paho.mqtt.client`),
- BlueALSA/`amixer`, `playerctl`, and `bluetoothctl` system commands,
- Pan-Tilt HAT control (`pantilthat`), and
- Spotify integration via `spotify_controller.py`.

Likely external reference material used during development:

- official library documentation (OpenCV, Paho MQTT, Spotify Web API),
- Raspberry Pi/BlueZ command-line examples for Bluetooth media control,
- common community examples for face tracking and MQTT callback structure.

If any direct snippets were copied from specific posts/repos, add exact links and license notes in this section for full attribution.

## Design decisions we made

- **Resilience over strict dependencies:** media control tries Spotify first, then system-level fallbacks (`playerctl`/`bluetoothctl`) so playback still works in mixed states.
- **Robust tracker creation:** multiple tracker constructors are attempted to handle OpenCV version differences.
- **Config portability:** runtime values are loaded from `config.py` with environment-variable fallback for easier deployment on new machines.
- **Stable control behavior:** smoothing, dead zones, and step limits are used for pan movement, distance updates, and volume changes to reduce jitter.
- **Fail-soft mood pipeline:** heuristic mood detection works by default; DeepFace is optional and auto-disables if too slow.
- **Dashboard-first observability:** current volume/distance/pan/tilt/tracking/mood are published over MQTT for remote visibility.

## Known bugs / risk areas

- **Potential topic check bug:** `if msg.topic in (TOPIC_GESTURES):` behaves like substring membership on a string; use `==` for exact topic matching.
- **Volume mapping inconsistency:** dashboard command path remaps 0-100 display volume into 60-100 "real" range, while other paths use full 0-100 directly.
- **Race conditions on globals:** MQTT callbacks and main loop share mutable global state without locks.
- **Aggressive camera cleanup:** `release_camera()` can `kill -9` processes using `/dev/video0`, which may terminate unrelated camera apps.
- **Detection/tracking fragility:** Haar cascade + tracker approach can fail in low light, occlusion, or profile-heavy scenes.
- **Hardware command assumptions:** `sudo` and device-specific commands may fail depending on permissions, BlueALSA setup, or distro differences.

## Future improvements

- Replace string-topic membership checks with strict equality and add message schema validation.
- Move shared runtime state into a small thread-safe state object (or queue/event model).
- Add structured logging and lightweight health metrics (camera FPS, MQTT reconnect count, mood inference latency).
- Calibrate distance and mood models per environment; optionally upgrade detection to modern DNN models.
- Separate hardware side effects behind adapters/interfaces so core logic can be unit-tested.
- Add automated tests for volume mapping, control-loop math, MQTT command handling, and fallback behavior.
- Improve graceful recovery (camera reconnect/backoff, Bluetooth retry strategy, watchdog for stalled loops).

## Quick run notes

- Configure broker/device settings in `config.py` (or environment variables).
- Ensure required system tools/services are installed (`bluealsa`, `amixer`, `bluetoothctl`, optional `playerctl`).
- Start via `launcher.py` for full system orchestration.

