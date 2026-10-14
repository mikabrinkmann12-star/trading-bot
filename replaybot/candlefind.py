"""Die neueste (rechteste) Kerze im Chart finden - mit Gegenprobe.

Kerzen sind bei dir blau (bullisch) oder schwarz (bärisch). Kandidaten sind Spalten mit
mindestens `min_run` zusammenhängenden Kerzenpixeln. Weil auch Zahlen (Preis-/Zeitachse)
schwarz sind, wird jeder Kandidat per Maus-Hover geprüft:
  - Maus auf den Kandidaten  -> Legende muss die AKTUELLE Kerze zeigen
  - Maus eine Kerze weiter links -> Legende muss die VORHERIGE Kerze zeigen
Erst wenn beides stimmt, ist es wirklich die letzte Kerze. (Über leeren Flächen oder der
Preisachse zeigt TradingView auch die letzte Kerze an - deshalb reicht die erste Probe allein
nicht.)
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


def _masked(img, origin, exclude):
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
    return mask


def candle_candidates(img, origin: tuple[int, int] = (0, 0), exclude: list[Rect] = (),
                      min_run: int = 5) -> list[int]:
    """Bildschirm-x aller Kerzen-Kandidaten, von RECHTS nach LINKS.

    Nur "starke" Spalten (>= min_run senkrecht zusammenhängende Kerzenpixel) zählen. Eine
    Kerze = zusammenhängende starke Spalten (Körper) bzw. nur der Docht bei flachem Körper -
    beides liefert die Kerzenmitte. Waagerechte Linien (Kurslinie, Level-Linien von
    Indikatoren) sind höchstens 2-3 px dick und verbinden deshalb keine Kerzen."""
    runs = longest_runs(_masked(img, origin, exclude))
    strong = runs >= min_run
    out: list[int] = []
    x = len(runs) - 1
    while x >= 0:
        if not strong[x]:
            x -= 1
            continue
        right = x
        while x - 1 >= 0 and strong[x - 1]:
            x -= 1
        out.append(origin[0] + (x + right) // 2)
        x -= 1
    return out


def find_last_candle_x(img, origin=(0, 0), exclude=(), min_run: int = 5) -> int | None:
    c = candle_candidates(img, origin, exclude, min_run)
    return c[0] if c else None


def bar_spacing(cands: list[int]) -> int | None:
    """Typischer Abstand zwischen Kerzen (Median der Abstände der rechten Kandidaten)."""
    gaps = sorted(a - b for a, b in zip(cands, cands[1:12]) if 2 <= a - b <= 80)
    return gaps[len(gaps) // 2] if gaps else None


def legend_zone(legend: Rect | None, chart: Rect) -> Rect | None:
    """Bereich mit Legende, Kauf-/Verkauf-Buttons und Indikator-Namen oben links."""
    if not legend:
        return None
    left, top, w, h = legend
    c_left, c_top, _cw, _ch = chart
    return (c_left, c_top, (left + w + 150) - c_left, (top + h + 60) - c_top)


def exclusion_zones(cfg: dict, extra: list[Rect] = ()) -> list[Rect]:
    """Alles, was schwarz/blau ist, aber keine Kerze: Legende, Preisachse (+ alles rechts
    davon), Zeitachse unten im Chart-Rechteck, Bot-Fenster."""
    chart = cfg["chart"]
    zones: list[Rect] = [legend_zone(cfg.get("legende"), chart)]
    c_left, c_top, c_w, c_h = chart
    axis = cfg.get("preisachse")
    if axis:
        a_left = axis[0] - 8
        zones.append((a_left, c_top - 50, c_left + c_w - a_left + 50, c_h + 100))
    zones.append((c_left, c_top + c_h - 30, c_w, 40))       # Zeitachsen-Zahlen
    zones.extend(r for r in extra if r)
    return [z for z in zones if z]


def _same(a, b) -> bool:
    return a is not None and b is not None and all(abs(x - y) < 0.01 for x, y in zip(a, b))


def locate_current_candle(cfg: dict, current: tuple, previous: tuple | None = None, *,
                          grab, read_ohlc, move, sleep, exclude: list[Rect] = (),
                          max_candidates: int = 12, hover_pause: float = 0.4
                          ) -> tuple[int | None, str]:
    """x der aktuellen Kerze finden und doppelt gegenprüfen. Rückgabe (x, '') oder (None, Grund)."""
    chart = cfg.get("chart")
    if not chart:
        return None, "Chart-Bereich nicht kalibriert"
    cands = candle_candidates(grab(chart), origin=(chart[0], chart[1]),
                              exclude=exclusion_zones(cfg, list(exclude)))
    if not cands:
        return None, "keine Kerze im Chart gefunden"
    spacing = bar_spacing(cands) or 8
    y = chart[1] + chart[3] // 2

    def legend_at(x):
        move(x, y)
        sleep(hover_pause)
        vals, _ = read_ohlc(grab(cfg["legende"]))
        return vals

    for i, x in enumerate(cands[:max_candidates]):
        if not _same(legend_at(x), current):
            continue
        # eine Kerze weiter links: Abstand zum nächsten Kandidaten und der typische Abstand
        # (falls die vorherige Kerze ein Mini-Doji war und nicht als Kandidat auftaucht)
        steps = []
        if i + 1 < len(cands) and 3 <= x - cands[i + 1] <= 80:
            steps.append(x - cands[i + 1])
        if spacing not in steps:
            steps.append(spacing)
        for step in steps:
            left_vals = legend_at(x - step)
            ok = (_same(left_vals, previous) if previous
                  else left_vals is not None and not _same(left_vals, current))
            if ok:
                return x, ""
    return None, ("Legende bestätigt keine Kerze (weder aktuelle Kerze an der Stelle noch "
                  "vorherige Kerze links daneben)")
