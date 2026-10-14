"""Kerzen aus einer CSV lesen: Zeit,O,H,L,C (Kopfzeile optional).

Erlaubt auch Semikolon mit Komma als Dezimalzeichen (deutsches Excel):
09:30;30819,0;30852,0;30767,5;30848,8
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import Candle

_TIME_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s*$")


def _num(s: str, decimal_comma: bool) -> float:
    s = s.strip()
    if decimal_comma:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def read_candles(path: str | Path) -> list[Candle]:
    candles = []
    text = Path(path).read_text(encoding="utf-8-sig")
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        semi = ";" in line
        parts = line.split(";" if semi else ",")
        if not _TIME_RE.match(parts[0]):
            continue  # Kopfzeile
        if len(parts) < 5:
            raise ValueError(f"{path}:{lineno}: brauche Zeit,O,H,L,C - gefunden: {line}")
        try:
            o, h, l, c = (_num(p, semi) for p in parts[1:5])
        except ValueError:
            raise ValueError(f"{path}:{lineno}: Zahl nicht lesbar: {line}") from None
        candles.append(Candle(parts[0], o, h, l, c))
    return candles


def date_from_filename(path: str | Path) -> str:
    m = re.search(r"\d{4}-\d{2}-\d{2}", Path(path).name)
    return m.group(0) if m else ""
