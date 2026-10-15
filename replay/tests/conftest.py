"""Damit die Bild-Tests (Texterkennung) auch unter Windows laufen: Dort steht Tesseract meist
nicht im PATH, sondern unter C:\\Program Files\\Tesseract-OCR - wie in config.json eingetragen.
Ohne diese Datei wurden sie dort still übersprungen ('skipped')."""
import json
import os
import shutil
from pathlib import Path


def _find_tesseract():
    candidates = []
    cfg = Path(__file__).resolve().parent.parent / "config.json"
    if cfg.exists():
        try:
            candidates.append(json.loads(cfg.read_text(encoding="utf-8-sig")).get("tesseract"))
        except (OSError, ValueError):
            pass
    candidates += [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                   r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]
    return next((c for c in candidates if c and Path(c).exists()), None)


if shutil.which("tesseract") is None:
    _exe = _find_tesseract()
    if _exe:
        os.environ["PATH"] = str(Path(_exe).parent) + os.pathsep + os.environ.get("PATH", "")
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = _exe
        except ImportError:
            pass
