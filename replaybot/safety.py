"""Sicherheitsregeln für jeden Klick.

- Nur auf kalibrierte Punkte (±15 px).
- Nur, wenn dort ein TradingView-Fenster liegt (Fenstertitel oder Programmname).
- Höchstens 200 Klicks pro Lauf.
- Jede Aktion wird geloggt. pyautogui-Failsafe: Maus in die linke obere Ecke = Abbruch.
"""
from __future__ import annotations

from typing import Callable

MAX_CLICKS = 200
TOLERANCE = 15
MARKER = "tradingview"


class SafetyError(RuntimeError):
    pass


def _real_click(x: int, y: int):
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.click(x, y)


def _real_window(x: int, y: int) -> tuple[str, str]:
    from . import winutil
    return winutil.window_title_at(x, y), winutil.window_exe_at(x, y)


class Guard:
    def __init__(self, cfg: dict, journal, *, max_clicks: int = MAX_CLICKS,
                 click_fn: Callable[[int, int], None] = _real_click,
                 window_fn: Callable[[int, int], tuple[str, str]] = _real_window):
        self.cfg = cfg
        self.journal = journal
        self.max_clicks = max_clicks
        self.click_fn = click_fn
        self.window_fn = window_fn
        self.count = 0

    def allowed_points(self) -> list[tuple[str, int, int]]:
        pts = []
        if self.cfg.get("naechste_kerze"):
            x, y = self.cfg["naechste_kerze"]
            pts.append(("naechste_kerze", x, y))
        for name, steps in (self.cfg.get("ablaeufe") or {}).items():
            for i, st in enumerate(steps):
                pts.append((f"{name}[{i}]", *st["punkt"]))
        return pts

    def check(self, x: int, y: int) -> str:
        """Gibt den Grund zurück, falls der Klick verboten ist, sonst ''."""
        if self.count >= self.max_clicks:
            return f"Maximal {self.max_clicks} Klicks pro Lauf erreicht"
        if not any(abs(x - px) <= TOLERANCE and abs(y - py) <= TOLERANCE
                   for _, px, py in self.allowed_points()):
            return f"Punkt ({x}, {y}) ist nicht kalibriert"
        title, exe = self.window_fn(x, y)
        if MARKER not in title.lower() and MARKER not in exe.lower():
            return (f"An ({x}, {y}) liegt kein TradingView-Fenster "
                    f"(Titel '{title}', Programm '{exe}')")
        return ""

    def click(self, x: int, y: int, what: str):
        why = self.check(x, y)
        if why:
            self.journal.log_action(f"KLICK VERWEIGERT {what} ({x}, {y}): {why}")
            raise SafetyError(why)
        self.count += 1
        self.journal.log_action(f"Klick {self.count}/{self.max_clicks}: {what} ({x}, {y})")
        self.click_fn(x, y)

    def click_next(self):
        if not self.cfg.get("naechste_kerze"):
            raise SafetyError("'Nächste Kerze' ist nicht kalibriert")
        x, y = self.cfg["naechste_kerze"]
        self.click(x, y, "Nächste Kerze")
