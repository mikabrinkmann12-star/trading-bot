"""Paper-Sperre: Vor jeder Order wird der Kontoname im Handelspanel gelesen.
Steht dort nicht 'Paper', wird NICHTS geklickt."""
from __future__ import annotations

import re
from typing import Callable

from .safety import SafetyError


def read_account(rect) -> str:
    import pytesseract

    from .ocr import grab, preprocess
    img = grab(rect)
    texts = []
    for thr in (False, True):
        texts.append(pytesseract.image_to_string(preprocess(img, 3, thr), config="--psm 7"))
    return " | ".join(t.strip() for t in texts)


def is_paper(text: str) -> bool:
    """'Paper Trading' (auch mit kleinen OCR-Fehlern wie 'Paoer', 'PaperTrading')."""
    t = re.sub(r"[^a-z]", "", text.lower())
    return bool(re.search(r"pa[pvo]er", t))


class PaperLock:
    def __init__(self, cfg: dict, journal, read_fn: Callable[[object], str] = read_account):
        self.cfg = cfg
        self.journal = journal
        self.read_fn = read_fn

    def check(self, what: str):
        rect = self.cfg.get("konto")
        if not rect:
            raise SafetyError("Kontoname ist nicht kalibriert - ohne Paper-Prüfung keine Orders")
        try:
            text = self.read_fn(rect)
        except Exception as exc:
            text = f"(Fehler: {exc})"
        ok = is_paper(text)
        self.journal.log_action(f"Paper-Prüfung vor '{what}': {text!r} -> {'OK' if ok else 'NEIN'}")
        if not ok:
            raise SafetyError(f"Kein Paper-Konto erkannt (gelesen: {text!r}) - '{what}' NICHT "
                              f"ausgeführt. Der Bot handelt nur im Paper-Trading-Konto.")
