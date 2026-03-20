# Team 6 Project Overview

This project is an interactive Raspberry Pi system that combines:

- person tracking with a camera,
- gesture/voice-triggered controls,
- Bluetooth + Spotify playback control, and
- MQTT-based communication with a local dashboard.

## Project Structure

- `ConnectingPi/`: main runtime code for Pi agents, dashboard, setup scripts, and media/control logic.
- `ConnectingPi/README.md`: detailed documentation for the `ConnectingPi` subsystem.
- `debug_mode.md`: notes for running and troubleshooting in debug mode.

## Main Components

- `pi1_agent.py`: input side (gesture/voice events and command publishing).
- `pi2_agent.py`: tracking, auto-volume, mood analysis, and playback/status control.
- `launcher.py`: setup and launch orchestration across devices.
- `dashboard/`: browser UI for status, controls, and mood/playlist feedback.

## Quick Start

1. Configure device and broker settings in `ConnectingPi/config.py`.
2. Make sure required packages/tools are installed on the Raspberry Pi(s).
3. Run the launcher to start the system:
   - `python3 ConnectingPi/launcher.py`

## Notes

- This project depends on Raspberry Pi hardware, camera access, Bluetooth audio, and an MQTT broker.
- For implementation details, known risks, and future improvements, see `ConnectingPi/README.md`.

