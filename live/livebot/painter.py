"""Long-/Short-Box im LIVE-Chart einzeichnen: an der entstehenden Kerze (rechts neben der
zuletzt abgeschlossenen), Mittellinie auf dem Entry, danach passend zoomen."""
from __future__ import annotations

import time
from typing import Callable


def make_painter(cfg: dict, guard, post: Callable[[str, str], None],
                 exclude_fn: Callable[[], list] = lambda: []):
    from . import ocr
    from .candlefind import (_same, bar_spacing, candle_candidates, exclusion_zones,
                             locate_current_candle, same_open)
    from .chartnav import ChartNav
    from .draw import Drawer

    drawer = Drawer(cfg, guard, post=lambda t: post(t, "info"))
    nav = ChartNav(cfg, guard, post=lambda t: post(t, "info"))

    def paint(direction: str, entry: float, stop: float, target: float,
              last_closed: tuple | None = None, prev_closed: tuple | None = None,
              on_given_candle: bool = False):
        """last_closed = zuletzt abgeschlossene Kerze; die Box kommt eine Kerze rechts davon
        (entstehende Kerze). on_given_candle=True: genau auf die übergebene Kerze (Test)."""
        side = "Long" if direction == "long" else "Short"
        anchor = None
        if last_closed is not None and cfg.get("chart"):
            post("Suche die aktuelle Kerze im Chart ...", "info")
            x, why = locate_current_candle(
                cfg, last_closed, prev_closed, grab=ocr.grab, read_ohlc=ocr.read_ohlc,
                move=lambda mx, my: guard.move_to(mx, my, "Kerze prüfen (Hover)"),
                sleep=time.sleep, exclude=exclude_fn(),
                same=same_open if on_given_candle else _same)
            if x is None:
                post(f"Kerze nicht gefunden ({why}) - Box an der aufgenommenen Stelle.", "warn")
            else:
                chart = cfg["chart"]
                cands = candle_candidates(ocr.grab(chart), origin=(chart[0], chart[1]),
                                          exclude=exclusion_zones(cfg, exclude_fn()))
                shift = 0 if on_given_candle else (bar_spacing(cands) or 8)
                anchor = (x + shift, nav.price_to_y(entry))
                post(f"Box-Position: x={anchor[0]}, y={anchor[1]}.", "info")
        post(f"Zeichne {side}-Position (Entry {entry:.2f}) ...", "warn")
        drawer.draw(direction, entry, stop, target, anchor=anchor)
        if nav.ready():
            span = abs(target - stop)
            lo, hi = min(stop, target) - 0.1 * span, max(stop, target) + 0.1 * span
            if not nav.ensure_visible(lo, hi):
                post("Position evtl. nicht ganz sichtbar (Zoom hat nicht gereicht).", "warn")
        if cfg.get("parkplatz"):
            guard.move_to(*cfg["parkplatz"], "Maus aus dem Chart")

    return paint
