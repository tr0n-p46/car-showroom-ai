import io
import os
from pathlib import Path
import threading
import audioop
import struct

import numpy as np
import scipy.io.wavfile as wavfile
from scipy.signal import resample_poly
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

def _available_voice_ids(engine) -> set[str]:
    """
    Best-effort extraction of available voice IDs from kokoro-onnx.
    The library's internal structure can vary by version.
    """
    for attr in ("voices", "_voices", "voice_map", "_voice_map"):
        v = getattr(engine, attr, None)
        if isinstance(v, dict):
            return set(v.keys())
        if isinstance(v, (list, tuple, set)) and all(isinstance(x, str) for x in v):
            return set(v)
    return set()


def _is_male_voice_id(v: str) -> bool:
    return isinstance(v, str) and v.startswith(("am_", "bm_", "hm_", "jm_", "pm_", "em_", "im_"))


def _resolve_voice_id(engine, requested: str, fallback: str) -> str:
    requested = requested or ""
    fallback = fallback or "af_bella"
    voices = _available_voice_ids(engine)
    if not voices:
        return requested or fallback
    if requested in voices:
        return requested
    if fallback in voices:
        return fallback

    # Prefer a female-sounding default if present.
    for cand in ("af_bella", "af_nicole", "af_sarah", "af_sky", "hf_alpha"):
        if cand in voices:
            return cand

    # Otherwise pick any non-male voice deterministically.
    non_male = sorted(v for v in voices if not _is_male_voice_id(v))
    if non_male:
        return non_male[0]

    return sorted(voices)[0]


def _to_pcm16(samples: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples)
    if samples.dtype.kind == "f":
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak > 0:
            samples = samples * (0.98 / peak)
        samples = np.clip(samples, -1.0, 1.0)
        return (samples * 32767.0).astype(np.int16)
    return samples.astype(np.int16, copy=False)


def _encode_wav_pcm16(pcm16: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    wavfile.write(buf, sample_rate, pcm16)
    return buf.getvalue()


def _encode_wav_mulaw(pcm16: np.ndarray, sample_rate: int) -> bytes:
    """
    Telephony-friendly WAV: 8-bit μ-law at 8kHz.
    This often sounds dramatically cleaner over PSTN than 24k PCM.
    """
    ulaw = audioop.lin2ulaw(pcm16.tobytes(), 2)
    # Manually build a RIFF/WAVE file with WAVE_FORMAT_MULAW (0x0007).
    # The standard library `wave` module can't reliably write non-PCM WAVs.
    num_channels = 1
    bits_per_sample = 8
    audio_format = 7  # WAVE_FORMAT_MULAW
    block_align = num_channels * (bits_per_sample // 8)  # 1
    byte_rate = sample_rate * block_align  # 8000
    data = ulaw

    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,  # PCM-style fmt chunk size
        audio_format,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    )
    data_chunk = struct.pack("<4sI", b"data", len(data)) + data
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    header = struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE")
    return header + fmt_chunk + data_chunk


def generate_speech_wav(
    text: str,
    voice_id: str = "hf_alpha",
    lang: str = "en-us",
    fallback_voice_id: str | None = None,
):
    """
    Generates a WAV file in memory. 
    hf_alpha = Hindi Female (Ananya)
    hm_psi = Hindi Male (Karan)
    """
    engine = load_kokoro()

    # You can override via `KOKORO_SPEED`.
    # kokoro-onnx enforces: 0.5 <= speed <= 2.0
    speed = float(os.getenv("KOKORO_SPEED", "1.0"))
    speed = max(0.5, min(2.0, speed))

    # VAPI typically expects 24kHz PCM WAV for custom TTS; returning 8kHz can be
    # interpreted as 24kHz on the client side and sound like fast "gibberish".
    # Keep 24kHz by default; only downsample if you explicitly set it.
    target_sr = int(os.getenv("TTS_SAMPLE_RATE", "24000"))
    # Default to PCM16 for broad compatibility. (Some clients mis-handle μ-law WAV
    # and play it as PCM, which sounds like gibberish/noise.)
    encoding = os.getenv("TTS_ENCODING", "pcm16").lower().strip()  # mulaw|pcm16

    # If the requested voice isn't actually in voices.bin, kokoro-onnx may fall back.
    # Resolve deterministically to avoid accidentally getting a male/default voice.
    fallback_voice = fallback_voice_id or os.getenv("KOKORO_VOICE_ID", "af_bella")
    voice_id = _resolve_voice_id(engine, voice_id, fallback_voice)

    # Kokoro processes text and returns samples + sample_rate
    samples, sample_rate = engine.create(text, voice=voice_id, speed=speed, lang=lang)

    pcm16 = _to_pcm16(samples)

    # Optional extra pauses (helps perceived speaking rate on phone calls).
    # Values are milliseconds.
    pause_sentence_ms = int(os.getenv("TTS_PAUSE_SENTENCE_MS", "0"))
    pause_comma_ms = int(os.getenv("TTS_PAUSE_COMMA_MS", "0"))
    if pause_sentence_ms > 0 or pause_comma_ms > 0:
        # Create a rough pause map based on punctuation.
        # This is intentionally simple: add silence proportional to punctuation counts.
        sentence_marks = sum(text.count(x) for x in (".", "!", "?", "\n"))
        comma_marks = text.count(",") + text.count(";") + text.count(":")
        total_pause_ms = sentence_marks * pause_sentence_ms + comma_marks * pause_comma_ms
        if total_pause_ms > 0:
            silence_samples = int(sample_rate * (total_pause_ms / 1000.0))
            pcm16 = np.concatenate([pcm16, np.zeros(silence_samples, dtype=np.int16)])

    # Resample only if needed.
    if target_sr > 0 and sample_rate != target_sr:
        # polyphase resampling; keep mono
        pcm16_f = pcm16.astype(np.float32)
        resampled = resample_poly(pcm16_f, target_sr, sample_rate)
        pcm16 = np.clip(resampled, -32768, 32767).astype(np.int16)
        sample_rate = target_sr

    if encoding == "mulaw":
        return _encode_wav_mulaw(pcm16, sample_rate)
    return _encode_wav_pcm16(pcm16, sample_rate)