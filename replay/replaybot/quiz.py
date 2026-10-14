"""Prüfmodus: Vor jedem Schritt tippst du deine Antwort, der Bot vergleicht mit seiner
Rechnung und erklärt dir direkt, wo du falsch lagst.

Die Ein-/Ausgabe läuft über zwei Callbacks:
  ask(frage) -> str   (Konsole: input(), ab Phase 2: Eingabefeld im Fenster)
  say(text)           (Konsole: print(), ab Phase 2: Fenster)
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Callable

from .models import EPS, Candle, fmt, m2t
from .strategy import (LONG, MAX_RISK, OUT_ON, OUT_TIME, RR, SHORT, START, STOP,
                       STOP_OFFSET, TARGET, CandleReport, StrategyEngine)

TOL = 0.01

QUOTES = [
    "Discipline is choosing between what you want now and what you want most.",
    "You didn't come this far to only come this far.",
    "Stay hard.",
    "Who's gonna carry the boats?",
    "Hard work beats talent when talent doesn't work hard.",
    "Motivation gets you going, discipline keeps you growing.",
    "Your future self is watching you right now through memories.",
    "Do it tired. Do it scared. Just do it.",
    "Comfort is the enemy of progress.",
    "Nobody is coming to save you.",
    "The pain of discipline weighs ounces, the pain of regret weighs tons.",
    "Lock in.",
]

SKIP_WORDS = {"", "?", "kb", "kp", "idk", "skip", "weiß nicht", "weiss nicht", "keine ahnung"}
QUIT_WORDS = {"q", "quit", "exit", "ende", "stopp"}

CHOICE_ALIASES = {
    "long": {"long", "l", "bull", "bullisch", "kauf", "buy"},
    "short": {"short", "s", "bär", "bär.", "bärisch", "baerisch", "bear", "verkauf", "sell"},
    "kein": {"kein", "keine", "k", "none", "neutral", "gleich", "-", "0"},
    "j": {"j", "ja", "y", "yes"},
    "n": {"n", "nein", "no"},
    "stop": {"stop", "sl", "stopp"},
    "ziel": {"ziel", "tp", "target"},
    "weiter": {"weiter", "w", "läuft", "laeuft", "nichts"},
    "zeit": {"zeit", "zeit-exit", "zeitexit", "time", "12", "12:00"},
}
NONE_WORDS = {"keins", "kein", "keine", "none", "-", "nichts"}


class QuizAbort(Exception):
    """Nutzer hat 'q' getippt."""


def parse_number(text: str, thousands_dot: bool = True) -> float:
    """'30.845,00' / '30845,0' / '30845.0' / '30.845' -> 30845.0"""
    s = text.strip().replace(" ", "").replace("+", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif thousands_dot and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


def _is(a: float | None, b: float | None, tol: float = TOL) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


@dataclass
class Question:
    key: str
    text: str
    kind: str                      # "num" oder "choice"
    expected: object               # float, None (= 'keins') oder Auswahl-String
    explain: Callable[[object], str]
    choices: tuple[str, ...] = ()
    thousands_dot: bool = True

    def expected_str(self) -> str:
        if self.kind == "num":
            return "keins" if self.expected is None else fmt(self.expected)
        return str(self.expected)


@dataclass
class Mistake:
    candle: str
    question: str
    answer: str
    expected: str


@dataclass
class Quiz:
    ask: Callable[[str], str]
    say: Callable[[str], None]
    journal: object | None = None
    date: str = ""
    total: int = 0
    correct: int = 0
    mistakes: list[Mistake] = field(default_factory=list)

    def run(self, engine: StrategyEngine, rep: CandleReport):
        for q in questions_for(engine, rep):
            self._ask_one(q, rep.candle.time)

    def _ask_one(self, q: Question, ctime: str):
        while True:
            raw = self.ask(q.text)
            if raw is None:
                raise QuizAbort()
            raw = raw.strip()
            low = raw.lower()
            if low in QUIT_WORDS:
                raise QuizAbort()
            if low in SKIP_WORDS:
                self.say(f'"{random.choice(QUOTES)}"')
                self.say(f"Lösung: {q.expected_str()}. {q.explain(None)}")
                self._record(q, ctime, raw or "(leer)", False)
                return
            try:
                val = self._parse(q, low)
            except ValueError:
                hint = "/".join(q.choices) if q.kind == "choice" else "eine Zahl oder 'keins'"
                self.say(f"Versteh ich nicht. Erwartet: {hint}")
                continue
            ok = self._check(q, val)
            if ok:
                self.say("Richtig.")
            else:
                self.say(f"Falsch. Richtig ist {q.expected_str()}. {q.explain(val)}")
            self._record(q, ctime, raw, ok)
            return

    def _parse(self, q: Question, low: str):
        if q.kind == "choice":
            for key in q.choices:
                if low in CHOICE_ALIASES.get(key, {key}):
                    return key
            raise ValueError
        if low in NONE_WORDS:
            return None
        return parse_number(low, q.thousands_dot)

    @staticmethod
    def _check(q: Question, val) -> bool:
        if q.kind == "choice":
            return val == q.expected
        if q.expected is None or val is None:
            return q.expected is None and val is None
        return _is(val, q.expected)

    def _record(self, q: Question, ctime: str, answer: str, ok: bool):
        self.total += 1
        if ok:
            self.correct += 1
        else:
            self.mistakes.append(Mistake(ctime, q.key, answer, q.expected_str()))
        if self.journal is not None:
            self.journal.log_quiz(self.date, ctime, q.key, answer, q.expected_str(), ok)

    def summary(self) -> str:
        if self.total == 0:
            return "Prüfmodus: keine Fragen gestellt."
        pct = 100 * self.correct / self.total
        lines = [f"Prüfmodus: {self.correct}/{self.total} richtig ({pct:.0f} %)."]
        for m in self.mistakes:
            lines.append(f"  {m.candle} {m.question}: du '{m.answer}', richtig '{m.expected}'")
        if pct < 100:
            lines.append("Die Fehler oben nochmal durchrechnen, bis sie sitzen.")
        return "\n".join(lines)


# ====================================================================== Fragen

def questions_for(e: StrategyEngine, rep: CandleReport) -> list[Question]:
    if rep.ignored:
        return []
    qs: list[Question] = []
    c = rep.candle
    long = e.direction == LONG

    if rep.direction_decided:
        qs.append(Question(
            "Richtung", "Schritt 1 - Richtung? (long/short/kein)", "choice", e.direction,
            lambda a: _explain_direction(e), choices=("long", "short", "kein")))

    if rep.bos_checked:
        lvl = rep.bos_level_candle
        name = "Swing-Hoch" if long else "Swing-Tief"
        qs.append(Question(
            name, f"Schritt 2 - Letztes BESTÄTIGTES {name}? (Zahl oder 'keins')", "num",
            None if lvl is None else (lvl.h if long else lvl.l),
            lambda a: _explain_swing(e, rep, a)))
        qs.append(Question(
            "BOS", f"Schritt 3 - BOS auf der {c.time}-Kerze? (j/n)", "choice",
            "j" if rep.is_bos else "n",
            lambda a: _explain_bos(e, rep), choices=("j", "n")))

    if rep.setup_computed:
        lo, hi = e.leg_low, e.leg_high
        qs += [
            Question("Leg-Tief", "Schritt 4 - Leg-Tief?", "num", lo.l,
                     lambda a: _explain_leg(e, a, "l")),
            Question("Leg-Hoch", "Schritt 4 - Leg-Hoch?", "num", hi.h,
                     lambda a: _explain_leg(e, a, "h")),
            Question("Entry", "Schritt 4 - Entry?", "num", e.entry,
                     lambda a: _explain_entry(e, a)),
            Question("Stop", "Schritt 4 - Stop?", "num", e.stop,
                     lambda a: _explain_stop(e, a)),
            Question("Risiko", "Schritt 4 - Risiko (Punkte)?", "num", e.risk,
                     lambda a: _explain_risk(e, a)),
            Question("Ziel", "Schritt 4 - Ziel?", "num", e.target,
                     lambda a: _explain_target(e, a)),
            Question("Trade erlaubt", f"Schritt 4 - Trade erlaubt (Risiko <= {MAX_RISK:.0f})? (j/n)",
                     "choice", "j" if e.risk <= MAX_RISK + EPS else "n",
                     lambda a: _explain_valid(e), choices=("j", "n")),
        ]

    if rep.fill_checked:
        side = "Long" if long else "Short"
        qs.append(Question(
            "Gefüllt", f"Schritt 5 - Wird das {side}-Limit {fmt(e.entry)} auf {c.time} gefüllt? (j/n)",
            "choice", "j" if rep.filled else "n",
            lambda a: _explain_fill(e, rep), choices=("j", "n")))

    if rep.manage_checked:
        if rep.filled:
            text = f"Schritt 5 - Füll-Kerze {c.time}: was passiert? (stop/ziel/weiter)"
            choices = ("stop", "ziel", "weiter")
        else:
            text = f"Schritt 5 - Kerze {c.time}: was passiert? (stop/ziel/weiter/zeit)"
            choices = ("stop", "ziel", "weiter", "zeit")
        qs.append(Question("Management", text, "choice", rep.outcome,
                           lambda a: _explain_manage(e, rep), choices=choices))

    if rep.closed and e.is_trade:
        qs.append(Question("Ergebnis R", "Schritt 5 - Ergebnis in R?", "num", e.r,
                           lambda a: _explain_r(e), thousands_dot=False))
    return qs


# ================================================================ Erklärungen

def _cmp(a: float, b: float) -> str:
    if a > b + EPS:
        return ">"
    if a < b - EPS:
        return "<"
    return "="


def _explain_direction(e: StrategyEngine) -> str:
    o, c = e.by_time["09:30"].o, e.by_time["09:40"].c
    word = {LONG: "bullisch -> nur Long", SHORT: "bärisch -> nur Short"}.get(
        e.direction, "gleich -> kein Trade")
    return (f"Close 9:40 ({fmt(c)}) {_cmp(c, o)} Open 9:30 ({fmt(o)}) -> {word}. "
            f"Typische Fehler: Close 9:30 statt Open 9:30, oder 9:35 statt 9:40.")


def _neighbors(e: StrategyEngine, k: Candle) -> tuple[Candle | None, Candle | None]:
    prev = e.by_time.get(m2t(k.minute - 5)) if k.minute - 5 >= START else None
    return prev, e.by_time.get(m2t(k.minute + 5))


def _explain_swing(e: StrategyEngine, rep: CandleReport, ans) -> str:
    long = e.direction == LONG
    attr = "h" if long else "l"
    hl = "Hoch" if long else "Tief"
    name = f"Swing-{hl}"
    word = "höher" if long else "tiefer"
    better = (lambda a, b: a > b + EPS) if long else (lambda a, b: a < b - EPS)
    swings = e.swing_highs if long else e.swing_lows
    lvl = rep.bos_level_candle

    if lvl is None:
        sol = f"Bis {rep.candle.time} gibt es kein bestätigtes {name} ab 9:00."
    else:
        p, n = _neighbors(e, lvl)
        sol = (f"Letztes bestätigtes {name} = {fmt(getattr(lvl, attr))} ({lvl.time}): {hl} "
               f"{word} als {p.time} ({fmt(getattr(p, attr))}) und {n.time} "
               f"({fmt(getattr(n, attr))}).")
    if ans is None:
        return sol

    seen = [k for k in e.candles if k.minute <= rep.candle.minute]
    match = [k for k in seen if _is(getattr(k, attr), ans)]
    if not match:
        return f"{sol} {fmt(ans)} ist kein {hl} einer Kerze ab 9:00."
    k = match[-1]
    if k.time == rep.candle.time:
        hint = (f"{fmt(ans)} ist das {hl} der aktuellen Kerze {k.time} - die ist noch NICHT "
                f"bestätigt, dafür braucht es die Kerze danach.")
    elif any(s.time == k.time for s in swings):
        hint = f"{fmt(ans)} ({k.time}) war ein älteres {name}. Es zählt das ZULETZT bestätigte."
    else:
        p, n = _neighbors(e, k)
        if p is None:
            why = "es gibt keine Kerze davor ab 9:00"
        elif not better(getattr(k, attr), getattr(p, attr)):
            why = f"{p.time} hat {hl} {fmt(getattr(p, attr))}, also ist {k.time} nicht {word}"
        else:
            why = f"{n.time} hat {hl} {fmt(getattr(n, attr))}, also ist {k.time} nicht {word}"
        hint = f"{fmt(ans)} ist das {hl} von {k.time}, aber kein Swing: {why}."
    return f"{sol} {hint}"


def _explain_bos(e: StrategyEngine, rep: CandleReport) -> str:
    long = e.direction == LONG
    c, lvl = rep.candle, rep.bos_level_candle
    name = "Swing-Hoch" if long else "Swing-Tief"
    if lvl is None:
        return f"Ohne bestätigtes {name} gibt es keinen BOS."
    level = lvl.h if long else lvl.l
    side = "über" if long else "unter"
    txt = (f"BOS = SCHLUSSKURS {side} dem {name} {fmt(level)} ({lvl.time}). "
           f"Close {c.time} = {fmt(c.c)} {_cmp(c.c, level)} {fmt(level)} -> "
           f"{'BOS' if rep.is_bos else 'kein BOS'}.")
    wick = c.h if long else c.l
    if not rep.is_bos and (wick > level + EPS if long else wick < level - EPS):
        txt += (f" Der Docht ({'Hoch' if long else 'Tief'} {fmt(wick)}) war zwar drüber, "
                f"aber der Docht zählt nicht - nur der Close.")
    return txt


def _leg_range(e: StrategyEngine, start: int, end: int, attr: str) -> float | None:
    ks = [k for k in e.candles if start <= k.minute <= end]
    if not ks:
        return None
    vals = [getattr(k, attr) for k in ks]
    return min(vals) if attr == "l" else max(vals)


def _explain_leg(e: StrategyEngine, ans, attr: str) -> str:
    lo, hi, b = e.leg_low, e.leg_high, e.bos_candle
    txt = (f"Leg = 9:30 bis INKLUSIVE BOS-Kerze {b.time}: tiefstes Tief {fmt(lo.l)} "
           f"({lo.time}), höchstes Hoch {fmt(hi.h)} ({hi.time}).")
    if ans is None:
        return txt
    right = lo.l if attr == "l" else hi.h
    without_bos = _leg_range(e, 9 * 60 + 30, b.minute - 5, attr)
    from_nine = _leg_range(e, START, b.minute, attr)
    if _is(ans, without_bos) and not _is(ans, right):
        txt += " Du hast die BOS-Kerze vergessen - sie gehört zum Leg."
    elif _is(ans, from_nine) and not _is(ans, right):
        txt += " Vor 9:30 zählt nicht - das Leg startet bei 9:30."
    elif _is(ans, hi.h if attr == "l" else lo.l):
        txt += " Hoch und Tief verwechselt."
    return txt


def _explain_entry(e: StrategyEngine, ans) -> str:
    lo, hi = e.leg_low.l, e.leg_high.h
    txt = f"Entry = (Leg-Tief {fmt(lo)} + Leg-Hoch {fmt(hi)}) / 2 = {fmt(e.entry)}."
    if _is(ans, hi - lo):
        txt += " Das ist die Leg-GRÖSSE, nicht die Mitte."
    elif _is(ans, (hi - lo) / 2):
        txt += " Das ist die halbe Leg-Größe - du musst sie noch auf das Tief addieren."
    return txt


def _explain_stop(e: StrategyEngine, ans) -> str:
    lo, hi = e.leg_low.l, e.leg_high.h
    if e.direction == LONG:
        txt = f"Long-Stop = Leg-Tief {fmt(lo)} - {STOP_OFFSET:.0f} = {fmt(e.stop)}."
        base, wrong_side, other = lo, lo + STOP_OFFSET, hi + STOP_OFFSET
    else:
        txt = f"Short-Stop = Leg-Hoch {fmt(hi)} + {STOP_OFFSET:.0f} = {fmt(e.stop)}."
        base, wrong_side, other = hi, hi - STOP_OFFSET, lo - STOP_OFFSET
    if _is(ans, base):
        txt += f" Du hast die {STOP_OFFSET:.0f} Punkte Puffer vergessen."
    elif _is(ans, wrong_side):
        txt += " Puffer auf der falschen Seite - der Stop liegt AUSSERHALB vom Leg."
    elif _is(ans, other):
        txt += " Das ist der Stop für die andere Richtung."
    elif e.entry is not None and (_is(ans, e.entry - STOP_OFFSET) or _is(ans, e.entry + STOP_OFFSET)):
        txt += " Der Stop hängt am Leg-Extrem, nicht am Entry."
    return txt


def _explain_risk(e: StrategyEngine, ans) -> str:
    lo, hi = e.leg_low.l, e.leg_high.h
    txt = f"Risiko = |Entry {fmt(e.entry)} - Stop {fmt(e.stop)}| = {fmt(e.risk)}."
    if _is(ans, (hi - lo) / 2):
        txt += f" Du hast die {STOP_OFFSET:.0f} Punkte Puffer nicht mitgerechnet."
    elif _is(ans, hi - lo):
        txt += " Das ist die ganze Leg-Größe, nicht Entry bis Stop."
    return txt


def _explain_target(e: StrategyEngine, ans) -> str:
    sign = 1 if e.direction == LONG else -1
    op = "+" if sign > 0 else "-"
    txt = (f"Ziel = Entry {fmt(e.entry)} {op} {RR:.0f} x Risiko {fmt(e.risk)} = "
           f"{fmt(e.target)}.")
    if _is(ans, e.entry + sign * e.risk):
        txt += " Das ist nur 1R - das Ziel ist 2R."
    elif _is(ans, e.entry - sign * RR * e.risk):
        txt += " Falsche Richtung."
    return txt


def _explain_valid(e: StrategyEngine) -> str:
    ok = e.risk <= MAX_RISK + EPS
    return (f"Risiko {fmt(e.risk)} {'<=' if ok else '>'} {MAX_RISK:.0f} -> "
            f"{'Trade erlaubt' if ok else 'kein Trade'}.")


def _explain_fill(e: StrategyEngine, rep: CandleReport) -> str:
    c = rep.candle
    if e.direction == LONG:
        return (f"Long-Limit wird gefüllt, wenn das TIEF die Entry erreicht: "
                f"Tief {fmt(c.l)} {'<=' if rep.filled else '>'} Entry {fmt(e.entry)}.")
    return (f"Short-Limit wird gefüllt, wenn das HOCH die Entry erreicht: "
            f"Hoch {fmt(c.h)} {'>=' if rep.filled else '<'} Entry {fmt(e.entry)}.")


def _explain_manage(e: StrategyEngine, rep: CandleReport) -> str:
    c = rep.candle
    long = e.direction == LONG
    s_ext, s_name = (c.l, "Tief") if long else (c.h, "Hoch")
    t_ext, t_name = (c.h, "Hoch") if long else (c.l, "Tief")
    s_hit = s_ext <= e.stop + EPS if long else s_ext >= e.stop - EPS
    t_hit = t_ext >= e.target - EPS if long else t_ext <= e.target + EPS
    s_txt = f"{s_name} {fmt(s_ext)} vs. Stop {fmt(e.stop)} -> {'getroffen' if s_hit else 'nicht getroffen'}"
    t_txt = f"{t_name} {fmt(t_ext)} vs. Ziel {fmt(e.target)} -> {'erreicht' if t_hit else 'nicht erreicht'}"
    if rep.filled:
        txt = f"Auf der Füll-Kerze zählt nur der Stop: {s_txt}."
        if t_hit and rep.outcome == OUT_ON:
            txt += (" Das Ziel zählt auf der Füll-Kerze noch NICHT - man weiß nicht, ob es "
                    "vor oder nach der Füllung kam.")
        return txt
    txt = f"Erst Stop prüfen: {s_txt}. Dann Ziel: {t_txt}."
    if s_hit and t_hit:
        txt += " Beide berührt -> Stop zählt zuerst (konservativ)."
    if rep.outcome == OUT_TIME:
        txt += f" 11:55 ist die letzte Kerze -> Zeit-Exit zum Close {fmt(c.c)}."
    return txt


def _explain_r(e: StrategyEngine) -> str:
    if e.result == TARGET:
        return f"Ziel = +{RR:.0f}R."
    if e.result == STOP:
        return "Stop = -1R."
    if e.direction == LONG:
        return (f"Zeit-Exit: (Close {fmt(e.exit_price)} - Entry {fmt(e.entry)}) / Risiko "
                f"{fmt(e.risk)} = {e.r:+.2f}R.")
    return (f"Zeit-Exit Short: (Entry {fmt(e.entry)} - Close {fmt(e.exit_price)}) / Risiko "
            f"{fmt(e.risk)} = {e.r:+.2f}R.")
