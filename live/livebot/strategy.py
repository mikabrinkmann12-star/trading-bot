"""Rechenkern der Strategie. Reine Logik: kein Bildschirm, keine Dateien.

Die Engine bekommt Kerze für Kerze (on_candle) und rechnet die 5 Schritte:
  1. Richtung: Open 9:30 gegen Close 9:40
  2. Swing-Hoch/-Tief (bestätigt, sobald die Kerze danach da ist)
  3. BOS auf 9:45 / 9:50 / 9:55 (Schlusskurs über/unter dem letzten Swing)
  4. Leg 9:30..BOS -> Entry, Stop, Risiko, Ziel
  5. Füllung bis 11:00, dann Stop/Ziel, spätestens Close 11:55
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import EPS, Candle, fmt, m2t, t2m

START = t2m("09:00")
DIR_OPEN = t2m("09:30")
DIR_CLOSE = t2m("09:40")
BOS_TIMES = (t2m("09:45"), t2m("09:50"), t2m("09:55"))
FILL_END = t2m("11:00")
EXIT_TIME = t2m("11:55")
STEP_MIN = 5
STOP_OFFSET = 4.0
MAX_RISK = 100.0
RR = 2.0

LONG, SHORT, NONE = "long", "short", "kein"

# Ergebnisse
TARGET = "Ziel"
STOP = "Stop"
TIME_EXIT = "Zeit-Exit"
NOT_FILLED = "nicht gefüllt"
NO_TRADE = "Kein Trade"
OPEN = "offen"
ERROR = "Fehler"

# Was auf einer Kerze im Management passiert ist
OUT_STOP, OUT_TARGET, OUT_ON, OUT_TIME = "stop", "ziel", "weiter", "zeit"

STEP_NAMES = {
    1: "Richtung",
    2: "Swing-Level",
    3: "BOS",
    4: "Leg / Entry",
    5: "Füllung / Trade",
}


@dataclass
class CandleReport:
    """Was die Engine auf genau dieser Kerze geprüft hat (für Prüfmodus/Anzeige)."""

    candle: Candle
    ignored: bool = False
    new_swing_high: Candle | None = None
    new_swing_low: Candle | None = None
    direction_decided: bool = False
    bos_checked: bool = False
    bos_level_candle: Candle | None = None  # Swing, gegen den geprüft wurde
    is_bos: bool = False
    setup_computed: bool = False
    fill_checked: bool = False
    filled: bool = False
    manage_checked: bool = False
    outcome: str | None = None
    closed: bool = False
    events: list[str] = field(default_factory=list)


class StrategyEngine:
    def __init__(self, date: str = "", max_risk: float = MAX_RISK):
        self.date = date
        self.max_risk = float(max_risk)       # Risiko darüber -> kein Trade (config "max_risiko")
        self.candles: list[Candle] = []
        self.by_time: dict[str, Candle] = {}
        self.swing_highs: list[Candle] = []
        self.swing_lows: list[Candle] = []
        self.direction: str | None = None
        self.bos_candle: Candle | None = None
        self.leg_low: Candle | None = None   # Kerze mit dem tiefsten Tief
        self.leg_high: Candle | None = None  # Kerze mit dem höchsten Hoch
        self.entry: float | None = None
        self.stop: float | None = None
        self.risk: float | None = None
        self.target: float | None = None
        self.fill_candle: Candle | None = None
        self.exit_candle: Candle | None = None
        self.exit_price: float | None = None
        self.result: str | None = None
        self.r: float | None = None
        self.done = False
        self.step = 1
        self.reason = "Warte auf Kerzen ab 9:00. Richtung = Close 9:40 gegen Open 9:30."
        self.events: list[str] = []
        self.last_report: CandleReport | None = None

    # ------------------------------------------------------------ Hilfen
    @property
    def swing_high(self) -> Candle | None:
        return self.swing_highs[-1] if self.swing_highs else None

    @property
    def swing_low(self) -> Candle | None:
        return self.swing_lows[-1] if self.swing_lows else None

    @property
    def is_trade(self) -> bool:
        return self.result in (TARGET, STOP, TIME_EXIT)

    def _finish(self, result: str, reason: str, rep: CandleReport,
                exit_price: float | None = None):
        self.result = result
        self.reason = reason
        self.done = True
        rep.closed = True
        if exit_price is not None:
            self.exit_candle = rep.candle
            self.exit_price = exit_price
            if self.direction == LONG:
                self.r = (exit_price - self.entry) / self.risk
            else:
                self.r = (self.entry - exit_price) / self.risk
        self._event(rep, reason)

    def _event(self, rep: CandleReport, text: str):
        msg = f"{rep.candle.time}: {text}"
        rep.events.append(msg)
        self.events.append(msg)

    # ------------------------------------------------------------ Kern
    def on_candle(self, c: Candle) -> CandleReport:
        rep = CandleReport(candle=c)
        self.last_report = rep

        if c.minute < START:
            rep.ignored = True
            self._event(rep, "vor 9:00 - wird ignoriert")
            return rep
        if self.candles and c.minute <= self.candles[-1].minute:
            raise ValueError(
                f"Kerze {c.time} kommt nicht nach {self.candles[-1].time} - Reihenfolge prüfen.")
        if not c.is_plausible():
            raise ValueError(f"Kerze {c.time} unplausibel (L <= O,C <= H verletzt): {c}")
        if self.candles and c.minute != self.candles[-1].minute + STEP_MIN:
            self._event(rep, f"WARNUNG Lücke: nach {self.candles[-1].time} fehlt mindestens "
                             f"{m2t(self.candles[-1].minute + STEP_MIN)}")

        self.candles.append(c)
        self.by_time[c.time] = c

        self._update_swings(rep)
        if self.done:
            return rep

        self._step_direction(rep)
        if not self.done:
            self._step_bos(rep)
        if not self.done and self.entry is not None and not rep.setup_computed:
            if self.fill_candle is None:
                self._step_fill(rep)
            else:
                self._step_manage(rep)
        return rep

    def _update_swings(self, rep: CandleReport):
        """Die vorletzte Kerze ist jetzt bestätigbar (Nachfolger ist da)."""
        if len(self.candles) < 3:
            return
        prev, mid, nxt = self.candles[-3], self.candles[-2], self.candles[-1]
        if not (prev.minute + STEP_MIN == mid.minute and mid.minute + STEP_MIN == nxt.minute):
            return  # Lücke -> nicht sicher prüfbar
        if mid.h > prev.h + EPS and mid.h > nxt.h + EPS:
            self.swing_highs.append(mid)
            rep.new_swing_high = mid
            self._event(rep, f"Swing-Hoch {fmt(mid.h)} ({mid.time}) bestätigt")
        if mid.l < prev.l - EPS and mid.l < nxt.l - EPS:
            self.swing_lows.append(mid)
            rep.new_swing_low = mid
            self._event(rep, f"Swing-Tief {fmt(mid.l)} ({mid.time}) bestätigt")

    def _step_direction(self, rep: CandleReport):
        c = rep.candle
        if self.direction is not None:
            return
        if c.minute < DIR_CLOSE:
            o930 = self.by_time.get("09:30")
            if o930:
                self.reason = (f"Open 9:30 = {fmt(o930.o)}. Richtung kommt mit dem "
                               f"Close der 9:40-Kerze.")
            else:
                self.reason = "Warte auf 9:30 und 9:40: Richtung = Close 9:40 gegen Open 9:30."
            return
        o930, c940 = self.by_time.get("09:30"), self.by_time.get("09:40")
        if o930 is None or c940 is None:
            self._finish(ERROR, "9:30- oder 9:40-Kerze fehlt - Richtung nicht bestimmbar. "
                                "Bot früher starten (vor 9:00 NY).", rep)
            return
        rep.direction_decided = True
        if c940.c > o930.o + EPS:
            self.direction = LONG
            self.step = 2
            self.reason = (f"Close 9:40 ({fmt(c940.c)}) > Open 9:30 ({fmt(o930.o)}) -> "
                           f"bullisch, nur Long. Jetzt BOS 9:45-9:55 abwarten.")
            self._event(rep, "Richtung LONG")
        elif c940.c < o930.o - EPS:
            self.direction = SHORT
            self.step = 2
            self.reason = (f"Close 9:40 ({fmt(c940.c)}) < Open 9:30 ({fmt(o930.o)}) -> "
                           f"bärisch, nur Short. Jetzt BOS 9:45-9:55 abwarten.")
            self._event(rep, "Richtung SHORT")
        else:
            self.direction = NONE
            self._finish(NO_TRADE, f"Close 9:40 = Open 9:30 ({fmt(o930.o)}) -> keine Richtung, "
                                   f"kein Trade heute.", rep)

    def _step_bos(self, rep: CandleReport):
        c = rep.candle
        if self.bos_candle is not None or self.direction not in (LONG, SHORT):
            return
        if c.minute not in BOS_TIMES:
            if c.minute > BOS_TIMES[-1]:
                self._finish(NO_TRADE, "BOS-Fenster 9:45-9:55 verpasst (Kerzen fehlen) - "
                                       "kein Trade.", rep)
            return
        self.step = 3
        rep.bos_checked = True
        if self.direction == LONG:
            lvl = self.swing_high
            rep.bos_level_candle = lvl
            ok = lvl is not None and c.c > lvl.h + EPS
            name, cmp_word = "Swing-Hoch", "über"
            lvl_val = lvl.h if lvl else None
        else:
            lvl = self.swing_low
            rep.bos_level_candle = lvl
            ok = lvl is not None and c.c < lvl.l - EPS
            name, cmp_word = "Swing-Tief", "unter"
            lvl_val = lvl.l if lvl else None

        if ok:
            rep.is_bos = True
            self.bos_candle = c
            self._event(rep, f"BOS: Close {fmt(c.c)} {cmp_word} {name} {fmt(lvl_val)} ({lvl.time})")
            self._compute_setup(rep)
            return

        if lvl is None:
            why = f"kein bestätigtes {name} - kein BOS möglich"
        else:
            why = f"Close {fmt(c.c)} nicht {cmp_word} {name} {fmt(lvl_val)} - noch kein BOS"
        if c.minute == BOS_TIMES[-1]:
            self._finish(NO_TRADE, f"{why}. Kein BOS bis 9:55 -> Kein Trade heute.", rep)
        else:
            self.reason = f"{c.time}: {why}."

    def _compute_setup(self, rep: CandleReport):
        self.step = 4
        rep.setup_computed = True
        leg = [k for k in self.candles if DIR_OPEN <= k.minute <= self.bos_candle.minute]
        self.leg_low = min(leg, key=lambda k: k.l)
        self.leg_high = max(leg, key=lambda k: k.h)
        lo, hi = self.leg_low.l, self.leg_high.h
        self.entry = (lo + hi) / 2
        if self.direction == LONG:
            self.stop = lo - STOP_OFFSET
        else:
            self.stop = hi + STOP_OFFSET
        self.risk = abs(self.entry - self.stop)
        sign = 1 if self.direction == LONG else -1
        self.target = self.entry + sign * RR * self.risk
        txt = (f"Leg {fmt(lo)}-{fmt(hi)} -> Entry {fmt(self.entry)}, Stop {fmt(self.stop)}, "
               f"Ziel {fmt(self.target)}, Risiko {fmt(self.risk)}")
        if self.risk > self.max_risk + EPS:
            self._finish(NO_TRADE, f"{txt}. Risiko {fmt(self.risk)} > {self.max_risk:.0f} Punkte "
                                   f"-> Kein Trade.", rep)
            return
        self.reason = (f"BOS {self.bos_candle.time}. {txt}. Limit wartet ab der nächsten "
                       f"Kerze bis 11:00.")
        self._event(rep, txt)

    def _step_fill(self, rep: CandleReport):
        c = rep.candle
        self.step = 5
        if c.minute > FILL_END:
            self._finish(NOT_FILLED, "Entry bis 11:00 nicht gefüllt.", rep)
            return
        rep.fill_checked = True
        long = self.direction == LONG
        hit = c.l <= self.entry + EPS if long else c.h >= self.entry - EPS
        if not hit:
            if c.minute == FILL_END:
                self._finish(NOT_FILLED, "Entry bis einschließlich 11:00 nicht gefüllt -> "
                                         "kein Trade.", rep)
            else:
                ext = f"Tief {fmt(c.l)}" if long else f"Hoch {fmt(c.h)}"
                self.reason = (f"{c.time}: {ext} hat Entry {fmt(self.entry)} nicht erreicht - "
                               f"Limit wartet weiter (bis 11:00).")
            return
        rep.filled = True
        self.fill_candle = c
        self._event(rep, f"Entry {fmt(self.entry)} gefüllt")
        stop_hit = c.l <= self.stop + EPS if long else c.h >= self.stop - EPS
        rep.manage_checked = True
        if stop_hit:
            rep.outcome = OUT_STOP
            self._finish(STOP, f"Füll-Kerze berührt auch den Stop {fmt(self.stop)} -> "
                               f"konservativ Stop, -1R.", rep, exit_price=self.stop)
            return
        rep.outcome = OUT_ON
        self.reason = (f"Gefüllt {c.time} bei {fmt(self.entry)}. Ab jetzt pro Kerze erst Stop "
                       f"{fmt(self.stop)}, dann Ziel {fmt(self.target)}; spätestens Close 11:55.")

    def _step_manage(self, rep: CandleReport):
        c = rep.candle
        self.step = 5
        rep.manage_checked = True
        long = self.direction == LONG
        stop_hit = c.l <= self.stop + EPS if long else c.h >= self.stop - EPS
        tgt_hit = c.h >= self.target - EPS if long else c.l <= self.target + EPS
        if stop_hit:
            rep.outcome = OUT_STOP
            self._finish(STOP, f"Stop {fmt(self.stop)} getroffen -> -1R.", rep,
                         exit_price=self.stop)
        elif tgt_hit:
            rep.outcome = OUT_TARGET
            self._finish(TARGET, f"Ziel {fmt(self.target)} erreicht -> +2R.", rep,
                         exit_price=self.target)
        elif c.minute >= EXIT_TIME:
            rep.outcome = OUT_TIME
            self._finish(TIME_EXIT, f"12:00 erreicht -> Zeit-Exit zum Close {fmt(c.c)}.", rep,
                         exit_price=c.c)
        else:
            rep.outcome = OUT_ON
            self.reason = (f"{c.time}: weder Stop {fmt(self.stop)} noch Ziel "
                           f"{fmt(self.target)} - Trade läuft.")

    def end_of_data(self):
        """Daten zu Ende, aber Tag nicht abgeschlossen."""
        if self.done:
            return
        if self.fill_candle is not None:
            self.result = OPEN
            self.reason = "Daten enden, Trade noch offen."
        elif self.entry is not None:
            self.result = OPEN
            self.reason = "Daten enden, Limit noch nicht gefüllt."
        else:
            self.result = OPEN
            self.reason = "Daten enden vor einer Entscheidung."

    # ------------------------------------------------------------ Anzeige
    def snapshot(self) -> dict:
        sh, sl = self.swing_high, self.swing_low
        last = self.candles[-1].time if self.candles else "-"
        return {
            "step": self.step,
            "step_name": STEP_NAMES[self.step],
            "values": [
                ("Datum", self.date or "-"),
                ("Kerze", last),
                ("Richtung", {LONG: "LONG (bullisch)", SHORT: "SHORT (bärisch)",
                              NONE: "keine"}.get(self.direction, "-")),
                ("Swing-Hoch", f"{fmt(sh.h)} ({sh.time})" if sh else "-"),
                ("Swing-Tief", f"{fmt(sl.l)} ({sl.time})" if sl else "-"),
                ("BOS", self.bos_candle.time if self.bos_candle else "-"),
                ("Leg", f"{fmt(self.leg_low.l)} - {fmt(self.leg_high.h)}"
                 if self.leg_low else "-"),
                ("Entry", fmt(self.entry)),
                ("Stop", fmt(self.stop)),
                ("Ziel", fmt(self.target)),
                ("Risiko", fmt(self.risk)),
                ("Gefüllt", self.fill_candle.time if self.fill_candle else "-"),
                ("Ergebnis", self.result or "-"),
                ("R", f"{self.r:+.2f}" if self.r is not None else "-"),
            ],
            "reason": self.reason,
        }

    def trade_row(self) -> dict:
        return {
            "Datum": self.date,
            "Richtung": self.direction or "-",
            "BOS-Zeit": self.bos_candle.time if self.bos_candle else "",
            "Entry": fmt(self.entry) if self.entry is not None else "",
            "Stop": fmt(self.stop) if self.stop is not None else "",
            "Ziel": fmt(self.target) if self.target is not None else "",
            "Risiko": fmt(self.risk) if self.risk is not None else "",
            "Ergebnis": self.result or "",
            "R": f"{self.r:.2f}" if self.r is not None else "",
        }
