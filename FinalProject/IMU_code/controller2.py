import time
import re
import subprocess

from led_feedback import flash_green
import pi1_agent


# ---------- BlueZ AVRCP playback control ----------
def _sh(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()

def _get_bluez_player_path() -> str:
    tree = _sh(["busctl", "--system", "tree", "org.bluez"])
    m = re.search(r"(/org/bluez/hci\d+/dev_[0-9A-F_]+/player\d+)", tree, re.I)
    if not m:
        raise RuntimeError("No BlueZ player found. Phone may not expose AVRCP or not connected/streaming.")
    return m.group(1)

def _bluez_player_call(method: str):
    path = _get_bluez_player_path()
    subprocess.run(
        ["busctl", "--system", "call", "org.bluez", path, "org.bluez.MediaPlayer1", method],
        check=False
    )

def prev_track():
    _bluez_player_call("Previous")

def next_track():
    _bluez_player_call("Next")

def play():
    _bluez_player_call("Play")

def pause():
    _bluez_player_call("Pause")


# ---------- Volume control on the Pi sink ----------
def _get_default_sink() -> str:
    return _sh(["pactl", "get-default-sink"])

def volume_up(step_pct: int = 5):
    sink = _get_default_sink()
    subprocess.run(["pactl", "set-sink-volume", sink, f"+{step_pct}%"], check=False)

def volume_down(step_pct: int = 5):
    sink = _get_default_sink()
    subprocess.run(["pactl", "set-sink-volume", sink, f"-{step_pct}%"], check=False)


# ---------- Arbitration ----------

def main():

    while True:
        cmd = pi1_agent.get_voice_command()

        if cmd is None:
            time.sleep(0.02)
            continue

        match cmd:
            case "PREV_TRACK":
                prev_track()
            case "NEXT_TRACK":
                next_track()
            case "PAUSE":
                pause()
            case "PLAY":
                play()
            case "VOL_UP":
                volume_up()
            case "VOL_DOWN":
                volume_down()

if __name__ == "__main__":
    main()
