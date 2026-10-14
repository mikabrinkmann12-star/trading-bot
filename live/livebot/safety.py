"""Sicherheitsregeln für jede Maus-/Tastaturaktion.

- Klicks nur auf kalibrierte Punkte (±15 px), Ziehen nur innerhalb kalibrierter Bereiche.
- Nur, wenn dort ein TradingView-Fenster liegt (Fenstertitel oder Programmname).
- Tippen nur, wenn TradingView im Vordergrund ist.
- Höchstens 200 Aktionen pro Lauf, jede Aktion wird geloggt.
- pyautogui-Failsafe: Maus in die linke obere Ecke = Abbruch.
"""
from __future__ import annotations

from typing import Callable

from .config import in_rect

MAX_CLICKS = 200
TOLERANCE = 15
MARKER = "tradingview"


class SafetyError(RuntimeError):
    pass


class PyAutoGuiBackend:
    """Die echten Maus-/Tastaturaktionen."""

    def __init__(self):
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self.pg = pyautogui

    def click(self, x: int, y: int, double: bool = False):
        if double:
            self.pg.doubleClick(x, y)
        else:
            self.pg.click(x, y)

    def drag(self, x1: int, y1: int, x2: int, y2: int):
        self.pg.moveTo(x1, y1)
        self.pg.mouseDown(button="left")
        self.pg.moveTo(x2, y2, duration=0.4)
        self.pg.mouseUp(button="left")

    def type_text(self, text: str):
        self.pg.hotkey("ctrl", "a")
        self.pg.write(text, interval=0.03)

    def press(self, key: str):
        self.pg.press(key)

    def move(self, x: int, y: int):
        self.pg.moveTo(x, y)


def _real_window(x: int, y: int) -> tuple[str, str]:
    from . import winutil
    return winutil.window_title_at(x, y), winutil.window_exe_at(x, y)


def _real_foreground() -> tuple[str, str]:
    from . import winutil
    return winutil.foreground_info()


def _is_tv(title: str, exe: str) -> bool:
    return MARKER in title.lower() or MARKER in exe.lower()


class Guard:
    def __init__(self, cfg: dict, journal, *, max_clicks: int = MAX_CLICKS,
                 backend=None,
                 window_fn: Callable[[int, int], tuple[str, str]] = _real_window,
                 foreground_fn: Callable[[], tuple[str, str]] = _real_foreground,
                 stop_event=None):
        self.stop_event = stop_event        # gesetzt = Nutzer hat 'Stop' gedrückt
        self.cfg = cfg
        self.journal = journal
        self.max_clicks = max_clicks
        self._backend = backend
        self.window_fn = window_fn
        self.foreground_fn = foreground_fn
        self.count = 0

    @property
    def backend(self):
        if self._backend is None:
            self._backend = PyAutoGuiBackend()
        return self._backend

    # ------------------------------------------------------------ Prüfungen
    def allowed_points(self) -> list[tuple[str, int, int]]:
        pts = []
        for name, steps in (self.cfg.get("ablaeufe") or {}).items():
            for i, st in enumerate(steps):
                pts.append((f"{name}[{i}]", *st["punkt"]))
        return pts

    def _budget(self) -> str:
        if self.stop_event is not None and self.stop_event.is_set():
            return "Bot wurde gestoppt"
        if self.count >= self.max_clicks:
            return f"Maximal {self.max_clicks} Aktionen pro Lauf erreicht"
        return ""

    def _window_at(self, x: int, y: int) -> str:
        title, exe = self.window_fn(x, y)
        if not _is_tv(title, exe):
            return (f"An ({x}, {y}) liegt kein TradingView-Fenster "
                    f"(Titel '{title}', Programm '{exe}')")
        return ""

    def check(self, x: int, y: int) -> str:
        """Grund, warum ein Klick auf (x, y) verboten ist, sonst ''."""
        if why := self._budget():
            return why
        if not any(abs(x - px) <= TOLERANCE and abs(y - py) <= TOLERANCE
                   for _, px, py in self.allowed_points()):
            return f"Punkt ({x}, {y}) ist nicht kalibriert"
        return self._window_at(x, y)

    def _near_axis(self, x: int, y: int, margin: int = 25) -> bool:
        axis = self.cfg.get("preisachse")
        if not axis:
            return False
        left, top, w, h = axis
        return left - margin <= x < left + w + margin and top - margin <= y < top + h + margin

    def _axis_rule(self, x: int, y: int, double: bool) -> str:
        """Ein Doppelklick auf die Preisachse stellt TradingView auf Auto - nie erlaubt."""
        if double and self._near_axis(x, y):
            return (f"Doppelklick bei ({x}, {y}) liegt an der Preisachse - das würde den Chart "
                    f"auf Auto stellen")
        return ""

    def _refuse(self, what: str, why: str):
        self.journal.log_action(f"VERWEIGERT {what}: {why}")
        raise SafetyError(why)

    def _done(self, what: str):
        self.count += 1
        self.journal.log_action(f"Aktion {self.count}/{self.max_clicks}: {what}")

    # ------------------------------------------------------------ Aktionen
    def click(self, x: int, y: int, what: str, double: bool = False):
        if why := (self._axis_rule(x, y, double) or self.check(x, y)):
            self._refuse(f"{what} ({x}, {y})", why)
        self._done(f"{'Doppelklick' if double else 'Klick'} {what} ({x}, {y})")
        self.backend.click(x, y, double)

    def click_in(self, region: str, x: int, y: int, what: str, double: bool = False):
        """Klick irgendwo INNERHALB eines kalibrierten Bereichs (z.B. auf die aktuelle Kerze)."""
        rect = self.cfg.get(region)
        why = self._budget()
        if not why and not rect:
            why = f"Bereich '{region}' ist nicht kalibriert"
        if not why and not in_rect(x, y, rect):
            why = f"Punkt ({x}, {y}) liegt nicht im Bereich '{region}'"
        if not why and self._near_axis(x, y, margin=8):
            why = f"Punkt ({x}, {y}) liegt auf der Preisachse"
        if not why:
            why = self._axis_rule(x, y, double)
        if not why:
            why = self._window_at(x, y)
        if why:
            self._refuse(f"{what} ({x}, {y})", why)
        self._done(f"{'Doppelklick' if double else 'Klick'} {what} ({x}, {y}) in '{region}'")
        self.backend.click(x, y, double)

    def click_next(self):
        if not self.cfg.get("naechste_kerze"):
            raise SafetyError("'Nächste Kerze' ist nicht kalibriert")
        x, y = self.cfg["naechste_kerze"]
        self.click(x, y, "Nächste Kerze")

    def drag(self, x1: int, y1: int, x2: int, y2: int, region: str, what: str):
        rect = self.cfg.get(region)
        why = self._budget()
        if not why and not rect:
            why = f"Bereich '{region}' ist nicht kalibriert"
        if not why and not (in_rect(x1, y1, rect) and in_rect(x2, y2, rect)):
            why = f"Ziehen ({x1},{y1})->({x2},{y2}) verlässt den Bereich '{region}'"
        if not why:
            why = self._window_at(x1, y1)
        if why:
            self._refuse(what, why)
        self._done(f"Ziehen {what} ({x1},{y1})->({x2},{y2})")
        self.backend.drag(x1, y1, x2, y2)

    def _foreground_ok(self, what: str):
        title, exe = self.foreground_fn()
        if not _is_tv(title, exe):
            self._refuse(what, f"TradingView ist nicht im Vordergrund (Titel '{title}', "
                               f"Programm '{exe}')")

    def type_text(self, text: str, what: str):
        if why := self._budget():
            self._refuse(what, why)
        self._foreground_ok(what)
        self._done(f"Tippe {what}: {text}")
        self.backend.type_text(text)

    def press(self, key: str, what: str):
        if why := self._budget():
            self._refuse(what, why)
        self._foreground_ok(what)
        self._done(f"Taste {key} ({what})")
        self.backend.press(key)

    def move_to(self, x: int, y: int, what: str):
        """Maus nur bewegen (kein Klick) - zählt nicht, wird aber geloggt."""
        self.journal.log_action(f"Maus nach ({x}, {y}): {what}")
        self.backend.move(x, y)
