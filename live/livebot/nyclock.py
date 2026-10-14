"""NY-Zeit aus der Windows-Uhr (und eine Zeitraffer-Uhr nur für Tests)."""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:                     # Windows ohne 'tzdata'-Paket
    NY = None


def now_ny() -> datetime:
    if NY is None:
        raise RuntimeError("Zeitzone fehlt - bitte 'pip install tzdata' ausführen.")
    return datetime.now(NY)


def sec_of_day(dt: datetime) -> float:
    return dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1e6


class SimClock:
    """Nur zum Testen: startet bei 'start' (HH:MM) und läuft 'factor'-mal so schnell."""

    def __init__(self, start: str, factor: float = 1.0, epoch: float | None = None):
        hh, mm = (int(x) for x in start.split(":"))
        base = datetime(2026, 1, 5, hh, mm)
        self.base, self.factor = base, factor
        self.epoch = epoch if epoch is not None else time.time()   # gemeinsamer Startpunkt

    def __call__(self) -> datetime:
        return self.base + timedelta(seconds=(time.time() - self.epoch) * self.factor)


LATEST_START = 9 * 3600 + 4 * 60      # danach fehlt die 9:00-Kerze -> Strategie nicht rechenbar


def start_problem(now: datetime) -> str | None:
    """Warum ein echter Live-Lauf jetzt keinen Sinn hat (oder None)."""
    sec = sec_of_day(now)
    if now.weekday() >= 5:
        return "Heute ist Wochenende (NY) - kein Handelstag."
    if sec > LATEST_START:
        return (f"Es ist schon {now:%H:%M} NY. Der Bot braucht ALLE Kerzen ab 9:00 NY und muss "
                f"deshalb vor 9:04 NY laufen (normalerweise 15:04 deutscher Zeit; vom 25.10. "
                f"bis 31.10. schon 14:04). Heute geht nur noch:  python live.py --probelauf")
    return None


def probe_shift(real_sec: float, start: int = 9 * 3600) -> int:
    """Probelauf: um wie viele Sekunden die Uhr zurückgestellt wird - immer ganze 5 Minuten
    (dann passen die Kerzengrenzen zum Chart), so dass 'jetzt' 0-5 min vor 9:00 liegt."""
    return max(0, math.ceil((real_sec - start + 1) / 300)) * 300


class ShiftClock:
    """Probelauf: echte NY-Zeit minus 'shift' Sekunden. Die Kerzen im Chart sind echt, der
    Bot tut nur so, als wäre es kurz vor 9:00."""

    def __init__(self, shift: float, real=now_ny):
        self.shift, self.real = shift, real

    def __call__(self) -> datetime:
        return self.real() - timedelta(seconds=self.shift)
