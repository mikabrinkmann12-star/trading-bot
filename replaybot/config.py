"""config.json laden/speichern (Kalibrierung, Tesseract-Pfad, Fensterposition)."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULTS = {
    "tesseract": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "legende": None,          # [left, top, width, height]
    "chart": None,            # [left, top, width, height] - Maus darin -> nicht lesen
    "naechste_kerze": None,   # [x, y]
    "fenster": None,          # [x, y] Position des Bot-Fensters
    "max_open_luecke": 25.0,  # Punkte: Open weicht so weit vom letzten Close ab -> Stopp
    "klick_timeout": 0,       # Sekunden ohne neue Kerze nach Klick -> Stopp (0 = aus, wartet ewig)
}


def load(path: str | Path = "config.json") -> dict:
    cfg = dict(DEFAULTS)
    p = Path(path)
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def save(cfg: dict, path: str | Path = "config.json"):
    Path(path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def in_rect(x: int, y: int, rect) -> bool:
    if not rect:
        return False
    left, top, w, h = rect
    return left <= x < left + w and top <= y < top + h
