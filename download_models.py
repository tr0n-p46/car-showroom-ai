import requests
import os

def download_file(url, filename):
    if os.path.exists(filename):
        print(f"{filename} already exists, skipping.")
        return
    print(f"Downloading {filename}...")
    response = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

# Hugging Face URLs for Kokoro v0.19 ONNX
download_file("https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v0_19.onnx", "kokoro-v0_19.onnx")
download_file("https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/voices.bin", "voices.bin")