"""Live-Trade-Verwaltung: Einstieg bei Entry-Berührung, TP/SL mitverfolgen, 12:00-Regel,
Schluss um 15:55 NY. Reine Logik - die Klicks kommen über ein 'actions'-Objekt rein.

Regeln (vom Nutzer festgelegt):
  - Nach dem BOS: berührt der Kurs bis 11:05:00 NY den Entry -> sofort Markt-Order mit
    Menge, TP (Ziel) und SL (Stop). Höchstens EINE Order pro Tag, nie ein zweiter Versuch.
  - TradingView führt TP/SL selbst aus; der Bot verfolgt nur mit, was passiert.
  - 12:00 NY, Position offen: im Plus -> Stop auf Break-even (Entry), weiterlaufen lassen;
    sonst (Minus oder genau Entry) -> Position schließen.
  - Nach Break-even spätestens 15:55 NY schließen.
"""
from __future__ import annotations

from typing import Callable

from .models import EPS, fmt
from .strategy import ERROR, LONG, NO_TRADE

WAIT, ARMED, IN_TRADE, DONE = "warten", "lauert", "im Trade", "fertig"

TARGET, STOP, BREAKEVEN = "Ziel", "Stop", "Break-even"
CLOSED_NOON, CLOSED_LATE = "Geschlossen 12:00", "Geschlossen 15:55"
NOT_FILLED, ORDER_ERROR = "nicht gefüllt", "Order-Fehler"
NO_PAPER = "Kein Paper-Konto"
SKIPPED = "ausgelassen"            # Entry berührt, Kurs aber schon hinter Stop/Ziel
TRADE_RESULTS = (TARGET, STOP, BREAKEVEN, CLOSED_NOON, CLOSED_LATE)

FILL_END = (11 * 60 + 5) * 60      # 11:05:00 NY (Kerze 11:00 einschließlich)
BE_TIME = 12 * 60 * 60             # 12:00:00 NY
CLOSE_TIME = (15 * 60 + 55) * 60   # 15:55:00 NY


def _hms(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


class TradeManager:
    def __init__(self, engine, actions, *, post: Callable[[str, str], None] = lambda t, l: None,
                 price_fn: Callable[[], float | None] | None = None):
        self.engine = engine
        self.actions = actions
        self.post = post
        self.price_fn = price_fn      # liest den Kurs JETZT (vor Break-even/Schließen)
        self.state = WAIT
        self.orders_sent = 0
        self.direction: str | None = None
        self.entry = self.stop = self.target = self.risk = None
        self.sl: float | None = None          # aktueller Stop (nach Break-even = Entry)
        self.breakeven = False
        self.fill_time: str | None = None
        self.fill_price: float | None = None
        self.exit_time: str | None = None
        self.exit_price: float | None = None
        self.result: str | None = None
        self.r: float | None = None
        self.reason = "Warte auf Setup (Richtung, BOS 9:45-9:55)."
        self._fill_bar: int | None = None
        self._fill_hl: tuple[float, float] | None = None
        self._confirm: dict[str, int] = {}     # Treffer müssen 2 Lesungen hintereinander zeigen

    def _confirmed(self, key: str, hit: bool, need: int = 2) -> bool:
        """Schutz vor einer einzelnen falsch gelesenen Zahl: erst bei 'need' Lesungen in Folge."""
        self._confirm[key] = self._confirm.get(key, 0) + 1 if hit else 0
        return self._confirm[key] >= need

    # ------------------------------------------------------------ Kerzen
    def on_bar_closed(self, minute: int | None = None, vals: tuple | None = None):
        """Nach jeder abgeschlossenen Kerze (Engine hat sie schon verarbeitet).
        minute/vals = die abgeschlossene Kerze (genau gelesen). Damit wird nachgeprüft, ob in
        den letzten Sekunden der Kerze Entry, Stop oder Ziel berührt wurden, die der Bot
        zwischen zwei Lesungen verpasst haben könnte."""
        e = self.engine
        if vals is not None and minute is not None and self.state in (ARMED, IN_TRADE):
            end = (minute + 5) * 60 - 0.5          # letzte halbe Sekunde dieser Kerze
            if self.state == ARMED and minute * 60 < FILL_END:
                self._check_fill(end, vals, need=1)
            elif self.state == IN_TRADE:
                self._manage(end, vals, need=1, time_rules=False)
        if self.state != WAIT:
            return
        if e.result in (NO_TRADE, ERROR):
            self._finish(e.result, None, None, e.reason)
            return
        if e.entry is not None and e.bos_candle is not None:
            self.direction, self.entry = e.direction, e.entry
            self.stop, self.target, self.risk = e.stop, e.target, e.risk
            self.sl = self.stop
            self.state = ARMED
            self.reason = (f"Setup steht: {self.direction.upper()} Entry {fmt(self.entry)}, "
                           f"Stop {fmt(self.stop)}, Ziel {fmt(self.target)}. Warte auf Berührung "
                           f"bis 11:05.")
            self.post(self.reason, "warn")
        elif e.done:
            self._finish(e.result or NO_TRADE, None, None, e.reason)

    # ------------------------------------------------------------ Ticks
    def on_tick(self, sec: float, vals: tuple):
        """Jede frische Lesung der entstehenden Kerze. sec = Sekunde des Tages (NY)."""
        if self.state == ARMED:
            self._check_fill(sec, vals)
        elif self.state == IN_TRADE:
            self._manage(sec, vals)

    def on_time(self, sec: float, price: float | None):
        """Zeitregeln auch ohne frische Lesung (11:05 ohne Füllung, 12:00, 15:55).
        price = letzter bekannter Kurs (frische Lesung oder Close der letzten Kerze)."""
        if self.state == ARMED and sec >= FILL_END:
            self._finish(NOT_FILLED, None, None, "Entry bis 11:05 nicht berührt - kein Trade.")
        elif self.state == IN_TRADE and price is not None:
            self._time_rules(sec, price)

    def _check_fill(self, sec: float, vals: tuple, need: int = 2):
        if sec >= FILL_END:
            self._finish(NOT_FILLED, None, None, "Entry bis 11:05 nicht berührt - kein Trade.")
            return
        _o, h, l, c = vals
        touched = l <= self.entry + EPS if self.direction == LONG else h >= self.entry - EPS
        if not self._confirmed("entry", touched, need):
            return
        # Höchstens EINE Order pro Tag - der Zähler wird VOR dem Klick erhöht
        if self.orders_sent:
            return
        long = self.direction == LONG
        past_stop = c <= self.stop + EPS if long else c >= self.stop - EPS
        past_target = c >= self.target - EPS if long else c <= self.target + EPS
        if past_stop or past_target:
            # Kurs ist (z.B. nach einem schnellen Sprung) schon hinter Stop oder Ziel:
            # TradingView würde die Order mit diesem TP/SL ablehnen bzw. sie wäre sofort > 1R
            # im Minus.
            self._finish(SKIPPED, None, None,
                         f"Entry berührt, aber der Kurs {fmt(c)} steht schon hinter dem "
                         f"{'Stop' if past_stop else 'Ziel'} - KEINE Order.")
            self.post(self.reason, "warn")
            return
        self.orders_sent += 1
        self.fill_time, self.fill_price = _hms(sec), c
        self._fill_bar, self._fill_hl = int(sec // 300), (h, l)
        side = "kaufen" if self.direction == LONG else "verkaufen"
        self.post(f"Entry {fmt(self.entry)} berührt (Kurs {fmt(c)}) - Markt {side} ...", "warn")
        try:
            self.actions.market(self.direction, self.stop, self.target)
        except Exception as exc:
            if "Kein Paper-Konto" in str(exc) or "nicht kalibriert" in str(exc):
                # Paper-Sperre: es wurde garantiert NICHTS geklickt
                self.fill_time = self.fill_price = None
                self._finish(NO_PAPER, None, None, f"{exc} Es wurde NICHTS geklickt.")
                self.post(self.reason, "error")
                return
            # Nie ein zweiter Versuch: unklar, ob die Order rausging
            self._finish(ORDER_ERROR, None, None,
                         f"Order-Ablauf fehlgeschlagen ({exc}). Bitte in TradingView prüfen, "
                         f"ob eine Position offen ist - der Bot kauft NICHT nochmal.")
            self.post(self.reason, "error")
            return
        self.state = IN_TRADE
        self.reason = (f"Im Trade seit {self.fill_time} (Kurs ca. {fmt(c)}). TP {fmt(self.target)}, "
                       f"SL {fmt(self.sl)}. 12:00: Plus -> Break-even, Minus -> schließen.")
        self.post(self.reason, "ok")
        try:
            self.actions.draw(self.direction, self.entry, self.stop, self.target)
        except Exception as exc:
            self.post(f"Einzeichnen fehlgeschlagen ({exc}) - Trade läuft trotzdem.", "error")

    def _extremes(self, sec: float, vals: tuple) -> tuple[float, float]:
        """Hoch/Tief SEIT der Füllung (in der Füll-Kerze zählen nur neue Extreme)."""
        _o, h, l, c = vals
        if int(sec // 300) == self._fill_bar:
            fh, fl = self._fill_hl
            return (h if h > fh else c), (l if l < fl else c)
        return h, l

    def _manage(self, sec: float, vals: tuple, need: int = 2, time_rules: bool = True):
        c = vals[3]
        hi, lo = self._extremes(sec, vals)
        long = self.direction == LONG
        stop_hit = self._confirmed("stop", lo <= self.sl + EPS if long else hi >= self.sl - EPS,
                                   need)
        tgt_hit = self._confirmed("ziel", hi >= self.target - EPS if long
                                  else lo <= self.target + EPS, need)
        if stop_hit:                                   # konservativ: Stop zuerst
            res = BREAKEVEN if self.breakeven else STOP
            self._finish(res, sec, self.sl,
                         "Break-even-Stop getroffen -> 0R." if self.breakeven
                         else f"Stop {fmt(self.sl)} getroffen -> -1R.")
            return
        if tgt_hit:
            self._finish(TARGET, sec, self.target, f"Ziel {fmt(self.target)} erreicht -> +2R.")
            return
        if time_rules:
            self._time_rules(sec, c)

    def _time_rules(self, sec: float, c: float):
        long = self.direction == LONG
        if not self.breakeven and sec >= BE_TIME:
            c = self._fresh_price(c)                     # direkt vor der Entscheidung neu lesen
            in_profit = c > self.entry + EPS if long else c < self.entry - EPS
            if in_profit:
                try:
                    self.actions.breakeven(self.entry)
                except Exception as exc:
                    self.post(f"Break-even fehlgeschlagen ({exc}) - bitte SL in TradingView "
                              f"selbst auf {fmt(self.entry)} setzen!", "error")
                self.breakeven, self.sl = True, self.entry
                self.reason = (f"12:00 im Plus -> Stop auf Break-even {fmt(self.entry)}. "
                               f"Läuft bis Ziel {fmt(self.target)} oder spätestens 15:55.")
                self.post(self.reason, "ok")
            else:
                self._close(sec, c, CLOSED_NOON, "12:00 nicht im Plus -> Position geschlossen.")
            return
        if self.breakeven and sec >= CLOSE_TIME:
            self._close(sec, c, CLOSED_LATE, "15:55 erreicht -> Position geschlossen.")

    def _fresh_price(self, fallback: float) -> float:
        """Aktueller Kurs unmittelbar vor der 12:00-Entscheidung (sonst der bekannte Kurs)."""
        if self.price_fn is None:
            return fallback
        try:
            p = self.price_fn()
        except Exception:
            p = None
        if p is None:
            return fallback
        if abs(p - fallback) > 1e-9:
            self.post(f"Kurs direkt vor der 12:00-Entscheidung: {fmt(p)} (vorher {fmt(fallback)}).",
                      "info")
        return p

    def _close(self, sec: float, price: float, result: str, reason: str):
        try:
            self.actions.close()
        except Exception as exc:
            reason += f" ACHTUNG: Schließen fehlgeschlagen ({exc}) - bitte selbst schließen!"
            self.post(reason, "error")
        self._finish(result, sec, price, reason)

    def _finish(self, result: str, sec: float | None, price: float | None, reason: str):
        self.state = DONE
        self.result, self.reason = result, reason
        if sec is not None:
            self.exit_time = _hms(sec)
        if price is not None and self.entry is not None and self.risk:
            self.exit_price = price
            if result == TARGET:
                self.r = 2.0
            elif result == STOP:
                self.r = -1.0
            elif result == BREAKEVEN:
                self.r = 0.0
            else:
                diff = price - self.entry if self.direction == LONG else self.entry - price
                self.r = diff / self.risk
        self.post(reason, "ok" if result in TRADE_RESULTS else "info")

    # ------------------------------------------------------------ Ausgabe
    @property
    def done(self) -> bool:
        return self.state == DONE

    def row(self, date: str) -> dict:
        e = self.engine
        return {
            "Datum": date,
            "Richtung": self.direction or e.direction or "-",
            "BOS-Zeit": e.bos_candle.time if e.bos_candle else "",
            "Entry": fmt(self.entry) if self.entry is not None else "",
            "Stop": fmt(self.stop) if self.stop is not None else "",
            "Ziel": fmt(self.target) if self.target is not None else "",
            "Risiko": fmt(self.risk) if self.risk is not None else "",
            "Füllzeit": self.fill_time or "",
            "Füllkurs": fmt(self.fill_price) if self.fill_price is not None else "",
            "Ausstieg": self.exit_time or "",
            "Ergebnis": self.result or "",
            "R": f"{self.r:.2f}" if self.r is not None else "",
        }

    def snapshot(self, snap: dict) -> dict:
        """Engine-Anzeige um den Live-Stand ergänzen (Füllung/Ergebnis kommen von hier)."""
        values = []
        for name, value in snap["values"]:
            if name == "Gefüllt":
                value = self.fill_time or "-"
            elif name == "Ergebnis":
                value = self.result or self.state
            elif name == "R":
                value = f"{self.r:+.2f}" if self.r is not None else "-"
            elif name == "Stop" and self.breakeven:
                value = f"{fmt(self.sl)} (BE)"
            values.append((name, value))
        out = dict(snap, values=values)
        if self.state != WAIT or self.done:
            out["reason"] = self.reason
            out["step"], out["step_name"] = 5, "Live-Trade"
        return out
