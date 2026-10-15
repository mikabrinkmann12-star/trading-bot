"""Die echten Handels-Aktionen im Paper-Konto: Markt kaufen/verkaufen mit Menge, TP und SL,
Stop auf Break-even, Position schließen, Box einzeichnen.

Vor JEDER Order-Aktion: Paper-Sperre (Kontoname muss 'Paper' enthalten). Die Abläufe hat der
Nutzer vorher mit 'python live.py --aufnehmen ...' vorgemacht.
"""
from __future__ import annotations

from typing import Callable

from .strategy import LONG


class LiveActions:
    def __init__(self, cfg: dict, drawer, paper_lock, *, painter=None, enabled: bool = True,
                 post: Callable[[str, str], None] = lambda t, l: None,
                 around: Callable[[Callable[[], None]], None] | None = None):
        self.cfg = cfg
        self.drawer = drawer
        self.paper = paper_lock
        self.painter = painter
        self.enabled = enabled
        self.post = post
        # 'around' führt eine Aktion aus (z.B. mit ausgeblendetem Bot-Fenster)
        self.around = around or (lambda fn: fn())
        self.last_closed = None         # (O,H,L,C) der letzten abgeschlossenen Kerze
        self.prev_closed = None

    def _order_pause(self) -> float:
        return float(self.cfg.get("order_pause", 0.3))

    def _confirm_pause(self) -> float:
        """Nach dem Bestätigen kurz warten, bevor z.B. das X geklickt wird."""
        return float(self.cfg.get("bestaetigen_pause", 2.5))

    def _dec(self) -> str:
        """Das Bestellfenster nimmt nur den PUNKT (ein Komma wird verschluckt -> 100x zu groß)."""
        return self.cfg.get("dezimal_order", ".")

    def market(self, direction: str, stop: float, target: float):
        name = "kaufen" if direction == LONG else "verkaufen"
        if not self.enabled:
            self.post(f"(--ohne-orders) Hier würde der Bot jetzt Markt {name}.", "warn")
            return
        self.paper.check(f"Markt {name}")
        values = {"menge": int(self.cfg.get("menge", 1)), "stop": stop, "ziel": target}
        # Bestellfenster bleibt offen -> keine Schließ-Prüfung; TP und SL MÜSSEN sicher stimmen
        self.around(lambda: self.drawer.play(name, values, final_esc=False,
                                             pause=self._order_pause(),
                                             decimal=self._dec(), close_check="off",
                                             strict=("ziel", "stop"),
                                             confirm_pause=self._confirm_pause()))

    def breakeven(self, entry: float):
        if not self.enabled:
            self.post("(--ohne-orders) Hier würde der Bot den Stop auf Break-even setzen.", "warn")
            return
        self.paper.check("Break-even")
        self.around(lambda: self.drawer.play("breakeven", {"entry": entry}, final_esc=False,
                                             pause=self._order_pause(),
                                             decimal=self._dec(), close_check="warn",
                                             strict=("entry",),
                                             confirm_pause=self._confirm_pause()))

    def close(self):
        if not self.enabled:
            self.post("(--ohne-orders) Hier würde der Bot die Position schließen.", "warn")
            return
        self.paper.check("Position schließen")
        self.around(lambda: self.drawer.play("schliessen", {}, final_esc=False,
                                             pause=self._order_pause(),
                                             decimal=self._dec(), close_check="off"))

    def dismiss_messages(self):
        """Meldungen wie 'Order ausgefüllt' wegklicken (aufgenommener Ablauf 'meldungen').
        Keine Paper-Prüfung nötig: Es wird nichts gekauft, nur geklickt."""
        if not (self.cfg.get("ablaeufe") or {}).get("meldungen"):
            return
        self.drawer.play("meldungen", {}, final_esc=False, pause=0.3, close_check="off")

    def draw(self, direction: str, entry: float, stop: float, target: float):
        if self.painter is None or not (self.cfg.get("ablaeufe") or {}).get(direction):
            self.post(f"Einzeichnen '{direction}' nicht aufgenommen - übersprungen.", "warn")
            return
        self.around(lambda: self.painter(direction, entry, stop, target,
                                         last_closed=self.last_closed,
                                         prev_closed=self.prev_closed))
