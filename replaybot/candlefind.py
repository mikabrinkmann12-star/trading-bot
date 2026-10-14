"""Die neueste (rechteste) Kerze im Chart-Screenshot finden.

Kerzen sind bei dir blau (bullisch) oder schwarz (bärisch). Gesucht wird die rechteste
Spalte mit mindestens `min_run` zusammenhängenden Kerzenpixeln - so fallen die gepunktete
Kurslinie (1-2 px pro Spalte), der hellblaue Sitzungs-Hintergrund und graue Texte raus.
"""
from __future__ import annotations

Rect = tuple[int, int, int, int]   # left, top, width, height (Bildschirm)


def candle_mask(img):
    """img = BGR (numpy). True, wo ein Kerzenpixel ist (blau oder schwarz)."""
    import numpy as np
    b = img[..., 0].astype(np.int16)
    g = img[..., 1].astype(np.int16)
    r = img[..., 2].astype(np.int16)
    blue = (b > 180) & (r < 120) & (b - r > 100)
    black = (b < 70) & (g < 70) & (r < 70)
    return blue | black


def longest_runs(mask):
    """Längster senkrechter Lauf von True je Spalte."""
    import numpy as np
    run = np.zeros(mask.shape[1], dtype=np.int32)
    best = np.zeros(mask.shape[1], dtype=np.int32)
    for row in mask:
        run = (run + 1) * row
        np.maximum(best, run, out=best)
    return best


def find_last_candle_x(img, origin: tuple[int, int] = (0, 0), exclude: list[Rect] = (),
                       min_run: int = 5) -> int | None:
    """Bildschirm-x der Mitte der rechtesten Kerze, oder None."""
    import numpy as np
    mask = candle_mask(img)
    ox, oy = origin
    h, w = mask.shape
    for rect in exclude:
        if not rect:
            continue
        left, top, rw, rh = rect
        x1, y1 = max(0, left - ox), max(0, top - oy)
        x2, y2 = min(w, left - ox + rw), min(h, top - oy + rh)
        if x1 < x2 and y1 < y2:
            mask[y1:y2, x1:x2] = False
    runs = longest_runs(mask)
    cols = np.nonzero(runs >= min_run)[0]
    if len(cols) == 0:
        return None
    right = int(cols[-1])
    left = right
    while left - 1 >= 0 and runs[left - 1] >= 2:      # Körper links vom Docht dazunehmen
        left -= 1
    while right + 1 < w and runs[right + 1] >= 2:
        right += 1
    return ox + (left + right) // 2


def legend_zone(legend: Rect | None, chart: Rect) -> Rect | None:
    """Bereich mit Legende, Kauf-/Verkauf-Buttons und Indikator-Namen oben links."""
    if not legend:
        return None
    left, top, w, h = legend
    c_left, c_top, _cw, _ch = chart
    return (c_left, c_top, (left + w + 250) - c_left, (top + h + 60) - c_top)


def locate_current_candle(cfg: dict, current: tuple, *, grab, read_ohlc, move,
                          sleep, exclude: list[Rect] = (), max_shift: int = 60,
                          step: int = 2) -> tuple[int | None, str]:
    """x der aktuellen Kerze finden und per Legende gegenprüfen.

    current = (O, H, L, C) der aktuellen Kerze. move(x, y) bewegt die Maus (Hover),
    read_ohlc(img) liest die Legende. Rückgabe (x, '') oder (None, Grund)."""
    chart = cfg.get("chart")
    if not chart:
        return None, "Chart-Bereich nicht kalibriert"
    zones = [legend_zone(cfg.get("legende"), chart), *exclude]
    x0 = find_last_candle_x(grab(chart), origin=(chart[0], chart[1]), exclude=zones)
    if x0 is None:
        return None, "keine Kerze im Chart gefunden"
    y = chart[1] + chart[3] // 2
    right_edge = chart[0] + chart[2] - 1
    for dx in range(0, max_shift + 1, step):
        x = x0 + dx
        if x > right_edge:
            break
        move(x, y)
        sleep(0.15)
        vals, _text = read_ohlc(grab(cfg["legende"]))
        if vals and all(abs(a - b) < 0.01 for a, b in zip(vals, current)):
            return x, ""
    return None, "Legende zeigt beim Drüberfahren nicht die aktuelle Kerze"
