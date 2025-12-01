# requires installation of:
#   sudo apt install portaudio19-dev flac pocketsphinx python3-pocketsphinx python3-pyaudio
#   pip3 install SpeechRecognition

import speech_recognition as sr
import time

DEVICE_INDEX = 9       # "array" device index in list_devices.py
SAMPLE_RATE = 48000
CHUNK = 1024


def map_command(text: str):
    """Map recognized text to a simple command string."""
    t = text.lower()

    if "next" in t or "skip" in t:
        return "NEXT_TRACK"

    if "previous" in t or "back" in t or "prior" in t or "last" in t:
        return "PREV_TRACK"

    if "pause" in t or "stop" in t:
        return "PAUSE"

    if "resume" in t or ("play" in t and "playlist" not in t):
        return "PLAY"

    if "volume up" in t or "turn up" in t or "louder" in t:
        return "VOL_UP"

    if "volume down" in t or "turn down" in t or "quieter" in t:
        return "VOL_DOWN"

    return None


def main():
    r = sr.Recognizer()

    with sr.Microphone(device_index=DEVICE_INDEX,
                       sample_rate=SAMPLE_RATE,
                       chunk_size=CHUNK) as source:
        print("Calibrating for ambient noise... stay quiet for ~1 second.")
        r.adjust_for_ambient_noise(source, duration=1.0)
        print("Done. Listening for commands...")

        while True:
            try:
                print("\n[Listening...]")
                # Listen for up to ~3 seconds per speech detection
                audio = r.listen(source, phrase_time_limit=3.0)

                try:
                    text = r.recognize_google(audio, language="en-US")
                    print("[Raw STT]", repr(text))
                except sr.UnknownValueError:
                    print("[Raw STT] (could not understand)")
                    continue
                except sr.RequestError as e:
                    print("[Raw STT] Google error:", e)
                    continue

                # Map to control command
                cmd = map_command(text)
                if cmd:
                    print("[COMMAND]", cmd)
                    #implement control queue and Raspotify control
                else:
                    print("[COMMAND] None")

            except KeyboardInterrupt:
                print("\nExiting cleanly.")
                break


if __name__ == "__main__":
    main()

