import requests
import os
import sys

def download_file(url, filename, expected_min_size_mb):
    if os.path.exists(filename):
        size_mb = os.path.getsize(filename) / (1024 * 1024)
        if size_mb >= expected_min_size_mb:
            print(f"--- {filename} already exists and looks valid ({size_mb:.2f} MB). ---")
            return True
    
    print(f"--- Downloading {filename} from {url} ---")
    # Added User-Agent to avoid being blocked by CDNs
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Showroom-Bot/1.0'}
    
    try:
        # Use stream=True for large 300MB files
        response = requests.get(url, stream=True, allow_redirects=True, headers=headers, timeout=60)
        
        if response.status_code == 404:
            print(f"--- 404 Not Found at {url} ---")
            return False
            
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024*1024): # 1MB chunks
                if chunk:
                    f.write(chunk)
        
        final_size = os.path.getsize(filename) / (1024 * 1024)
        print(f"--- Finished. Final size: {final_size:.2f} MB ---")
        return True
    except Exception as e:
        print(f"--- Error downloading {filename}: {e} ---")
        return False

# 1. Primary URLs (GitHub Latest Redirects)
GITHUB_ONNX = "https://github.com/thewh1teagle/kokoro-onnx/releases/latest/download/kokoro-v0_19.onnx"
GITHUB_VOICES = "https://github.com/thewh1teagle/kokoro-onnx/releases/latest/download/voices.bin"

# 2. Fallback URLs (Hugging Face Resolve)
HF_ONNX = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v0_19.onnx"
HF_VOICES = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/voices.bin"

# Execute Download with Fallback logic
print("STEP 1: Downloading Model File...")
if not download_file(GITHUB_ONNX, "kokoro-v0_19.onnx", 300):
    print("Attempting Hugging Face Fallback for Model...")
    if not download_file(HF_ONNX, "kokoro-v0_19.onnx", 300):
        print("CRITICAL ERROR: Could not download model file.")
        sys.exit(1)

print("\nSTEP 2: Downloading Voices File...")
if not download_file(GITHUB_VOICES, "voices.bin", 20):
    print("Attempting Hugging Face Fallback for Voices...")
    if not download_file(HF_VOICES, "voices.bin", 20):
        print("CRITICAL ERROR: Could not download voices file.")
        sys.exit(1)

print("\n--- All model assets verified and ready. ---")