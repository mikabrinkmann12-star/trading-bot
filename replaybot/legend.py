"""OHLC-Legende aus OCR-Text lesen (reine Textverarbeitung, testbar ohne Bildschirm).

TradingView zeigt z.B.:  O30.877,00 H30.888,75 L30.847,50 C30.874,25 −2,50 (−0,01%)
"""
from __future__ import annotations

import re

from .models import EPS

# Preis: Tausendergruppen + genau 2 Nachkommastellen, z.B. 30.877,00 / 30877,00 / 30.877.00.
# Endet nach den 2 Nachkommastellen - wichtig, weil OCR oft das Leerzeichen vor der
# Veränderung verschluckt: "C30.874,25-2,50" oder "C30.874,252,50".
# Höchstens eine Tausendergruppe (Preise < 1.000.000), sonst würde ",252" mitgefressen.
_NUM = r"\d{1,3}(?:[.,]?\d{3})?[.,]\d{2}"
_LETTERED = re.compile(
    rf"[O0]\s*({_NUM})\s*H\s*({_NUM})\s*L\s*({_NUM})\s*C\s*({_NUM})", re.IGNORECASE)
# Fallback, wenn die Buchstaben verloren gehen: die ersten 4 Preise
_PRICE = re.compile(_NUM)


class LegendError(ValueError):
    pass


def normalize_number(tok: str) -> float:
    """'30.877,00' -> 30877.0. Der letzte Trenner vor genau 2 Ziffern ist das Komma,
    alle anderen Trenner sind Tausenderpunkte (robust gegen OCR-Verwechslung . / ,)."""
    tok = tok.strip().replace(" ", "")
    m = re.fullmatch(r"([\d.,]*?)[.,](\d{2})", tok)
    if m:
        whole = re.sub(r"[.,]", "", m.group(1))
        return float(f"{whole}.{m.group(2)}")
    return float(re.sub(r"[.,]", "", tok))


def parse_legend(text: str) -> tuple[float, float, float, float]:
    """OCR-Text -> (O, H, L, C). Wirft LegendError, wenn nichts Sinnvolles gefunden wird."""
    clean = text.replace("\n", " ")
    m = _LETTERED.search(clean)
    if m:
        try:
            return tuple(normalize_number(g) for g in m.groups())  # type: ignore[return-value]
        except ValueError:
            pass
    prices = _PRICE.findall(clean)
    if len(prices) >= 4:
        return tuple(normalize_number(p) for p in prices[:4])  # type: ignore[return-value]
    raise LegendError(f"OHLC nicht gefunden in: {text!r}")


def check_plausible(o: float, h: float, l: float, c: float,
                    prev_close: float | None = None, max_jump: float = 0.03) -> str | None:
    """None = ok, sonst der Grund auf Deutsch."""
    if not (l <= min(o, c) + EPS and max(o, c) <= h + EPS):
        return f"L <= O,C <= H verletzt (O {o} H {h} L {l} C {c})"
    if h > 0 and (h - l) > max_jump * h:
        return (f"Spanne H-L {h - l:.2f} ist unrealistisch groß - vermutlich Ziffer falsch "
                f"gelesen (O {o} H {h} L {l} C {c})")
    if prev_close:
        for name, v in (("O", o), ("H", h), ("L", l), ("C", c)):
            if abs(v - prev_close) > max_jump * prev_close:
                return (f"{name} {v} liegt mehr als {max_jump:.0%} vom letzten Close "
                        f"{prev_close} weg - vermutlich Ziffer falsch gelesen")
    return None
