"""Fast Plate OCR reader integration for RoadSense edge pipeline."""

from __future__ import annotations

import logging
import re
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Cached default FPO reader instance
_DEFAULT_FPO_READER: FPOReader | None = None
MIN_PLATE_WIDTH_GATING: int = 75
DEFAULT_OCR_ALLOWLIST: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


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


def preprocess_crop(
    crop: np.ndarray,
    target_height: int = 64,
    grayscale: bool = False,
) -> np.ndarray:
    """Preprocess crop for OCR.

    FPO handles internal resizing to (128, 64), but expects RGB color format.
    """
    if crop is None or crop.size == 0:
        return crop

    if crop.ndim == 3 and crop.shape[2] == 3:
        return cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return crop


class FPOReader:
    """Wrapper around fast-plate-ocr LicensePlateRecognizer."""

    def __init__(
        self,
        model_name: str = "cct-xs-v2-global-model",
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._recognizer = None

    @property
    def recognizer(self) -> Any:
        if self._recognizer is None:
            from fast_plate_ocr import LicensePlateRecognizer

            self._recognizer = LicensePlateRecognizer(self.model_name, device=self.device)
        return self._recognizer

    def read_plate(
        self,
        crop: np.ndarray,
        return_confidence: bool = True,
        **kwargs: Any,
    ) -> tuple[str | None, float] | str | None:
        """Extract license plate text and confidence from a cropped image array.

        Converts BGR to RGB, runs FPO inference, and applies standard validation.
        """
        if crop is None or not isinstance(crop, np.ndarray) or crop.size == 0:
            return (None, 0.0) if return_confidence else None

        try:
            # Ensure RGB input as required by cct-xs-v2-global-model config
            if crop.ndim == 3 and crop.shape[2] == 3:
                rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            else:
                rgb_crop = crop

            preds = self.recognizer.run(rgb_crop, return_confidence=True)
            if not preds:
                return (None, 0.0) if return_confidence else None

            pred = preds[0]
            raw_text = pred.plate
            norm_text = normalize_plate_text(raw_text)

            conf = 0.0
            if pred.char_probs is not None and len(pred.char_probs) > 0:
                conf = float(np.mean(pred.char_probs))

            if norm_text is None:
                return (None, 0.0) if return_confidence else None

            if return_confidence:
                return norm_text, conf
            return norm_text
        except Exception:
            logger.exception("FPO failed while reading crop with shape %s", crop.shape)
            return (None, 0.0) if return_confidence else None


PlateReader = FPOReader


def _get_default_reader(model_name: str = "cct-xs-v2-global-model") -> FPOReader:
    global _DEFAULT_FPO_READER
    if _DEFAULT_FPO_READER is None or _DEFAULT_FPO_READER.model_name != model_name:
        _DEFAULT_FPO_READER = FPOReader(model_name=model_name)
    return _DEFAULT_FPO_READER


def read_plate(
    crop: np.ndarray,
    model_name: str = "cct-xs-v2-global-model",
    return_confidence: bool = True,
    **kwargs: Any,
) -> tuple[str | None, float] | str | None:
    """Functional interface for fast-plate-ocr reading."""
    if crop is None or not isinstance(crop, np.ndarray) or crop.size == 0:
        return (None, 0.0) if return_confidence else None

    try:
        reader = _get_default_reader(model_name=model_name)
        return reader.read_plate(crop, return_confidence=return_confidence)
    except Exception:
        return (None, 0.0) if return_confidence else None
