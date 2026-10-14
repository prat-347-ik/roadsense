from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge.ocr.plate_reader import PlateReader, read_plate, normalize_plate_text, preprocess_crop


def test_normalize_plate_text():
    assert normalize_plate_text("mh 12 ab 1234") == "MH12AB1234"
    assert normalize_plate_text("DL-01-C-9999") == "DL01C9999"
    assert normalize_plate_text("  ka. 05  mb 777!  ") == "KA05MB777"
    assert normalize_plate_text("A") is None  # Too short
    assert normalize_plate_text("") is None
    assert normalize_plate_text(None) is None


def test_preprocess_crop():
    small = np.zeros((30, 60, 3), dtype=np.uint8)
    upscaled = preprocess_crop(small, target_height=64)
    assert upscaled.shape[0] == 64
    assert upscaled.shape[1] == 128


def test_read_plate_empty():
    assert read_plate(None) is None
    assert read_plate(np.zeros((0, 0, 3), dtype=np.uint8)) is None
    # Blank black image should return None cleanly without error
    blank = np.zeros((40, 100, 3), dtype=np.uint8)
    assert read_plate(blank) is None
