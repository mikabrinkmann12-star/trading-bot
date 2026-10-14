"""Grundbausteine: Kerze, Zeit-Umrechnung, Zahlenformat."""
from __future__ import annotations

from dataclasses import dataclass

EPS = 1e-6


def t2m(t: str) -> int:
    """'09:30' oder '9:30' -> Minuten seit Mitternacht (570)."""
    hh, mm = t.strip().split(":")
    return int(hh) * 60 + int(mm)


def m2t(m: int) -> str:
    """570 -> '09:30'."""
    return f"{m // 60:02d}:{m % 60:02d}"


def fmt(x: float | None) -> str:
    """Zahl für die Anzeige: 2 Nachkommastellen, '-' wenn leer."""
    if x is None:
        return "-"
    return f"{x:.2f}"


@dataclass(frozen=True)
class Candle:
    """Eine 5-min-Kerze. time = Startzeit in NY ('09:30' = Kerze 9:30-9:35)."""

    time: str
    o: float
    h: float
    l: float
    c: float

    def __post_init__(self):
        # Zeit immer als 'HH:MM' speichern
        object.__setattr__(self, "time", m2t(t2m(self.time)))

    @property
    def minute(self) -> int:
        return t2m(self.time)

    def is_plausible(self) -> bool:
        """L <= O,C <= H"""
        return (self.l <= min(self.o, self.c) + EPS
                and max(self.o, self.c) <= self.h + EPS)

    def __str__(self) -> str:
        return (f"{self.time}  O {fmt(self.o)}  H {fmt(self.h)}  "
                f"L {fmt(self.l)}  C {fmt(self.c)}")
