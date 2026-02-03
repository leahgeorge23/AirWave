# compatible (untested) voice_commands.py
#
# Compatible with your controller script
# call start_voice_listener() once at startup
# repeatedly call get_voice_command() in your main loop
# voice has priority
#
# Install:
#   sudo apt install portaudio19-dev flac pocketsphinx python3-pocketsphinx python3-pyaudio
#   pip3 install SpeechRecognition

import threading
import time
import speech_recognition as sr

# Optional LED feedback (won't crash if missing or different signature)
try:
    from led_feedback import led_feedback
except Exception:
    led_feedback = None

DEVICE_INDEX = 9
SAMPLE_RATE = 48000
CHUNK = 1024

_last_voice_cmd = None
_lock = threading.Lock()
_thread = None
_stop = threading.Event()


def map_command(text: str):
    t = text.lower()

    if "next" in t or "skip" in t:
        return "NEXT_TRACK"

    if "previous" in t or "back" in t or "prior" in t or "last" in t:
        return "PREV_TRACK"

    if "pause" in t or "stop" in t:
        return "PAUSE"

    if "resume" in t or ("play" in t and "playlist" not in t):
        return "PLAY"

    if "volume up" in t or "turn up" in t or "louder" in t or "higher" in t:
        return "VOL_UP"

    if "volume down" in t or "turn down" in t or "quieter" in t or "softer" in t:
        return "VOL_DOWN"

    return None


def start_voice_listener():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_voice_loop, daemon=True)
    _thread.start()


def stop_voice_listener():
    _stop.set()


def get_voice_command():
    global _last_voice_cmd
    with _lock:
        cmd = _last_voice_cmd
        _last_voice_cmd = None
    return cmd


def _emit_led_feedback():
    if led_feedback is None:
        return
    try:
        led_feedback()
    except TypeError:
        try:
            led_feedback("green")
        except Exception:
            pass
    except Exception:
        pass


def _voice_loop():
    global _last_voice_cmd

    r = sr.Recognizer()

    with sr.Microphone(
        device_index=DEVICE_INDEX,
        sample_rate=SAMPLE_RATE,
        chunk_size=CHUNK
    ) as source:
        # quick ambient calibration
        r.adjust_for_ambient_noise(source, duration=1.0)

        while not _stop.is_set():
            try:
                # timeout keeps this loop responsive / non-blocking-ish
                audio = r.listen(source, timeout=0.5, phrase_time_limit=3.0)

                try:
                    text = r.recognize_google(audio, language="en-US")
                except sr.UnknownValueError:
                    continue
                except sr.RequestError:
                    continue

                cmd = map_command(text)
                if cmd is not None:
                    with _lock:
                        _last_voice_cmd = cmd
                    _emit_led_feedback()

            except sr.WaitTimeoutError:
                continue
            except Exception:
                # don't ever let the thread die
                time.sleep(0.05)


# Optional: run standalone for testing
if __name__ == "__main__":
    print("Voice listener test. Speak commands. Ctrl+C to exit.")
    start_voice_listener()
    try:
        while True:
            c = get_voice_command()
            if c is not None:
                print("VOICE:", c)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        stop_voice_listener()
        print("Stopped.")
