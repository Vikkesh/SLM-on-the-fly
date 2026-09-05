"""Decide how images are read: by a vision-capable model, or by local Tesseract OCR when the
configured model cannot see (single text-only model setups)."""

from __future__ import annotations

import io
from functools import lru_cache

import httpx

from . import config


@lru_cache(maxsize=1)
def mode() -> str:
    """'model' or 'ocr'. VISION_MODE=auto asks Ollama whether the vision model has the capability."""
    if config.VISION_MODE in ("model", "ocr"):
        return config.VISION_MODE
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/show", json={"name": config.VISION_MODEL_ID}, timeout=5)
        caps = r.json().get("capabilities") or []
        return "model" if "vision" in caps else "ocr"
    except (httpx.HTTPError, ValueError):
        return "ocr"


def ocr(png: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(f"OCR unavailable: {e}") from e
    try:
        text = pytesseract.image_to_string(Image.open(io.BytesIO(png)))
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError("OCR unavailable: install tesseract-ocr, or use a vision-capable model") from e
    return text.strip() or "(no text recognised in image)"
