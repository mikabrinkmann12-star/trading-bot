"""Live-Kerzen: aus der ständig lesenden Legende (entstehende Kerze) die abgeschlossenen
5-min-Kerzen gewinnen.

Die Legende zeigt im Live-Chart die Kerze, die GERADE entsteht. Der Bot liest sie etwa jede
halbe Sekunde. Wechselt die Uhr in einen neuen 5-min-Abschnitt, ist die vorige Kerze fertig:
ihr letzter gelesener Stand ist eine gute Näherung (danach wird sie per Hover genau gelesen).
"""
from __future__ import annotations

from .nyclock import sec_of_day


class LiveFeed:
    def __init__(self, settle: float = 1.5):
        self.settle = settle            # s nach Kerzenwechsel, in denen die Legende noch alt sein kann
        self.cur: int | None = None     # Startminute der entstehenden Kerze
        self.cur_vals: tuple | None = None
        self.last_closed: tuple | None = None

    def on_reading(self, now, vals) -> tuple[list[tuple[int, tuple]], tuple | None]:
        """-> (abgeschlossene Kerzen [(Startminute, O/H/L/C-Näherung)], frische Werte der
        entstehenden Kerze oder None, wenn die Lesung noch alt/ungültig sein könnte)."""
        sec = sec_of_day(now)
        bar = int(sec // 300) * 5
        closed = []
        if self.cur is None:
            self.cur = bar
        elif bar > self.cur:
            if self.cur_vals is not None:
                closed.append((self.cur, self.cur_vals))
                self.last_closed = self.cur_vals
            self.cur, self.cur_vals = bar, None
        fresh = (vals is not None and sec - bar * 60 >= self.settle
                 and vals != self.last_closed)
        if fresh:
            self.cur_vals = vals
        return closed, (vals if fresh else None)


def match_closed(vals, approx, tol: float = 25.0) -> bool:
    """Passt eine Hover-Lesung zur genäherten abgeschlossenen Kerze?
    Open ändert sich während der Kerze nicht -> muss exakt passen; H/L dürfen nur weiter
    sein (letzte Ticks), C darf bei schnellem Markt etwas abweichen."""
    if vals is None or approx is None:
        return False
    o, h, l, c = vals
    ao, ah, al, ac = approx
    return (abs(o - ao) < 0.01 and h >= ah - 0.01 and l <= al + 0.01
            and h - ah <= tol and al - l <= tol and abs(c - ac) <= tol)


def read_closed_exact(cfg: dict, approx: tuple, *, grab, read_ohlc, move, sleep,
                      exclude=(), max_candidates: int = 6, hover_pause: float = 0.4):
    """Abgeschlossene Kerze per Hover genau lesen. -> (O,H,L,C) oder None."""
    from .candlefind import candle_candidates, exclusion_zones
    chart = cfg.get("chart")
    if not chart:
        return None
    cands = candle_candidates(grab(chart), origin=(chart[0], chart[1]),
                              exclude=exclusion_zones(cfg, list(exclude)))
    y = chart[1] + chart[3] // 2
    for x in cands[:max_candidates]:
        move(x, y)
        sleep(hover_pause)
        vals, _ = read_ohlc(grab(cfg["legende"]))
        if match_closed(vals, approx):
            return vals
    return None
