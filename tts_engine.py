import io
import os
from pathlib import Path
import threading

import numpy as np
import scipy.io.wavfile as wavfile
from kokoro_onnx import Kokoro


def _resolve_model_assets():
    """
    Resolve Kokoro asset paths.

    Railway example: mount your volume at `/models` and (optionally) set `MODEL_DIR=/models`.
    """
    model_filename = "kokoro-v0_19.onnx"
    voices_filename = "voices.bin"

    # Preferred dir: Railway volume mount (default `/models`)
    model_dir = os.getenv("MODEL_DIR", "/models").strip() or "/models"
    candidate_dirs = [Path(model_dir)]

    # Back-compat / local fallbacks
    candidate_dirs += [Path("/app/models"), Path(".")]

    for d in candidate_dirs:
        model_path = d / model_filename
        voices_path = d / voices_filename
        if model_path.exists() and voices_path.exists():
            return model_path, voices_path

    searched = ", ".join(str(p) for p in candidate_dirs)
    raise FileNotFoundError(
        f"Could not find Kokoro assets. Looked for `{model_filename}` and `{voices_filename}` in: {searched}"
    )

_kokoro_lock = threading.Lock()
kokoro = None  # Lazy init: avoid crashing container if assets not uploaded yet


def reset_kokoro():
    """Invalidate the loaded Kokoro instance after uploading new assets."""
    global kokoro
    with _kokoro_lock:
        kokoro = None


def load_kokoro():
    """Load Kokoro once assets exist in the mounted model directory."""
    global kokoro
    with _kokoro_lock:
        if kokoro is not None:
            return kokoro

        model_path, voices_path = _resolve_model_assets()
        kokoro = Kokoro(model_path=str(model_path), voices_path=str(voices_path))
        return kokoro

def generate_speech_wav(text: str, voice_id: str = "hf_alpha", lang: str = "en-us"):
    """
    Generates a WAV file in memory. 
    hf_alpha = Hindi Female (Ananya)
    hm_psi = Hindi Male (Karan)
    """
    engine = load_kokoro()

    speed = float(os.getenv("KOKORO_SPEED", "1.25"))

    # Kokoro processes text and returns samples + sample_rate
    samples, sample_rate = engine.create(text, voice=voice_id, speed=speed, lang=lang)

    # Kokoro returns float samples; many players/streamers (including some TTS
    # integrations) expect standard PCM16 WAV, not IEEE-float WAV.
    samples = np.asarray(samples)
    if samples.dtype.kind == "f":
        # Kokoro floats are typically in [-1, 1]; clamp to be safe.
        samples = np.clip(samples, -1.0, 1.0)
        samples = (samples * 32767.0).astype(np.int16)
    else:
        # If it's already integer PCM, keep it as-is.
        samples = samples.astype(np.int16, copy=False)

    # Write to a buffer in WAV format (PCM16)
    byte_io = io.BytesIO()
    wavfile.write(byte_io, sample_rate, samples)
    return byte_io.getvalue()