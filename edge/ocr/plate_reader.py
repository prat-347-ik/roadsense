from __future__ import annotations

import re
from typing import Any
import cv2
import easyocr
import numpy as np

# Global cached reader for standalone function calls
_DEFAULT_READER: easyocr.Reader | None = None


def _get_default_reader() -> easyocr.Reader:
    global _DEFAULT_READER
    if _DEFAULT_READER is None:
        # gpu=False since edge setup runs on CPU/ONNX
        _DEFAULT_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _DEFAULT_READER


def normalize_plate_text(raw_text: str) -> str | None:
    """Minimal normalization for raw OCR output.

    Uppercases, removes whitespace and punctuation noise.
    Does not enforce rigid regex patterns so raw accuracy can be observed.
    """
    if not raw_text:
        return None

    # Uppercase
    text = raw_text.upper()

    # Strip whitespace
    text = re.sub(r"\s+", "", text)

    # Strip noise punctuation / non-alphanumeric symbols
    text = re.sub(r"[^A-Z0-9]", "", text)

    if len(text) < 2:
        return None

    return text


def preprocess_crop(crop: np.ndarray, target_height: int = 64) -> np.ndarray:
    """Basic crop preprocessing for small license plate bounding boxes.

    Upscales small crops proportionally to ensure characters have enough pixel resolution.
    """
    if crop is None or crop.size == 0:
        return crop

    h, w = crop.shape[:2]
    if h < target_height:
        scale = target_height / float(h)
        new_w = max(1, int(w * scale))
        crop = cv2.resize(crop, (new_w, target_height), interpolation=cv2.INTER_CUBIC)

    return crop


# Recommended minimum raw plate box width before attempting OCR (empirically derived)
# Discarding boxes < 75px avoids wasted inference on unresolvable subpixel specks.
MIN_PLATE_WIDTH_GATING: int = 75
DEFAULT_OCR_ALLOWLIST: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class PlateReader:
    """Wrapper around EasyOCR for license plate reading."""

    def __init__(self, reader: easyocr.Reader | None = None, gpu: bool = False):
        if reader is not None:
            self.reader = reader
        else:
            self.reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)

    def read_plate(
        self,
        crop: np.ndarray,
        preprocess: bool = True,
        allowlist: str | None = DEFAULT_OCR_ALLOWLIST,
    ) -> str | None:
        """Extract license plate text from a cropped image array.

        Returns normalized alphanumeric text or None if unreadable / empty.
        Uses alphanumeric allowlist by default to prevent symbol hallucinations.
        Never raises exceptions on bad reads.
        """
        if crop is None or not isinstance(crop, np.ndarray) or crop.size == 0:
            return None

        try:
            processed = preprocess_crop(crop) if preprocess else crop
            # EasyOCR expects RGB/BGR array
            read_kwargs: dict[str, Any] = {"detail": 1, "paragraph": False}
            if allowlist:
                read_kwargs["allowlist"] = allowlist

            results = self.reader.readtext(processed, **read_kwargs)
            if not results:
                return None

            # Concatenate detected text parts ordered by horizontal position
            results_sorted = sorted(results, key=lambda item: item[0][0][0])
            combined_text = "".join(item[1] for item in results_sorted)

            return normalize_plate_text(combined_text)
        except Exception:
            return None


def read_plate(crop: np.ndarray, allowlist: str | None = DEFAULT_OCR_ALLOWLIST) -> str | None:
    """Functional interface for license plate reading.

    Extracts text from a crop using the default EasyOCR instance.
    Returns None for empty/unreadable crops.
    """
    if crop is None or not isinstance(crop, np.ndarray) or crop.size == 0:
        return None

    try:
        reader = _get_default_reader()
        plate_reader = PlateReader(reader=reader)
        return plate_reader.read_plate(crop, allowlist=allowlist)
    except Exception:
        return None
