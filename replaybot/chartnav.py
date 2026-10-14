"""Chart so zoomen/verschieben, dass ein Preisbereich (Entry/Stop/Ziel) sichtbar ist.

Die Preisachse wird per OCR gelesen (Beschriftungen + ihre Höhe) -> lineare Zuordnung
Pixel-y <-> Preis. Danach:
  - Spanne zu groß  -> auf der Preisachse nach UNTEN ziehen (zoomt raus)
  - Bereich versetzt -> im Chart mit gedrückter linker Maustaste senkrecht ziehen
"""
from __future__ import annotations

import re
import time
from typing import Callable

from .legend import _NUM, normalize_number

Label = tuple[float, float]   # (y auf dem Bildschirm, Preis)


def fit_scale(labels: list[Label], px_tol: float = 3.0) -> tuple[float, float] | None:
    """Preis = a*y + b. Robust gegen einzelne falsch gelesene Beschriftungen."""
    pts = [(float(y), float(p)) for y, p in labels]
    if len(pts) < 2:
        return None
    best: tuple[int, float, list[Label]] | None = None
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (y1, p1), (y2, p2) = pts[i], pts[j]
            if abs(y2 - y1) < 5:
                continue
            a = (p2 - p1) / (y2 - y1)
            if a >= 0:                       # Preis muss nach oben steigen
                continue
            b = p1 - a * y1
            tol = abs(a) * px_tol
            inl = [(y, p) for y, p in pts if abs(a * y + b - p) <= tol]
            err = sum(abs(a * y + b - p) for y, p in inl)
            if best is None or len(inl) > best[0] or (len(inl) == best[0] and err < best[1]):
                best = (len(inl), err, inl)
    if best is None or best[0] < 2 or (len(pts) >= 3 and best[0] < 3):
        return None
    inl = best[2]
    n = len(inl)
    my = sum(y for y, _ in inl) / n
    mp = sum(p for _, p in inl) / n
    sxx = sum((y - my) ** 2 for y, _ in inl)
    a = sum((y - my) * (p - mp) for y, p in inl) / sxx
    return a, mp - a * my


def read_axis_labels(rect, scale: int = 3) -> list[Label]:
    """Beschriftungen der Preisachse per OCR (y in Bildschirmkoordinaten)."""
    import pytesseract

    from .ocr import grab, preprocess
    left, top, _w, _h = rect
    img = preprocess(grab(rect), scale=scale, threshold=True)
    data = pytesseract.image_to_data(
        img, config="--psm 11 -c tessedit_char_whitelist=0123456789.,",
        output_type=pytesseract.Output.DICT)
    out = []
    for text, t, h in zip(data["text"], data["top"], data["height"]):
        text = text.strip()
        if not re.fullmatch(_NUM, text):
            continue
        y = top + (t + h / 2 - 10) / scale     # 10 = Rand aus preprocess()
        out.append((y, normalize_number(text)))
    return out


class ChartNav:
    def __init__(self, cfg: dict, guard, *, labels_fn: Callable[[], list[Label]] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 post: Callable[[str], None] = lambda text: None):
        self.cfg = cfg
        self.guard = guard
        self.labels_fn = labels_fn or (lambda: read_axis_labels(cfg["preisachse"]))
        self.sleep = sleep
        self.post = post

    def scale(self) -> tuple[float, float] | None:
        try:
            return fit_scale(self.labels_fn())
        except Exception:
            return None

    def price_to_y(self, price: float) -> int | None:
        """Bildschirm-y eines Preises, begrenzt auf den Chart (5 % Rand)."""
        if not self.ready():
            return None
        sc = self.scale()
        if sc is None:
            return None
        a, b = sc
        _l, top, _w, h = self.cfg["chart"]
        y = (price - b) / a
        return int(max(top + 0.05 * h, min(top + 0.95 * h, y)))

    def ready(self) -> bool:
        return bool(self.cfg.get("preisachse") and self.cfg.get("chart"))

    def _visible(self, sc) -> tuple[float, float]:
        _l, top, _w, h = self.cfg["preisachse"]
        a, b = sc
        return a * (top + 0.95 * h) + b, a * (top + 0.05 * h) + b   # (unten, oben)

    def ensure_visible(self, lo: float, hi: float, rounds: int = 10,
                       fill_min: float = 0.45, fill_max: float = 0.8) -> bool:
        """Zoomen/verschieben, bis lo..hi sichtbar ist UND etwa die Hälfte bis 80 % der
        Höhe füllt. Nach jeder Aktion wird die Achse neu gelesen (Kontrolle)."""
        import math
        ax_l, ax_t, ax_w, ax_h = self.cfg["preisachse"]
        ch_l, ch_t, ch_w, ch_h = self.cfg["chart"]
        wait = float(self.cfg.get("zoom_pause", 1.0))   # > Doppelklick-Zeit von Windows
        prev = None
        force_zoom = False
        for _ in range(rounds):
            sc = self.scale()
            if sc is None:
                self.post("Preisachse nicht lesbar - Zoom übersprungen.")
                return False
            bottom, top = self._visible(sc)
            have, need = top - bottom, hi - lo
            fill = need / have if have > 0 else 9.0
            inside = lo >= bottom and hi <= top
            if inside and fill_min <= fill <= fill_max:
                return True
            if prev is not None and abs(prev[0] - sc[0]) < 1e-9 and abs(prev[1] - sc[1]) < 1e-6:
                force_zoom = True              # letzte Aktion hat nichts bewirkt (Auto-Skala?)
            prev = sc
            x_ax = ax_l + ax_w // 2
            y_mid = ax_t + ax_h // 2
            if fill > fill_max or fill < fill_min or force_zoom:
                goal = (fill_min + fill_max) / 2
                px = int(min(ax_h * 0.35, max(15, abs(math.log(max(fill, 0.01) / goal))
                                              * ax_h * 0.3)))
                zoom_out = fill > goal or (force_zoom and fill >= fill_min)
                dy = px if zoom_out else -px   # runter = raus, hoch = ran
                self.post("Zoome raus ..." if zoom_out else "Zoome ran ...")
                self.guard.drag(x_ax, y_mid - dy // 2, x_ax, y_mid + dy // 2, "preisachse",
                                "Zoom raus (Achse runter)" if zoom_out else "Zoom ran (Achse hoch)")
                force_zoom = False
            else:
                a, b = sc
                y_c = ((lo + hi) / 2 - b) / a          # wo die Mitte jetzt liegt
                dy = (ax_t + ax_h / 2) - y_c           # so weit muss der Inhalt wandern
                limit = ch_h * 0.4
                dy = max(-limit, min(limit, dy))
                x0 = int(ch_l + ch_w * 0.1)            # links, weg von der Box
                y0 = int(ch_t + ch_h / 2 - dy / 2)
                self.post("Verschiebe Chart ...")
                self.guard.drag(x0, y0, x0, int(y0 + dy), "chart", "Chart senkrecht verschieben")
            self.sleep(wait)
        sc = self.scale()
        if sc is None:
            return False
        bottom, top = self._visible(sc)
        return lo >= bottom and hi <= top
