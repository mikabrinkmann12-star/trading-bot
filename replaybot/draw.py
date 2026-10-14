"""Long-/Short-Position mit dem aufgenommenen Ablauf einzeichnen - mit Kontrolle nach jedem
Schritt:
  - Box wird an der aktuellen Kerze angelegt, Doppelklick knapp rechts daneben auf die
    Entry-Linie (öffnet die Einstellungen).
  - Bevor getippt wird: Ist der Einstellungsdialog wirklich aufgegangen? Wenn nicht -> Esc und
    sauber abbrechen, statt in den Chart zu tippen.
  - Nach jedem Tippen: Feld per OCR lesen. Steht eine andere Zahl drin -> nochmal tippen,
    beim zweiten Fehlschlag abbrechen.
"""
from __future__ import annotations

import math
import re
import time
from typing import Callable

from .config import in_rect
from .safety import SafetyError

PATCH = (150, 60)       # halbe Breite/Höhe des Bereichs um das erste Feld (Dialog-Check)
FIELD = (110, 16)       # halbe Breite/Höhe eines Eingabefelds (OCR-Kontrolle)


def format_price(value: float, decimal: str = ",", tick: float = 0.25) -> str:
    """30845.125 -> '30845,25' (auf Tick gerundet, Dezimalzeichen wie im TradingView-UI)."""
    rounded = math.floor(value / tick + 0.5) * tick
    return f"{rounded:.2f}".replace(".", decimal)


def numbers_in(text: str) -> list[float]:
    """Alle Zahlen in einem OCR-Text, tolerant: '30.915,50' / '30915.5' / '30 915,50'."""
    out = []
    for tok in re.findall(r"\d[\d.,' ]*\d|\d", text):
        tok = tok.replace(" ", "").replace("'", "")
        m = re.fullmatch(r"([\d.,]*?)[.,](\d{1,2})", tok)
        try:
            if m:
                out.append(float(re.sub(r"[.,]", "", m.group(1)) + "." + m.group(2)))
            else:
                out.append(float(re.sub(r"[.,]", "", tok)))
        except ValueError:
            continue
    return out


def changed(a, b, threshold: float = 0.15) -> bool:
    """Hat sich ein Bildausschnitt deutlich verändert (Dialog auf/zu)?"""
    import numpy as np
    if a is None or b is None or a.shape != b.shape:
        return True
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > 30
    return float(diff.mean()) > threshold


def anchor_pair(steps: list[dict], chart) -> tuple[int | None, int | None]:
    """(Index Klick, der die Box anlegt; Index Doppelklick, der sie öffnet)."""
    if not chart:
        return None, None
    first_type = next((i for i, s in enumerate(steps) if s.get("tippe")), len(steps))
    create = next((i for i in range(first_type)
                   if in_rect(*steps[i]["punkt"], chart) and not steps[i].get("doppel")), None)
    if create is None:
        return None, None
    dbl = next((j for j in range(create + 1, first_type) if steps[j].get("doppel")), None)
    return create, dbl


def _rect_around(x: int, y: int, half) -> list[int]:
    hw, hh = half
    return [x - hw, y - hh, 2 * hw, 2 * hh]


def strip_lines(gray):
    """Rahmenlinien eines Eingabefelds entfernen (Tesseract scheitert sonst daran)."""
    out = gray.copy()
    dark = out < 128
    out[dark.mean(axis=1) > 0.4, :] = 255                 # waagerechte Rahmenlinien
    out[:, dark.mean(axis=0) > 0.8] = 255                 # senkrechte Rahmenlinien
    return out


def _default_field_reader(img) -> str:
    """Mehrere Vorverarbeitungen probieren (Rahmen und grauer Hintergrund stören)."""
    import pytesseract

    from .ocr import preprocess
    for scale, thr, psm in ((3, False, 7), (3, True, 7), (4, False, 6), (2, False, 7)):
        text = pytesseract.image_to_string(
            strip_lines(preprocess(img, scale, thr)),
            config=f"--psm {psm} -c tessedit_char_whitelist=0123456789.,")
        if numbers_in(text):
            return text
    return ""


def _default_snap(rect):
    from .ocr import grab
    return grab(rect)


class Drawer:
    def __init__(self, cfg: dict, guard, *, sleep: Callable[[float], None] = time.sleep,
                 snap: Callable | None = _default_snap,
                 field_reader: Callable | None = _default_field_reader,
                 post: Callable[[str], None] = lambda text: None,
                 clock: Callable[[], float] = time.monotonic):
        self.cfg = cfg
        self.guard = guard
        self.sleep = sleep
        self.snap = snap                    # None = keine Bildkontrolle (nur für Tests)
        self.field_reader = field_reader
        self.post = post
        self.clock = clock

    def has(self, direction: str) -> bool:
        return bool((self.cfg.get("ablaeufe") or {}).get(direction))

    # ------------------------------------------------------------ Kontrollen
    def _wait_for_dialog(self, rect, before) -> bool:
        deadline = self.clock() + float(self.cfg.get("dialog_wartezeit", 3.0))
        while True:
            if changed(before, self.snap(rect)):
                self.sleep(0.4)             # Dialog fertig aufbauen lassen
                return True
            if self.clock() >= deadline:
                return False
            self.sleep(0.2)

    def _field_ok(self, x: int, y: int, value: float) -> bool | None:
        """True = richtige Zahl im Feld, False = falsche Zahl, None = nicht lesbar."""
        if self.snap is None or self.field_reader is None:
            return None
        try:
            nums = numbers_in(self.field_reader(self.snap(_rect_around(x, y, FIELD))))
        except Exception:
            return None
        if not nums:
            return None
        return any(abs(n - value) < 0.01 for n in nums)

    def _leave_field(self):
        """Tab: Feld verlassen -> TradingView übernimmt den Wert, und der blinkende Cursor
        stört das Nachlesen nicht (sonst wird aus '0|' gern eine '9')."""
        self.sleep(0.2)
        self.guard.press("tab", "Feld verlassen")
        self.sleep(0.4)

    def _abort(self, why: str):
        try:
            self.guard.press("esc", "Dialog schließen (Abbruch)")
        finally:
            raise SafetyError(why)

    # ------------------------------------------------------------ Ablauf
    def draw(self, direction: str, entry: float, stop: float, target: float,
             anchor: tuple[int, int | None] | None = None):
        """anchor = (x, y): Box an dieser Stelle anlegen statt am aufgenommenen Punkt.
        y = None -> aufgenommene Höhe behalten."""
        steps = (self.cfg.get("ablaeufe") or {}).get(direction)
        if not steps:
            raise SafetyError(f"Kein Ablauf für '{direction}' aufgenommen "
                              f"(python bot.py --aufnehmen {direction})")
        values = {"entry": entry, "stop": stop, "ziel": target}
        dec = self.cfg.get("dezimal", ",")
        pause = float(self.cfg.get("zeichnen_pause", 1.0))
        dx = int(self.cfg.get("doppelklick_versatz", 12))
        side = "Long" if direction == "long" else "Short"

        create, dbl = anchor_pair(steps, self.cfg.get("chart")) if anchor else (None, None)
        if create is not None:
            ax, ay = anchor
            if ay is None:
                ay = steps[create]["punkt"][1]
        first_type = next((i for i, s in enumerate(steps) if s.get("tippe")), None)
        dialog_rect = before = None
        if first_type and self.snap is not None:
            dialog_rect = _rect_around(*steps[first_type]["punkt"], PATCH)

        for i, st in enumerate(steps):
            x, y = st["punkt"]
            double = bool(st.get("doppel"))
            opens_dialog = dialog_rect is not None and i == first_type - 1
            if opens_dialog:
                before = self.snap(dialog_rect)          # Bild VOR dem Öffnen des Dialogs

            if i == create:
                self.guard.click_in("chart", ax, ay, f"{side}: Box an aktueller Kerze anlegen")
            elif i == dbl and create is not None:
                self.guard.click_in("chart", ax + dx, ay, f"{side}: Box öffnen (Doppelklick)",
                                    double=True)
            else:
                self.guard.click(x, y, f"{side} Schritt {i + 1}", double=double)

            if opens_dialog:
                self.post("Prüfe, ob der Einstellungsdialog offen ist ...")
                if not self._wait_for_dialog(dialog_rect, before):
                    self._abort("Einstellungsdialog ist nicht aufgegangen - Box wurde nicht "
                                "getroffen. Nichts getippt.")

            if st.get("tippe"):
                text = format_price(values[st["tippe"]], dec)
                value = float(text.replace(",", "."))   # gerundeter Wert = was im Feld steht
                self.sleep(0.3)
                self.guard.type_text(text, st["tippe"])
                self._leave_field()
                ok = self._field_ok(x, y, value)
                if ok is False:
                    self.post(f"{st['tippe']}: falsche Zahl im Feld - tippe nochmal ...")
                    self.guard.click(x, y, f"{side} Schritt {i + 1} (nochmal)")
                    self.sleep(0.3)
                    self.guard.type_text(text, st["tippe"] + " (nochmal)")
                    self._leave_field()
                    if self._field_ok(x, y, value) is False:
                        self._abort(f"Im Feld '{st['tippe']}' steht nach 2 Versuchen nicht "
                                    f"{text} - abgebrochen.")
                elif ok is None:
                    self.post(f"{st['tippe']}: Feld nicht lesbar - kann es nicht prüfen.")
            self.sleep(pause)

        self.guard.press("esc", "Auswahl aufheben")
        if self.cfg.get("naechste_kerze"):
            self.guard.move_to(*self.cfg["naechste_kerze"], "Maus aus dem Chart")
