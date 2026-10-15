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


def numbers_loose(text: str) -> list[float]:
    """Wie numbers_in, aber zusätzlich jedes durch Leerzeichen getrennte Stück einzeln.
    Nötig, wenn neben dem Preis noch 'Ticks'-Zahlen oder Symbole im Bild stehen
    ('30089.25 245 Ticks' darf nicht zu EINER Zahl verschmelzen)."""
    out = list(numbers_in(text))
    for part in re.split(r"\s+", text):
        out += numbers_in(part)
    return out


def change_ratio(a, b) -> float:
    """Anteil der Pixel, die sich deutlich verändert haben (0.0 - 1.0)."""
    import numpy as np
    if a is None or b is None or a.shape != b.shape:
        return 1.0
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > 30
    return float(diff.mean())


STRONG, SOFT = 0.02, 0.005      # ab 2 % sicher verändert, ab 0,5 % "vermutlich"


def changed(a, b, threshold: float = STRONG) -> bool:
    """Hat sich ein Bildausschnitt verändert (Dialog auf/zu)? Weißer Dialog auf weißem Chart
    ändert nur Text und Rahmen - das sind wenige Prozent der Pixel."""
    return change_ratio(a, b) > threshold


def anchor_pair(steps: list[dict], chart) -> tuple[int | None, int | None]:
    """(Index Klick, der die Box anlegt; Index Doppelklick, der sie öffnet).

    Bevorzugt: der erste Doppelklick im Chart vor dem ersten Tipp-Feld, und als Anlege-Klick
    der LETZTE einfache Chart-Klick davor (ein Fokus-Klick ganz am Anfang zählt so nicht)."""
    if not chart:
        return None, None
    first_type = next((i for i, s in enumerate(steps) if s.get("tippe")), len(steps))
    in_chart = [i for i in range(first_type) if in_rect(*steps[i]["punkt"], chart)]
    dbl = next((i for i in in_chart if steps[i].get("doppel")), None)
    if dbl is not None:
        before = [i for i in in_chart if i < dbl and not steps[i].get("doppel")]
        return (before[-1] if before else None), dbl
    singles = [i for i in in_chart if not steps[i].get("doppel")]
    return (singles[0] if singles else None), None


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


def tight_crops(img, max_blocks: int = 3) -> list:
    """Textblöcke im Feld einzeln ausschneiden, der Reihe nach: zuerst der, der dem Klickpunkt
    (Bildmitte) am nächsten liegt. Feldrahmen fallen weg, ebenso FARBIGER Text (z.B. blaue
    Preise neben dem Feld - Feldtext ist schwarz/grau). Jeder Block wird groß skaliert,
    schwarz auf weiß. Einzelne Ziffern wie die '1' im Mengenfeld liest Tesseract sonst fast nie.
    Symbole (z.B. das Pfeil-Symbol) liefern beim Lesen keine Zahl und werden übersprungen.
    -> Liste von Bildern (evtl. leer)."""
    import cv2
    import numpy as np
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if g.mean() < 127:
        g = 255 - g
    dark = g < 140
    dark[dark.mean(axis=1) > 0.4, :] = False              # waagerechte Rahmenlinien
    dark[:, dark.mean(axis=0) > 0.6] = False              # senkrechte Rahmenlinien
    n, lab, stats, cent = cv2.connectedComponentsWithStats(dark.astype(np.uint8), 8)
    h = g.shape[0]
    spread = img.astype(np.int16).max(axis=2) - img.astype(np.int16).min(axis=2)

    def colored(i):                                         # bunte Schrift = nicht im Feld
        return float(spread[lab == i].mean()) > 60

    comps = sorted((i for i in range(1, n)
                    if stats[i, cv2.CC_STAT_HEIGHT] >= 4
                    and abs(cent[i][1] - h / 2) <= h * 0.3 and not colored(i)),
                   key=lambda i: stats[i, 0])
    if not comps:
        return []
    gap_max = max(14, 1.6 * max(stats[i, cv2.CC_STAT_HEIGHT] for i in comps))
    clusters = [[comps[0]]]
    for i in comps[1:]:                       # zusammenhängender Text: Lücken < gap_max
        prev = clusters[-1][-1]
        if stats[i, 0] - (stats[prev, 0] + stats[prev, 2]) > gap_max:
            clusters.append([i])
        else:
            clusters[-1].append(i)
    mid = g.shape[1] / 2                      # Klickpunkt = Mitte; der Text im Feld liegt dort
                                              # oder links davon, fremder Text weiter weg

    def dist(cl):
        lo = min(stats[i, 0] for i in cl)
        hi = max(stats[i, 0] + stats[i, 2] for i in cl)
        return 0 if lo <= mid <= hi else min(abs(lo - mid), abs(hi - mid))
    return [_crop_cluster(g, stats, cl) for cl in sorted(clusters, key=dist)[:max_blocks]]


def _crop_cluster(g, stats, keep):
    import cv2
    x1 = min(stats[i, 0] for i in keep)
    y1 = min(stats[i, 1] for i in keep)
    x2 = max(stats[i, 0] + stats[i, 2] for i in keep)
    y2 = max(stats[i, 1] + stats[i, 3] for i in keep)
    crop = g[max(0, y1 - 2):y2 + 2, max(0, x1 - 2):x2 + 2]
    crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.copyMakeBorder(crop, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)


def _default_field_reader(img) -> str:
    """ALLE Vorverarbeitungen laufen durch; die Ergebnisse kommen zusammen zurück (durch ' | '
    getrennt), danach nach ' # ' die Lesung des eng ausgeschnittenen Felds. Die Kontrolle ist
    zufrieden, wenn EINE davon die richtige Zahl zeigt. (Früher
    hat die erste Variante gewonnen, die irgendeine Zahl las - auch Müll vom Symbol im Feld.)"""
    import pytesseract

    from .ocr import preprocess
    wl = "-c tessedit_char_whitelist=0123456789.,"
    texts = []
    for scale, thr, psm in ((3, False, 7), (3, True, 7), (4, False, 6), (2, False, 7)):
        text = pytesseract.image_to_string(strip_lines(preprocess(img, scale, thr)),
                                           config=f"--psm {psm} {wl}").strip()
        if numbers_in(text) and text not in texts:
            texts.append(text)
    try:
        blocks = tight_crops(img)
    except Exception:
        blocks = []
    only_field = ""
    for block in blocks:        # Textblöcke nach Nähe zum Klickpunkt; Symbole liefern keine Zahl
        only_field = pytesseract.image_to_string(block, config=f"--psm 7 {wl}").strip()
        if numbers_in(only_field):
            break
        only_field = ""
    out = " | ".join(texts)
    return f"{out} # {only_field}"


def tight_part(text: str) -> str | None:
    """Der Teil der Feld-Lesung, der NUR das Feld zeigt (nach ' # '), sonst None."""
    return text.split(" # ", 1)[1] if " # " in text else None


def pure_ints(text: str) -> list[int]:
    """Nur ALLEINSTEHENDE ganze Zahlen im OCR-Text ('1', '10'), keine Teile von Preisen oder
    Müll wie '730,00'. Für das Mengenfeld."""
    out = []
    for part in re.split(r"[\s|]+", text):
        if re.fullmatch(r"\d{1,3}", part):
            out.append(int(part))
    return out


def _default_snap(rect):
    from .ocr import grab
    return grab(rect)


def _default_save(img, tag: str, log_dir) -> str:
    from .ocr import save_debug
    return str(save_debug(img, log_dir, tag))


class Drawer:
    def __init__(self, cfg: dict, guard, *, sleep: Callable[[float], None] = time.sleep,
                 snap: Callable | None = _default_snap,
                 field_reader: Callable | None = _default_field_reader,
                 post: Callable[[str], None] = lambda text: None,
                 clock: Callable[[], float] = time.monotonic,
                 save_img: Callable | None = None):
        self.cfg = cfg
        self.guard = guard
        self.sleep = sleep
        self.snap = snap                    # None = keine Bildkontrolle (nur für Tests)
        self.field_reader = field_reader
        self.post = post
        self.clock = clock
        journal = getattr(guard, "journal", None)
        self.log = journal.log_action if journal is not None else (lambda text: None)
        log_dir = (journal.out / "logs") if journal is not None else "logs"
        self.save_img = save_img or (lambda img, tag: _default_save(img, tag, log_dir))

    def has(self, direction: str) -> bool:
        return bool((self.cfg.get("ablaeufe") or {}).get(direction))

    # ------------------------------------------------------------ Kontrollen
    def _wait_for_change(self, rect, before, seconds: float) -> bool:
        return self._watch(rect, before, seconds)[0] != "keins"

    def _watch(self, rect, before, seconds: float) -> tuple[str, float, object]:
        """Wartet auf eine Bildveränderung. -> ('stark'|'schwach'|'keins', Anteil, letztes Bild)."""
        deadline = self.clock() + seconds
        best, img = 0.0, None
        while True:
            img = self.snap(rect)
            best = max(best, change_ratio(before, img))
            if best > STRONG:
                return "stark", best, img
            if self.clock() >= deadline:
                return ("schwach" if best > SOFT else "keins"), best, img
            self.sleep(0.2)

    def _wait_for_dialog(self, rect, before, field) -> str:
        """'stark' / 'schwach' = Dialog vermutlich offen, 'keins' = nichts hat sich verändert.
        Das Feld wird danach nur ZUR INFO gelesen - die OCR ist beim echten TradingView nicht
        immer verlässlich und darf das Tippen nicht blockieren."""
        wait = float(self.cfg.get("dialog_wartezeit", 3.0))
        level, ratio, after = self._watch(rect, before, wait)
        self.log(f"Dialog-Prüfung: Veränderung {ratio * 100:.1f} % -> {level}")
        if level == "keins":
            self._diag("dialog_vorher", before, "(Bild vor dem Doppelklick)")
            self._diag("dialog_nachher", after, f"(Bild danach, Veränderung {ratio * 100:.1f} %)")
            return level
        self.sleep(0.6)                     # Dialog fertig aufbauen lassen
        if level == "schwach":
            self.post("Dialog nur schwach erkannt - tippe und prüfe danach die Zahl.")
        if self.field_reader is not None:
            nums, text, img = self._read_field(*field)
            if nums:
                self.log(f"Dialog offen, Einstiegspreis-Feld zeigt {nums[0]:.2f}")
            else:
                self._diag("vorher_entry", img, text)
                self.post("Einstiegspreis-Feld nicht lesbar - tippe trotzdem.")
        return level

    def _read_field(self, x: int, y: int) -> tuple[list[float], str, object]:
        """(gelesene Zahlen, OCR-Text, Bild) eines Eingabefelds."""
        try:
            img = self.snap(_rect_around(x, y, FIELD))
            text = self.field_reader(img)
            return numbers_loose(text), text, img
        except Exception as exc:
            return [], f"Fehler: {exc!r}", None

    def _field_numbers(self, x: int, y: int) -> list[float]:
        return self._read_field(x, y)[0]

    def _diag(self, tag: str, img, text: str):
        """Diagnose: Bild + OCR-Text sichern, damit man später sieht, was der Bot sah."""
        where = "-"
        if img is not None:
            try:
                where = self.save_img(img, f"zeichnen_{tag}")
            except Exception as exc:
                where = f"(nicht gespeichert: {exc})"
        self.log(f"Diagnose {tag}: OCR las {text!r}, Bild {where}")

    def _field_ok(self, x: int, y: int, value: float) -> bool | None:
        """True = richtige Zahl im Feld, False = falsche Zahl, None = nicht lesbar."""
        if self.snap is None or self.field_reader is None:
            return None
        nums, text, img = self._read_field(x, y)
        if not nums:
            self._diag(f"unlesbar_{value:.2f}", img, text)
            return None
        ok = any(abs(n - value) < 0.01 for n in nums)
        if not ok:
            self._diag(f"falsch_{value:.2f}", img, text)
        return ok

    def _leave_field(self):
        """Tab: Feld verlassen -> TradingView übernimmt den Wert, und der blinkende Cursor
        stört das Nachlesen nicht (sonst wird aus '0|' gern eine '9')."""
        self.sleep(0.2)
        self.guard.press("tab", "Feld verlassen")
        self.sleep(0.4)

    def _close_dialogs(self, what: str):
        """Zweimal Esc: das erste verlässt ggf. ein Eingabefeld, das zweite schließt den
        Dialog. Geht nur, wenn TradingView vorne ist - sonst still überspringen."""
        in_front = getattr(self.guard, "tv_in_front", None)
        if in_front is not None and not in_front():
            self.log(f"Esc übersprungen ({what}): TradingView ist nicht vorne.")
            return
        for _ in range(2):
            try:
                self.guard.press("esc", what)
            except SafetyError:
                return
            self.sleep(0.4)

    def _abort(self, why: str):
        try:
            self._close_dialogs("Dialog schließen (Abbruch)")
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

        # Aufräumen: ein offener Dialog von vorher würde die Kontrolle täuschen
        self._close_dialogs("offene Dialoge schließen (Start)")
        dialog_open = False
        dialog_level = "stark"
        first_typed = True
        last = len(steps) - 1
        for i, st in enumerate(steps):
            x, y = st["punkt"]
            double = bool(st.get("doppel"))
            opens_dialog = dialog_rect is not None and i == first_type - 1
            closes_dialog = dialog_open and i == last and not st.get("tippe")
            if opens_dialog or closes_dialog:
                before = self.snap(dialog_rect)          # Bild VOR dem Öffnen/Schließen

            if i == create:
                self.guard.click_in("chart", ax, ay, f"{side}: Box an aktueller Kerze anlegen")
            elif i == dbl and create is not None:
                self.guard.click_in("chart", ax + dx, ay, f"{side}: Box öffnen (Doppelklick)",
                                    double=True)
            else:
                self.guard.click(x, y, f"{side} Schritt {i + 1}", double=double)

            if opens_dialog:
                self.post("Prüfe, ob der Einstellungsdialog offen ist ...")
                dialog_level = self._wait_for_dialog(dialog_rect, before,
                                                     steps[first_type]["punkt"])
                if dialog_level == "keins":
                    self._abort("Einstellungsdialog ist nicht aufgegangen - Box wurde nicht "
                                "getroffen. Nichts getippt. (Bilder: logs\\ocr_zeichnen_dialog_*.png)")
                dialog_open = True
                first_typed = False

            if closes_dialog:
                self.post("Prüfe, ob der Dialog zu ist ...")
                if not self._wait_for_change(dialog_rect, before, 3.0):
                    self._abort("OK wurde nicht getroffen - Dialog ist noch offen. "
                                "Box evtl. ohne die richtigen Werte.")

            if st.get("tippe"):
                text = format_price(values[st["tippe"]], dec)
                value = float(text.replace(",", "."))   # gerundeter Wert = was im Feld steht
                self.sleep(0.3)
                self.guard.type_text(text, st["tippe"])
                self._leave_field()
                ok = self._field_ok(x, y, value)
                if dialog_level == "schwach" and not first_typed and ok is not True:
                    self._abort("Dialog nur schwach erkannt und die Zahl steht nicht im Feld - "
                                "vermutlich nichts geöffnet. Abgebrochen.")
                first_typed = True
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
