"""NY-Zeit aus der Windows-Uhr (und eine Zeitraffer-Uhr nur für Tests)."""
from __future__ import annotations

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
