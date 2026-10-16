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


LATEST_START = 9 * 3600 + 4 * 60      # bis hier sieht der Bot die 9:00-Kerze noch selbst
LATEST_BACKFILL = 9 * 3600 + 44 * 60  # bis hier: verpasste Kerzen ab 9:00 werden nachgelesen
                                      # (danach könnte schon ein BOS/Entry verpasst sein)


def german_time(now: datetime, hour: int, minute: int) -> str:
    """'hh:mm NY' an diesem Tag in deutscher Zeit (USA und Europa stellen die Uhr an
    verschiedenen Tagen um - meist 6 Stunden Unterschied, ein paar Tage im Jahr nur 5)."""
    try:
        from zoneinfo import ZoneInfo
        ny = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if ny.tzinfo is None:
            ny = ny.replace(tzinfo=ZoneInfo("America/New_York"))
        return f"das ist {ny.astimezone(ZoneInfo('Europe/Berlin')):%H:%M} deutscher Zeit"
    except Exception:
        return "meist 15:04 deutscher Zeit"


def start_problem(now: datetime) -> str | None:
    """Warum ein echter Live-Lauf jetzt keinen Sinn hat (oder None)."""
    sec = sec_of_day(now)
    if now.weekday() >= 5:
        return "Heute ist Wochenende (NY) - kein Handelstag."
    if sec > LATEST_BACKFILL:
        return (f"Es ist schon {now:%H:%M} NY. Der Bot braucht ALLE Kerzen ab 9:00 NY. Er kann "
                f"verpasste Kerzen nachlesen, aber nur bis 9:44 NY ({german_time(now, 9, 44)}) - "
                f"danach könnte der BOS oder die Entry-Berührung schon vorbei sein. Heute geht "
                f"nur noch:  python live.py --probelauf")
    return None


def missed_bars(now: datetime) -> int:
    """Wie viele fertige 5-min-Kerzen ab 9:00 NY schon vorbei sind (0 vor 9:05)."""
    bar = int(sec_of_day(now) // 300) * 5          # Startminute der entstehenden Kerze
    return max(0, (bar - 9 * 60) // 5)


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


TIME_SOURCES = ("https://www.tradingview.com", "https://www.google.com", "https://www.microsoft.com")


def internet_offset(sources=TIME_SOURCES, timeout: float = 5.0) -> float | None:
    """Wie viele Sekunden die PC-Uhr von der echten Zeit abweicht (echte - PC), gelesen aus dem
    'Date'-Kopf einer Webseite. None = nicht ermittelbar (kein Internet)."""
    import urllib.request
    from email.utils import parsedate_to_datetime
    for url in sources:
        try:
            req = urllib.request.Request(url, method="HEAD")
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                date = resp.headers.get("Date")
            t1 = time.time()
            if not date:
                continue
            real = parsedate_to_datetime(date).timestamp() + 0.5    # Date hat ganze Sekunden
            return real - (t0 + t1) / 2
        except Exception:
            continue
    return None


class OffsetClock:
    """NY-Zeit aus der PC-Uhr plus Korrektur (wenn die Windows-Uhr falsch geht)."""

    def __init__(self, offset: float, real=None):
        self.offset = offset
        self.real = real or now_ny

    def __call__(self) -> datetime:
        return self.real() + timedelta(seconds=self.offset)
