import requests
import os

def download_file(url, filename, expected_min_size_mb):
    if os.path.exists(filename):
        size_mb = os.path.getsize(filename) / (1024 * 1024)
        if size_mb >= expected_min_size_mb:
            print(f"--- {filename} already exists and looks valid ({size_mb:.2f} MB). ---")
            return
        else:
            print(f"--- {filename} is too small ({size_mb:.2f} MB), re-downloading... ---")

    print(f"--- Downloading {filename} from {url} ---")
    # GitHub releases handle redirects well
    response = requests.get(url, stream=True, allow_redirects=True)
    
    if response.status_code != 200:
        print(f"--- ERROR: Could not download {filename}. Status code: {response.status_code} ---")
        response.raise_for_status()

    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024*1024): # 1MB chunks
            if chunk:
                f.write(chunk)
    
    final_size = os.path.getsize(filename) / (1024 * 1024)
    print(f"--- Finished. Final size: {final_size:.2f} MB ---")

# Stable GitHub Release URLs for kokoro-onnx
ONNX_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/v0.2.0/kokoro-v0_19.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/v0.2.0/voices.bin"

download_file(ONNX_URL, "kokoro-v0_19.onnx", expected_min_size_mb=300)
download_file(VOICES_URL, "voices.bin", expected_min_size_mb=20)