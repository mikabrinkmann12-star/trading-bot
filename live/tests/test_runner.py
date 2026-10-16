"""Ein kompletter simulierter Live-Tag: Uhr läuft, Legende tickt, Bot handelt einmal."""
from datetime import datetime
from pathlib import Path

import pytest

from livebot.csv_source import read_candles
from livebot.journal import Journal
from livebot.livetrade import TARGET, TradeManager
from livebot.models import t2m
from livebot.runner import DONE, LiveRunner
from livebot.strategy import StrategyEngine
from test_livetrade import FakeActions

DATA = Path(__file__).parent / "data"


class TickingLegend:
    """Simuliert die Live-Legende: jede Kerze baut sich in 300 s auf
    (O -> Tief -> Hoch -> Close bzw. O -> Hoch -> Tief -> Close)."""

    def __init__(self, candles):
        self.by_min = {t2m(c.time): c for c in candles}
        self.now = None

    def read(self):
        sec = self.now.hour * 3600 + self.now.minute * 60 + self.now.second
        bar = sec // 300 * 5
        c = self.by_min.get(bar)
        if c is None:
            return None, "", None
        p = (sec - bar * 60) / 300
        down_first = c.c >= c.o
        path = [c.o, c.l, c.h, c.c] if down_first else [c.o, c.h, c.l, c.c]
        k = min(int(p * 3), 2)
        f = p * 3 - k
        price = path[k] + (path[k + 1] - path[k]) * f
        seen = path[:k + 1] + [price]
        if p >= 0.98:
            price, seen = c.c, path
        return (c.o, max(seen), min(seen), price), "", None


def test_ganzer_live_tag(tmp_path):
    cs = read_candles(DATA / "2026-09-14.csv")
    leg = TickingLegend(cs)
    engine = StrategyEngine("2026-09-14")
    acts = FakeActions()
    acts.last_closed = acts.prev_closed = None
    m = TradeManager(engine, acts)
    posts = []
    r = LiveRunner(engine, m, Journal(tmp_path), date="2026-09-14", read_fn=leg.read,
                   post=lambda k, p: posts.append((k, p)), actions=acts)
    sec = 9 * 3600 + 2
    while sec < 12 * 3600:
        leg.now = datetime(2026, 9, 14, sec // 3600, sec // 60 % 60, sec % 60)
        if not r.step(leg.now):
            break
        sec += 2
    assert [c.time for c in engine.candles][:10] == [c.time for c in cs][:10]
    assert engine.candles[9].c == cs[9].c                       # BOS-Kerze exakt
    assert engine.bos_candle.time == "09:45"
    assert [c[0] for c in acts.calls] == ["market", "draw"]
    assert m.fill_time.startswith("10:3")
    assert m.result == TARGET and m.r == pytest.approx(2.0)
    assert posts[-1][0] == DONE
    assert "2026-09-14" in (tmp_path / "trades.csv").read_text(encoding="utf-8")


def test_probelauf_uhr_passt_zu_den_kerzen():
    from datetime import datetime

    from livebot.nyclock import ShiftClock, probe_shift, sec_of_day
    for hh, mm, ss in ((11, 2, 30), (11, 5, 0), (9, 0, 1), (14, 59, 59)):
        real = datetime(2026, 10, 15, hh, mm, ss)
        shift = probe_shift(sec_of_day(real))
        assert shift % 300 == 0                                   # Kerzengrenzen bleiben gleich
        sim = sec_of_day(ShiftClock(shift, real=lambda r=real: r)())
        assert 8 * 3600 + 55 * 60 <= sim < 9 * 3600
    assert probe_shift(8 * 3600) == 0                              # vor 9:00: nichts verschieben


def test_zu_spaeter_start_wird_erklaert():
    from datetime import datetime

    from livebot.nyclock import start_problem
    assert start_problem(datetime(2026, 10, 15, 8, 55)) is None    # Donnerstag 8:55 NY
    assert start_problem(datetime(2026, 10, 15, 9, 3)) is None
    why = start_problem(datetime(2026, 10, 15, 11, 0))
    assert "--probelauf" in why and "11:00" in why
    assert "Wochenende" in start_problem(datetime(2026, 10, 17, 8, 0))


def test_maus_im_chart_wird_nicht_gelesen(tmp_path):
    """Steht die Maus im Chart, zeigt die Legende eine ALTE Kerze (hier: Tief unter dem Entry).
    Das darf weder eine Order auslösen noch als Kerze zählen."""
    cs = read_candles(DATA / "2026-09-14.csv")
    leg = TickingLegend(cs)
    engine = StrategyEngine("2026-09-14")
    acts = FakeActions()
    acts.last_closed = acts.prev_closed = None
    m = TradeManager(engine, acts)
    posts = []
    mouse = {"pos": None}
    old = (28950.0, 28960.0, 28900.0, 28955.0)          # Kerze unter der Maus

    def read():
        if mouse["pos"]:
            return old, "", None
        return leg.read()
    r = LiveRunner(engine, m, Journal(tmp_path), date="2026-09-14", read_fn=read,
                   post=lambda k, p: posts.append((k, p)), actions=acts,
                   mouse_fn=lambda: mouse["pos"], chart_rect=(0, 0, 1000, 600),
                   ignore_fn=lambda: (800, 400, 200, 200))
    sec = 9 * 3600 + 2
    while sec < 10 * 3600 + 20 * 60:                    # bis 10:20, Entry noch nicht berührt
        leg.now = datetime(2026, 9, 14, sec // 3600, sec // 60 % 60, sec % 60)
        mouse["pos"] = (500, 300) if 10 * 3600 + 5 * 60 < sec < 10 * 3600 + 7 * 60 else None
        r.step(leg.now)
        sec += 2
    assert acts.calls == []                             # keine Order wegen der alten Kerze
    assert all(c.l != 28900.0 for c in engine.candles)
    assert any("Maus aus dem Chart" in str(p) for k, p in posts)
    mouse["pos"] = (900, 500)                           # über dem Bot-Fenster: zählt nicht
    assert not r._mouse_in_chart()


def test_spaeter_start_mit_nachgelesenen_kerzen_handelt_normal(tmp_path):
    """Start um 9:21: Kerzen 9:00-9:15 werden nachgelesen, ab 9:20 live - gleiches Ergebnis."""
    cs = read_candles(DATA / "2026-09-14.csv")
    leg = TickingLegend(cs)
    engine = StrategyEngine("2026-09-14")
    acts = FakeActions()
    acts.last_closed = acts.prev_closed = None
    m = TradeManager(engine, acts)
    r = LiveRunner(engine, m, Journal(tmp_path), date="2026-09-14", read_fn=leg.read,
                   post=lambda k, p: None, actions=acts)
    r.preload([(c.o, c.h, c.l, c.c) for c in cs[:4]])          # 9:00, 9:05, 9:10, 9:15
    sec = 9 * 3600 + 21 * 60
    while sec < 12 * 3600:
        leg.now = datetime(2026, 9, 14, sec // 3600, sec // 60 % 60, sec % 60)
        if not r.step(leg.now):
            break
        sec += 2
    assert [c.time for c in engine.candles][:6] == ["09:00", "09:05", "09:10", "09:15", "09:20",
                                                    "09:25"]
    assert engine.bos_candle.time == "09:45" and m.result == TARGET


def test_start_bis_944_erlaubt_danach_nicht():
    from livebot.nyclock import missed_bars, start_problem
    assert start_problem(datetime(2026, 10, 16, 9, 6)) is None
    assert start_problem(datetime(2026, 10, 16, 9, 44)) is None
    assert "9:44" in start_problem(datetime(2026, 10, 16, 9, 45))
    assert missed_bars(datetime(2026, 10, 16, 9, 6)) == 1        # 9:00 ist fertig
    assert missed_bars(datetime(2026, 10, 16, 9, 21)) == 4
    assert missed_bars(datetime(2026, 10, 16, 8, 50)) == 0
