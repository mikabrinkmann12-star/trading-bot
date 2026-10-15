"""Bildschirmausschnitt fotografieren und die OHLC-Legende per Tesseract lesen."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .legend import LegendError, check_plausible, parse_legend

WHITELIST = "OHLC0123456789.,+-()%"
# Verschiedene Vorverarbeitungen: (Skalierung, Schwellwert ja/nein, psm)
VARIANTS = [(3, True, 7), (4, True, 7), (3, False, 7), (2, True, 6)]


class OcrError(RuntimeError):
    pass


def setup_tesseract(path: str | None):
    import pytesseract
    if path and Path(path).exists():
        pytesseract.pytesseract.tesseract_cmd = path


def grab(region):
    """region = [left, top, width, height] -> BGR-Bild (numpy)."""
    import mss
    import numpy as np
    left, top, width, height = region
    with (mss.MSS() if hasattr(mss, "MSS") else mss.mss()) as sct:   # neu: MSS, alt: mss
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    return np.array(shot)[:, :, :3].copy()


def preprocess(img, scale: int = 3, threshold: bool = True):
    import cv2
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if gray.mean() < 127:          # dunkles Theme -> invertieren (Tesseract mag schwarz auf weiß)
        gray = 255 - gray
    if threshold:
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.copyMakeBorder(gray, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)


def ocr_text(img, variant=VARIANTS[0]) -> str:
    import pytesseract
    scale, thr, psm = variant
    cfg = f"--psm {psm} -c tessedit_char_whitelist={WHITELIST}"
    return pytesseract.image_to_string(preprocess(img, scale, thr), config=cfg).strip()


def read_ohlc(img) -> tuple[tuple[float, float, float, float] | None, str]:
    """Probiert die Vorverarbeitungen durch, bis eine plausible Legende herauskommt."""
    last = ""
    for v in VARIANTS:
        text = ocr_text(img, v)
        last = text
        try:
            vals = parse_legend(text)
        except LegendError:
            continue
        if check_plausible(*vals) is None:
            return vals, text
    return None, last


def save_debug(img, log_dir: str | Path, tag: str) -> Path:
    import cv2
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"ocr_{tag}_{datetime.now():%Y%m%d_%H%M%S}.png"
    cv2.imwrite(str(p), img)
    return p


def read_candle(region, prev_close: float | None = None, retries: int = 3,
                log_dir: str | Path = "logs", pause: float = 0.3):
    """Liest O,H,L,C. Unplausibel -> bis zu `retries`-mal neu lesen, dann OcrError."""
    reason = ""
    img = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(pause)
        img = grab(region)
        vals, text = read_ohlc(img)
        if vals is None:
            reason = f"Legende nicht lesbar (OCR: {text!r})"
            continue
        reason = check_plausible(*vals, prev_close=prev_close) or ""
        if not reason:
            return vals
    path = save_debug(img, log_dir, "fehler") if img is not None else "-"
    raise OcrError(f"{reason}. Nach {retries + 1} Versuchen gestoppt. Bild: {path}")
