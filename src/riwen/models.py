"""Pinned local text models shared by the launcher, downloader and client."""
from dataclasses import dataclass
import os

DEFAULT_MODEL = "qwen3.5-4b"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    filename: str
    url: str
    sha256: str
    download_gb: str


MODELS = {
    "qwen3.5-2b": ModelSpec(
        "Qwen3.5-2B", "qwen3.5-2b-q4_k_m.gguf",
        "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf",
        "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223", "1.28"),
    "qwen3.5-4b": ModelSpec(
        "Qwen3.5-4B", "qwen3.5-4b-q4_k_m.gguf",
        "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf",
        "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4", "2.74"),
    "qwen3-1.7b": ModelSpec(
        "Qwen3-1.7B", "qwen3-1.7b-q4_k_m.gguf",
        "https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_K_M.gguf",
        "72c5c3cb38fa32d5256e2fe30d03e7a64c6c79e668ad84057e3bd66e250b24fb", "1.3"),
}


def selected_model():
    return os.environ.get("RIWEN_MODEL", DEFAULT_MODEL)


def model_spec(identifier):
    try:
        return MODELS[identifier]
    except KeyError:
        raise ValueError(f"Unknown local model {identifier!r}; choose {', '.join(MODELS)} or set RIWEN_MODEL_URL for your own server") from None
