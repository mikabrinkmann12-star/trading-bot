"""config.json des LIVE-Bots laden/speichern (Kalibrierung, Abläufe, Menge, ...)."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULTS = {
    "tesseract": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "legende": None,          # [left, top, width, height]
    "chart": None,            # [left, top, width, height] - Maus darin -> nicht lesen
    "preisachse": None,       # [left, top, width, height]
    "konto": None,            # [left, top, width, height] - Kontoname (Paper-Sperre)
    "parkplatz": None,        # [x, y] Stelle außerhalb des Charts, wo die Maus parkt
    "fenster": None,          # [x, y] Position des Bot-Fensters
    "menge": 1,               # Kontrakte pro Trade
    "dezimal": ",",           # Dezimalzeichen beim Tippen
    "lese_takt": 0.5,         # Sekunden zwischen zwei Legenden-Lesungen
}


def load(path: str | Path = "config.json") -> dict:
    cfg = dict(DEFAULTS)
    p = Path(path)
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8-sig")))   # auch mit BOM (Editor)
        except json.JSONDecodeError as e:
            raise SystemExit(
                f"{p} ist kaputt (Zeile {e.lineno}, Spalte {e.colno}): {e.msg}. Häufigster Grund: "
                f"ein Pfad mit einfachem \\. Schreibe ihn mit doppeltem \\\\ oder mit /, z.B. "
                f"\"C:\\\\Program Files\\\\Tesseract-OCR\\\\tesseract.exe\".")
    return cfg


def save(cfg: dict, path: str | Path = "config.json"):
    Path(path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def in_rect(x: int, y: int, rect) -> bool:
    if not rect:
        return False
    left, top, w, h = rect
    return left <= x < left + w and top <= y < top + h


def plot_rect(cfg: dict):
    """Der Kerzenbereich: das Chart-Rechteck, rechts begrenzt an der Preisachse (inklusive).
    Alles weiter rechts (Bestellfenster, Watchlist) gehört nicht dazu - auch wenn das
    kalibrierte Chart-Rechteck großzügig darüber gezogen wurde."""
    chart = cfg.get("chart")
    axis = cfg.get("preisachse")
    if not chart:
        return None
    if not axis:
        return list(chart)
    left, top, w, h = chart
    right = min(left + w, axis[0] + axis[2])
    return [left, top, max(1, right - left), h]
