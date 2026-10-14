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
