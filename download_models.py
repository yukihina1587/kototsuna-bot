"""Download STT model files for ReazonSpeech-k2-v2 + Silero VAD."""
import os
import tarfile
import tempfile
import requests

MODELS_DIR = "models"
REAZONSPEECH_DIR = os.path.join(MODELS_DIR, "reazonspeech")
os.makedirs(REAZONSPEECH_DIR, exist_ok=True)

# Check if already downloaded
required = [
    os.path.join(REAZONSPEECH_DIR, "encoder-epoch-99-avg-1.int8.onnx"),
    os.path.join(REAZONSPEECH_DIR, "decoder-epoch-99-avg-1.int8.onnx"),
    os.path.join(REAZONSPEECH_DIR, "joiner-epoch-99-avg-1.int8.onnx"),
    os.path.join(REAZONSPEECH_DIR, "tokens.txt"),
    os.path.join(MODELS_DIR, "silero_vad.onnx"),
]
if all(os.path.exists(f) and os.path.getsize(f) > 100 for f in required):
    print("All models already present. Skipping download.")
    raise SystemExit(0)

# 1. Download ReazonSpeech tar.bz2 from GitHub Releases
TAR_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-ja-reazonspeech-2024-08-01.tar.bz2"
print(f"Downloading ReazonSpeech model package...")
resp = requests.get(TAR_URL, stream=True, allow_redirects=True)
resp.raise_for_status()

tar_path = os.path.join(tempfile.gettempdir(), "reazonspeech.tar.bz2")
total = int(resp.headers.get("content-length", 0))
downloaded = 0
with open(tar_path, "wb") as f:
    for chunk in resp.iter_content(chunk_size=65536):
        f.write(chunk)
        downloaded += len(chunk)
        if total > 0:
            pct = downloaded * 100 // total
            print(f"\r  {downloaded // 1024 // 1024}MB / {total // 1024 // 1024}MB ({pct}%)", end="", flush=True)
print(f"\n  -> {os.path.getsize(tar_path) / 1024 / 1024:.1f} MB")

# 2. Extract needed files
NEEDED_FILES = {
    "encoder-epoch-99-avg-1.int8.onnx",
    "decoder-epoch-99-avg-1.int8.onnx",
    "joiner-epoch-99-avg-1.int8.onnx",
    "tokens.txt",
}

print("Extracting model files...")
with tarfile.open(tar_path, "r:bz2") as tar:
    for member in tar.getmembers():
        basename = os.path.basename(member.name)
        if basename in NEEDED_FILES:
            member.name = basename  # flatten path
            tar.extract(member, REAZONSPEECH_DIR)
            size_mb = member.size / 1024 / 1024
            print(f"  {basename} ({size_mb:.1f} MB)")

os.remove(tar_path)
print("Cleaned up temp file.")

# 3. Download Silero VAD
vad_path = os.path.join(MODELS_DIR, "silero_vad.onnx")
if os.path.exists(vad_path) and os.path.getsize(vad_path) > 1000:
    print(f"SKIP silero_vad.onnx (already exists)")
else:
    print("Downloading silero_vad.onnx...")
    resp = requests.get(
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
        allow_redirects=True,
    )
    resp.raise_for_status()
    with open(vad_path, "wb") as f:
        f.write(resp.content)
    print(f"  -> {os.path.getsize(vad_path) / 1024 / 1024:.1f} MB")

print("Done! All models ready.")
