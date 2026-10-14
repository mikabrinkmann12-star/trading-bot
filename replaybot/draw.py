"""Long-/Short-Position mit dem aufgenommenen Ablauf einzeichnen."""
from __future__ import annotations

import math
import time
from typing import Callable

from .config import in_rect
from .safety import SafetyError

ANCHOR_DIST = 10   # px


def format_price(value: float, decimal: str = ",", tick: float = 0.25) -> str:
    """30845.125 -> '30845,25' (auf Tick gerundet, Dezimalzeichen wie im TradingView-UI)."""
    rounded = math.floor(value / tick + 0.5) * tick
    return f"{rounded:.2f}".replace(".", decimal)


def anchor_steps(steps: list[dict], chart) -> set[int]:
    """Welche aufgenommenen Schritte die Box anlegen/öffnen (Klick in den Chart + Doppelklick
    an derselben Stelle). Nur diese werden auf die aktuelle Kerze umgelenkt - Dialogfelder,
    die zufällig über dem Chart liegen, nicht."""
    if not chart:
        return set()
    first_type = next((i for i, s in enumerate(steps) if s.get("tippe")), len(steps))
    cands = [i for i in range(first_type) if in_rect(*steps[i]["punkt"], chart)]

    def near(i, j):
        (x1, y1), (x2, y2) = steps[i]["punkt"], steps[j]["punkt"]
        return abs(x1 - x2) <= ANCHOR_DIST and abs(y1 - y2) <= ANCHOR_DIST

    for i in cands:                     # bevorzugt: Klick, auf den ein Doppelklick folgt
        group = {i} | {j for j in range(i + 1, first_type) if near(i, j)}
        if any(steps[j].get("doppel") for j in group if j != i) or steps[i].get("doppel"):
            return group
    if cands:
        i = cands[0]
        return {i} | {j for j in range(i + 1, first_type) if near(i, j)}
    return set()


class Drawer:
    def __init__(self, cfg: dict, guard, *, sleep: Callable[[float], None] = time.sleep):
        self.cfg = cfg
        self.guard = guard
        self.sleep = sleep

    def has(self, direction: str) -> bool:
        return bool((self.cfg.get("ablaeufe") or {}).get(direction))

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
        pause = float(self.cfg.get("zeichnen_pause", 0.5))
        side = "Long" if direction == "long" else "Short"
        moved = anchor_steps(steps, self.cfg.get("chart")) if anchor else set()
        if moved:
            ax, ay = anchor
            if ay is None:                      # Höhe vom ersten Anker-Klick, für alle gleich
                ay = steps[min(moved)]["punkt"][1]
        for i, st in enumerate(steps, 1):
            x, y = st["punkt"]
            double = bool(st.get("doppel"))
            if i - 1 in moved:
                self.guard.click_in("chart", ax, ay,
                                    f"{side} Schritt {i} (aktuelle Kerze)", double=double)
            else:
                self.guard.click(x, y, f"{side} Schritt {i}", double=double)
            if st.get("tippe"):
                self.sleep(0.2)
                self.guard.type_text(format_price(values[st["tippe"]], dec), st["tippe"])
            self.sleep(pause)
        self.guard.press("esc", "Auswahl aufheben")
        if self.cfg.get("naechste_kerze"):
            self.guard.move_to(*self.cfg["naechste_kerze"], "Maus aus dem Chart")
