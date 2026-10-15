"""Paper-Sperre: Vor jeder Order wird der Kontoname im Handelspanel gelesen.
Steht dort nicht 'Paper' (deutsch: 'Papierhandel'), wird NICHTS geklickt."""
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
    """Paper-Konto: englisch 'Paper Trading', deutsch 'Papierhandel' (auch mit kleinen
    OCR-Fehlern wie 'Paoer', 'Papierhande1'). Alles andere (z.B. ein Brokername) = nein."""
    t = re.sub(r"[^a-z]", "", text.lower())
    return bool(re.search(r"pa[pvo](ie|i|e)r(t|h|$)", t))


def _grab_and_save(rect, log_dir) -> str:
    from .ocr import grab, save_debug
    return str(save_debug(grab(rect), log_dir, "konto_fehler"))


class PaperLock:
    def __init__(self, cfg: dict, journal, read_fn: Callable[[object], str] = read_account,
                 picture_fn: Callable[[object, object], str] = _grab_and_save):
        self.cfg = cfg
        self.journal = journal
        self.read_fn = read_fn
        self.picture_fn = picture_fn

    def _save_picture(self, rect):
        """Bild der Kontoname-Stelle sichern: so sieht man später, was der Bot sah."""
        try:
            out = getattr(self.journal, "out", None)
            where = self.picture_fn(rect, (out / "logs") if out is not None else "logs")
            self.journal.log_action(f"Bild der Kontoname-Stelle: {where}")
        except Exception as exc:
            self.journal.log_action(f"Bild der Kontoname-Stelle nicht gespeichert: {exc}")

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
            self._save_picture(rect)
            raise SafetyError(f"Kein Paper-Konto erkannt (gelesen: {text!r}) - '{what}' NICHT "
                              f"ausgeführt. Der Bot handelt nur im Paper-Trading-Konto.")
