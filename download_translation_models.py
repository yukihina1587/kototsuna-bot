"""Download and convert OPUS-MT translation models for CTranslate2.

Usage:
    python download_translation_models.py

Requires: ctranslate2, transformers, sentencepiece, torch
    pip install ctranslate2 transformers[torch] sentencepiece
"""
import os
import shutil
import subprocess
import sys

MODELS_DIR = "models"
MODELS = [
    {
        "name": "opus-mt-ja-en",
        "hf_model": "Helsinki-NLP/opus-mt-ja-en",
        "output_dir": os.path.join(MODELS_DIR, "opus-mt-ja-en"),
    },
    {
        "name": "opus-mt-en-jap",
        "hf_model": "Helsinki-NLP/opus-mt-en-jap",
        "output_dir": os.path.join(MODELS_DIR, "opus-mt-en-jap"),
    },
]

REQUIRED_FILES = ["model.bin", "source.spm", "target.spm"]


def is_model_ready(output_dir: str) -> bool:
    """Check if all required model files exist."""
    return all(
        os.path.isfile(os.path.join(output_dir, f)) and os.path.getsize(os.path.join(output_dir, f)) > 100
        for f in REQUIRED_FILES
    )


def convert_model(hf_model: str, output_dir: str) -> None:
    """Convert HuggingFace model to CTranslate2 INT8 format."""
    print(f"  Converting {hf_model} -> {output_dir} (INT8)...")
    cmd = [
        sys.executable, "-m", "ctranslate2.converters.transformers",
        "--model", hf_model,
        "--output_dir", output_dir,
        "--quantization", "int8",
        "--copy_files", "source.spm", "target.spm",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: try ct2-transformers-converter CLI
        print(f"  Python module failed, trying CLI converter...")
        cmd_cli = [
            "ct2-transformers-converter",
            "--model", hf_model,
            "--output_dir", output_dir,
            "--quantization", "int8",
            "--copy_files", "source.spm", "target.spm",
        ]
        result = subprocess.run(cmd_cli, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr}")
            raise RuntimeError(f"Failed to convert {hf_model}")

    print(f"  Done! Files:")
    for f in os.listdir(output_dir):
        size = os.path.getsize(os.path.join(output_dir, f))
        print(f"    {f} ({size / 1024 / 1024:.1f} MB)")


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    all_ready = all(is_model_ready(m["output_dir"]) for m in MODELS)
    if all_ready:
        print("All translation models already present. Skipping.")
        return

    # Check dependencies
    missing = []
    for pkg in ["ctranslate2", "transformers", "sentencepiece"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print("Install with: pip install ctranslate2 transformers[torch] sentencepiece")
        sys.exit(1)

    for model in MODELS:
        if is_model_ready(model["output_dir"]):
            print(f"SKIP {model['name']} (already exists)")
            continue

        print(f"\nProcessing {model['name']}...")
        # Clean partial output
        if os.path.exists(model["output_dir"]):
            shutil.rmtree(model["output_dir"])

        convert_model(model["hf_model"], model["output_dir"])

        if not is_model_ready(model["output_dir"]):
            print(f"ERROR: {model['name']} conversion incomplete!")
            sys.exit(1)

        print(f"OK: {model['name']}")

    print("\nAll translation models ready!")


if __name__ == "__main__":
    main()
