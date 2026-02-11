import json
import os
from typing import Optional, Tuple

from vosk import Model, KaldiRecognizer

# Keep these names because pi1_agent imports them
# NOTE: defaulting to 9 is risky; set VOICE_DEVICE in env or change this default.
DEVICE_INDEX = int(os.environ.get("VOICE_DEVICE", "9"))
SAMPLE_RATE = int(os.environ.get("VOICE_RATE", "16000"))  # Vosk best at 16k
CHUNK = int(os.environ.get("VOICE_CHUNK", "1024"))

MODEL_PATH = os.environ.get(
    "VOSK_MODEL_PATH",
    "/home/pi/vosk_models/vosk-model-small-en-us-0.15",
)

# Tight grammar = more reliable
_PHRASES = [
    "play",
    "pause",
    "stop",
    "next",
    "skip",
    "previous",
    "back",
    "volume up",
    "turn up",
    "louder",
    "volume down",
    "turn down",
    "quieter",
    "softer",
]

_model = None
_rec = None


def _init():
    global _model, _rec
    if _rec is not None:
        return

    if not os.path.isdir(MODEL_PATH):
        raise RuntimeError(
            "[VOICE] Vosk model not found at: %s\n"
            "Set VOSK_MODEL_PATH or download the model into that path."
            % MODEL_PATH
        )

    _model = Model(MODEL_PATH)
    grammar = json.dumps(_PHRASES)
    _rec = KaldiRecognizer(_model, SAMPLE_RATE, grammar)


def recognize_offline(audio_data) -> Optional[str]:
    """
    audio_data: speech_recognition.AudioData (from sr.Recognizer.listen)
    Returns recognized text (lowercase) or None.
    """
    _init()

    raw = audio_data.get_raw_data(convert_rate=SAMPLE_RATE, convert_width=2)

    if _rec.AcceptWaveform(raw):
        res = json.loads(_rec.Result())
        t = (res.get("text") or "").strip().lower()
        _rec.Reset()  # helps prevent carryover like "pause pause"
        return t if t else None

    return None


def recognize_offline_with_partial(audio_data) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (text, partial). text is final; partial is interim (may be None/empty).
    """
    _init()

    raw = audio_data.get_raw_data(convert_rate=SAMPLE_RATE, convert_width=2)

    if _rec.AcceptWaveform(raw):
        res = json.loads(_rec.Result())
        t = (res.get("text") or "").strip().lower()
        _rec.Reset()  # helps prevent carryover like "pause pause"
        return (t if t else None, None)

    try:
        partial_res = json.loads(_rec.PartialResult())
        p = (partial_res.get("partial") or "").strip().lower()
        return (None, p if p else None)
    except Exception:
        return (None, None)


def map_command(text: str) -> Optional[str]:
    """Map recognized text to a simple command string (same outputs as before)."""
    if not text:
        return None

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
