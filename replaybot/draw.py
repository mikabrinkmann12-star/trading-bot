"""Long-/Short-Position mit dem aufgenommenen Ablauf einzeichnen."""
from __future__ import annotations

import math
import time
from typing import Callable

from .safety import SafetyError


def format_price(value: float, decimal: str = ",", tick: float = 0.25) -> str:
    """30845.125 -> '30845,25' (auf Tick gerundet, Dezimalzeichen wie im TradingView-UI)."""
    rounded = math.floor(value / tick + 0.5) * tick
    return f"{rounded:.2f}".replace(".", decimal)


class Drawer:
    def __init__(self, cfg: dict, guard, *, sleep: Callable[[float], None] = time.sleep):
        self.cfg = cfg
        self.guard = guard
        self.sleep = sleep

    def has(self, direction: str) -> bool:
        return bool((self.cfg.get("ablaeufe") or {}).get(direction))

    def draw(self, direction: str, entry: float, stop: float, target: float):
        steps = (self.cfg.get("ablaeufe") or {}).get(direction)
        if not steps:
            raise SafetyError(f"Kein Ablauf für '{direction}' aufgenommen "
                              f"(python bot.py --aufnehmen {direction})")
        values = {"entry": entry, "stop": stop, "ziel": target}
        dec = self.cfg.get("dezimal", ",")
        pause = float(self.cfg.get("zeichnen_pause", 0.5))
        side = "Long" if direction == "long" else "Short"
        for i, st in enumerate(steps, 1):
            x, y = st["punkt"]
            self.guard.click(x, y, f"{side} Schritt {i}", double=bool(st.get("doppel")))
            if st.get("tippe"):
                self.sleep(0.2)
                self.guard.type_text(format_price(values[st["tippe"]], dec), st["tippe"])
            self.sleep(pause)
        self.guard.press("esc", "Auswahl aufheben")
        if self.cfg.get("naechste_kerze"):
            self.guard.move_to(*self.cfg["naechste_kerze"], "Maus aus dem Chart")
