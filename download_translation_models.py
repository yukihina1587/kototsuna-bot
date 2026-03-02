"""Download NLLB-200 translation model (CTranslate2 INT8) from HuggingFace.

Usage:
    python download_translation_models.py

Requires: huggingface_hub
    pip install huggingface_hub
"""
import os
import sys

MODELS_DIR = "models"
NLLB_MODEL_DIR = os.path.join(MODELS_DIR, "nllb-200-distilled-600M-ct2-int8")
HF_REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"

REQUIRED_FILES = ["model.bin", "sentencepiece.bpe.model"]


def is_model_ready(output_dir: str) -> bool:
    """Check if all required model files exist."""
    return all(
        os.path.isfile(os.path.join(output_dir, f))
        and os.path.getsize(os.path.join(output_dir, f)) > 100
        for f in REQUIRED_FILES
    )


def main() -> None:
    if is_model_ready(NLLB_MODEL_DIR):
        print("NLLB-200 translation model already present. Skipping.")
        return

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Missing package: huggingface_hub")
        print("Install with: pip install huggingface_hub")
        sys.exit(1)

    print(f"Downloading {HF_REPO} -> {NLLB_MODEL_DIR}...")
    os.makedirs(NLLB_MODEL_DIR, exist_ok=True)

    snapshot_download(
        repo_id=HF_REPO,
        local_dir=NLLB_MODEL_DIR,
    )

    if not is_model_ready(NLLB_MODEL_DIR):
        print("ERROR: Model download incomplete!")
        sys.exit(1)

    print("\nFiles:")
    for f in os.listdir(NLLB_MODEL_DIR):
        filepath = os.path.join(NLLB_MODEL_DIR, f)
        if os.path.isfile(filepath):
            size = os.path.getsize(filepath)
            print(f"  {f} ({size / 1024 / 1024:.1f} MB)")

    print("\nNLLB-200 translation model ready!")


if __name__ == "__main__":
    main()
