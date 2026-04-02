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
    # Using follow redirects and stream
    response = requests.get(url, stream=True, allow_redirects=True)
    response.raise_for_status() 
    
    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024*1024): # 1MB chunks
            if chunk:
                f.write(chunk)
    
    final_size = os.path.getsize(filename) / (1024 * 1024)
    print(f"--- Finished. Final size: {final_size:.2f} MB ---")

# Hugging Face Direct LFS links (using 'resolve' is correct, but we ensure it's not a pointer)
download_file("https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v0_19.onnx", "kokoro-v0_19.onnx", expected_min_size_mb=300)
download_file("https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/voices.bin", "voices.bin", expected_min_size_mb=20)