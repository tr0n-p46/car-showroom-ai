import requests
import os
import sys

def download_file(url, filename, expected_min_size_mb):
    if os.path.exists(filename):
        size_mb = os.path.getsize(filename) / (1024 * 1024)
        if size_mb >= expected_min_size_mb:
            print(f"--- SUCCESS: {filename} already exists ({size_mb:.2f} MB). ---")
            return True
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*'
    }
    
    print(f"--- Attempting: {url} ---")
    try:
        response = requests.get(url, stream=True, allow_redirects=True, headers=headers, timeout=30)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk: f.write(chunk)
            
            final_size = os.path.getsize(filename) / (1024 * 1024)
            if final_size >= expected_min_size_mb:
                print(f"--- DOWNLOAD COMPLETE: {filename} ({final_size:.2f} MB) ---")
                return True
        print(f"--- FAILED: HTTP {response.status_code} ---")
        return False
    except Exception as e:
        print(f"--- ERROR: {e} ---")
        return False

# MIRROR LIST (Priority Order)
MODEL_MIRRORS = [
    "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v0_19.onnx?download=true",
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/v0.1.0/kokoro-v0_19.onnx",
    "https://huggingface.co/hexgrad/Kokoro-82M/resolve/v0.19/kokoro-v0_19.onnx"
]

VOICE_MIRRORS = [
    "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/voices.bin?download=true",
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/v0.1.0/voices.bin",
    "https://huggingface.co/hexgrad/Kokoro-82M/resolve/v0.19/voices.bin"
]

print("--- STARTING ASSET RECOVERY ---")

# Recover Model
model_success = False
for mirror in MODEL_MIRRORS:
    if download_file(mirror, "kokoro-v0_19.onnx", 300):
        model_success = True
        break

# Recover Voices
voice_success = False
for mirror in VOICE_MIRRORS:
    if download_file(mirror, "voices.bin", 20):
        voice_success = True
        break

if not (model_success and voice_success):
    print("\nCRITICAL: All mirrors failed. Building without assets will cause a runtime crash.")
    sys.exit(1)

print("\n--- ALL ASSETS READY ---")