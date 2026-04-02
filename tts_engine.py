from kokoro_onnx import Kokoro
import io
import scipy.io.wavfile as wavfile
import numpy as np

# Initialize model (this happens once on startup)
kokoro = Kokoro(
    model_path="/models/kokoro-v0_19.onnx",
    voices_path="/models/voices.bin"
)

def generate_speech_wav(text: str, voice_id: str = "hf_alpha"):
    """
    Generates a WAV file in memory. 
    hf_alpha = Hindi Female (Ananya)
    hm_psi = Hindi Male (Karan)
    """
    # Kokoro processes text and returns samples + sample_rate
    samples, sample_rate = kokoro.create(text, voice=voice_id, speed=1.1, lang="en-us")
    
    # Write to a buffer in WAV format
    byte_io = io.BytesIO()
    wavfile.write(byte_io, sample_rate, samples)
    return byte_io.getvalue()