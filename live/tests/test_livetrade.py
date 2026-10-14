from datetime import datetime
from pathlib import Path

import pytest

from livebot.account import PaperLock, is_paper
from livebot.csv_source import read_candles
from livebot.journal import Journal
from livebot.livefeed import LiveFeed, match_closed
from livebot.livetrade import (ARMED, BREAKEVEN, CLOSED_LATE, CLOSED_NOON, DONE, IN_TRADE,
                               NOT_FILLED, ORDER_ERROR, STOP, TARGET, TradeManager)
from livebot.orders import LiveActions
from livebot.safety import SafetyError
from livebot.strategy import StrategyEngine

DATA = Path(__file__).parent / "data"


def T(hh, mm, ss=0):
    return hh * 3600 + mm * 60 + ss


class FakeActions:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def market(self, d, stop, target):
        self.calls.append(("market", d, stop, target))
        if self.fail == "market":
            raise RuntimeError("Dialog nicht offen")

    def breakeven(self, entry):
        self.calls.append(("breakeven", entry))

    def close(self):
        self.calls.append(("close",))

    def draw(self, d, entry, stop, target):
        self.calls.append(("draw", d))


def armed_manager(fail=None):
    """14.9.: Long, BOS 9:45, Entry 28962.25, Stop 28874.75, Ziel 29137.25."""
    e = StrategyEngine("2026-09-14")
    acts = FakeActions(fail)
    m = TradeManager(e, acts)
    for c in read_candles(DATA / "2026-09-14.csv"):
        e.on_candle(c)
        m.on_bar_closed()
        if c.time == "09:45":
            break
    assert m.state == ARMED and m.entry == pytest.approx(28962.25)
    return m, acts


def tick(m, sec, o, h, l, c):
    m.on_tick(sec, (o, h, l, c))


def test_einzelne_fehllesung_loest_keine_order_aus():
    m, acts = armed_manager()
    tick(m, T(10, 35, 10), 29017, 29017.75, 28900.0, 28990)   # Ziffer verlesen
    tick(m, T(10, 35, 11), 29017, 29017.75, 29000.0, 29000)   # wieder normal
    assert acts.calls == [] and m.state == ARMED


def test_genau_eine_order_bei_beruehrung_dann_ziel():
    m, acts = armed_manager()
    tick(m, T(10, 35, 10), 29017, 29017.75, 28961.0, 28965)
    tick(m, T(10, 35, 11), 29017, 29017.75, 28961.0, 28965)
    tick(m, T(10, 35, 12), 29017, 29017.75, 28959.5, 28970)
    assert [c[0] for c in acts.calls] == ["market", "draw"]
    assert acts.calls[0] == ("market", "long", pytest.approx(28874.75), pytest.approx(29137.25))
    assert m.state == IN_TRADE and m.fill_time == "10:35:11"
    for s in (0, 1):
        tick(m, T(11, 30, s), 29077, 29140.0, 29072, 29138)
    assert m.result == TARGET and m.r == 2.0 and m.exit_time == "11:30:01"
    tick(m, T(11, 35), 29077, 29140, 28000, 28000)
    assert [c[0] for c in acts.calls] == ["market", "draw"]        # nie eine zweite Order


def test_tief_vor_der_fuellung_zaehlt_nicht_als_stop():
    m, acts = armed_manager()
    # Füll-Kerze: Tief 28870 lag VOR der Füllung (unter dem Stop) - darf keinen Stop auslösen
    tick(m, T(10, 35, 10), 29017, 29017.75, 28870.0, 28965)
    tick(m, T(10, 35, 11), 29017, 29017.75, 28870.0, 28965)
    tick(m, T(10, 35, 30), 29017, 29017.75, 28870.0, 28980)
    tick(m, T(10, 35, 31), 29017, 29017.75, 28870.0, 28985)
    assert m.state == IN_TRADE


def test_zwoelf_uhr_im_plus_break_even_dann_be_stop():
    m, acts = armed_manager()
    for s in (0, 1):
        tick(m, T(10, 35, s), 29017, 29017.75, 28960, 28965)
    tick(m, T(12, 0, 1), 29000, 29010, 28995, 29005)              # im Plus
    assert acts.calls[-1] == ("breakeven", pytest.approx(28962.25))
    assert m.breakeven and m.sl == pytest.approx(28962.25)
    for s in (0, 1):
        tick(m, T(13, 10, s), 28970, 28975, 28960, 28961)
    assert m.result == BREAKEVEN and m.r == 0.0


def test_zwoelf_uhr_im_minus_schliessen():
    m, acts = armed_manager()
    for s in (0, 1):
        tick(m, T(10, 35, s), 29017, 29017.75, 28960, 28965)
    tick(m, T(12, 0, 1), 28950, 28955, 28940, 28945)
    assert acts.calls[-1] == ("close",)
    assert m.result == CLOSED_NOON
    assert m.r == pytest.approx((28945 - 28962.25) / 87.5)


def test_nach_break_even_um_1555_schliessen():
    m, acts = armed_manager()
    for s in (0, 1):
        tick(m, T(10, 35, s), 29017, 29017.75, 28960, 28965)
    tick(m, T(12, 0, 1), 29000, 29010, 28995, 29005)
    tick(m, T(15, 55, 0), 29050, 29060, 29040, 29055)
    assert acts.calls[-1] == ("close",) and m.result == CLOSED_LATE
    assert m.r == pytest.approx((29055 - 28962.25) / 87.5)


def test_nicht_gefuellt_bis_1105():
    m, acts = armed_manager()
    tick(m, T(11, 4, 59), 29011, 29017, 28986.75, 28990)
    m.on_time(T(11, 5, 0), None)
    assert m.result == NOT_FILLED and acts.calls == []


def test_order_fehler_kein_zweiter_versuch():
    m, acts = armed_manager(fail="market")
    for s in (0, 1, 2, 3):
        tick(m, T(10, 35, s), 29017, 29017.75, 28960, 28965)
    assert m.state == DONE and m.result == ORDER_ERROR
    assert [c[0] for c in acts.calls] == ["market"]
    assert "NICHT nochmal" in m.reason


def test_short_stop():
    e = StrategyEngine("x")
    acts = FakeActions()
    m = TradeManager(e, acts)
    m.state, m.direction = ARMED, "short"
    m.entry, m.stop, m.target, m.risk, m.sl = 100.0, 110.0, 80.0, 10.0, 110.0
    for s in (0, 1):
        tick(m, T(10, 0, s), 99, 100.5, 98, 100)
    assert acts.calls[0] == ("market", "short", 110.0, 80.0)
    for s in (0, 1):
        tick(m, T(10, 5, s), 100, 110.25, 99, 109)
    assert m.result == STOP and m.r == -1.0


# ------------------------------------------------------------ Feed

def dt(sec):
    return datetime(2026, 1, 5, sec // 3600, sec // 60 % 60, sec % 60)


def test_feed_kerzenwechsel_und_alte_legende():
    f = LiveFeed(settle=1.5)
    assert f.on_reading(dt(T(9, 0, 10)), (1, 2, 0.5, 1.5)) == ([], (1, 2, 0.5, 1.5))
    f.on_reading(dt(T(9, 4, 59)), (1, 3, 0.5, 2.5))
    closed, fresh = f.on_reading(dt(T(9, 5, 0)), (1, 3, 0.5, 2.5))   # Legende noch alt
    assert closed == [(540, (1, 3, 0.5, 2.5))] and fresh is None
    closed, fresh = f.on_reading(dt(T(9, 5, 2)), (1, 3, 0.5, 2.5))   # immer noch alt
    assert closed == [] and fresh is None
    closed, fresh = f.on_reading(dt(T(9, 5, 3)), (2.5, 2.75, 2.25, 2.5))
    assert fresh == (2.5, 2.75, 2.25, 2.5)


def test_match_closed():
    approx = (100.0, 105.0, 99.0, 104.0)
    assert match_closed((100.0, 105.25, 99.0, 104.25), approx)
    assert match_closed((100.0, 105.0, 98.0, 112.0), approx)             # schneller Markt
    assert not match_closed((104.0, 104.5, 103.5, 104.25), approx)      # entstehende Kerze
    assert not match_closed((100.0, 104.0, 99.0, 104.0), approx)        # Hoch kleiner -> falsch


# ------------------------------------------------------------ Paper-Sperre / Aktionen

@pytest.mark.parametrize("text,ok", [("Paper Trading", True), ("PaperTrading | Paoer Trading", True),
                                     ("Paoer Tradlng", True), ("Interactive Brokers", False),
                                     ("", False), ("TradeStation 123", False)])
def test_is_paper(text, ok):
    assert is_paper(text) is ok


class FakeDrawer:
    def __init__(self):
        self.played = []

    def play(self, name, values, final_esc=True, pause=None):
        self.played.append((name, values))


def test_kein_paper_keine_order(tmp_path):
    dr = FakeDrawer()
    lock = PaperLock({"konto": [1, 1, 10, 10]}, Journal(tmp_path), read_fn=lambda r: "Echtgeld-Konto")
    acts = LiveActions({"menge": 2}, dr, lock)
    with pytest.raises(SafetyError, match="Kein Paper-Konto"):
        acts.market("long", 90, 120)
    assert dr.played == []
    assert "NEIN" in (tmp_path / "logs" / "aktionen.log").read_text(encoding="utf-8")


def test_paper_order_mit_menge_tp_sl(tmp_path):
    dr = FakeDrawer()
    lock = PaperLock({"konto": [1, 1, 10, 10]}, Journal(tmp_path), read_fn=lambda r: "Paper Trading")
    acts = LiveActions({"menge": 2}, dr, lock)
    acts.market("short", 110, 80)
    acts.breakeven(100)
    acts.close()
    assert dr.played == [("verkaufen", {"menge": 2, "stop": 110, "ziel": 80}),
                         ("breakeven", {"entry": 100}), ("schliessen", {})]


def test_ohne_orders_wird_nichts_geklickt(tmp_path):
    dr = FakeDrawer()
    lock = PaperLock({}, Journal(tmp_path), read_fn=lambda r: "x")
    acts = LiveActions({}, dr, lock, enabled=False)
    acts.market("long", 1, 2)
    acts.breakeven(1)
    acts.close()
    assert dr.played == []


def test_konto_nicht_kalibriert(tmp_path):
    lock = PaperLock({}, Journal(tmp_path), read_fn=lambda r: "Paper Trading")
    with pytest.raises(SafetyError, match="nicht kalibriert"):
        lock.check("Markt kaufen")


def test_paper_sperre_meldet_nichts_geklickt():
    from livebot.livetrade import NO_PAPER

    class PaperFail(FakeActions):
        def market(self, d, stop, target):
            self.calls.append(("market",))
            raise SafetyError("Kein Paper-Konto erkannt (gelesen: 'Live') - 'Markt kaufen' NICHT")
    e = StrategyEngine("x")
    acts = PaperFail()
    m = TradeManager(e, acts)
    m.state, m.direction = ARMED, "long"
    m.entry, m.stop, m.target, m.risk, m.sl = 100.0, 90.0, 120.0, 10.0, 90.0
    for s in (0, 1, 2):
        tick(m, T(10, 0, s), 101, 102, 99.5, 100)
    assert m.result == NO_PAPER and "NICHTS geklickt" in m.reason
    assert m.row("x")["Füllzeit"] == "" and len(acts.calls) == 1


def test_aktions_test_sequenz(tmp_path):
    from livebot.runner import SEQUENZEN, run_sequence
    dr = FakeDrawer()
    lock = PaperLock({"konto": [1, 1, 10, 10]}, Journal(tmp_path), read_fn=lambda r: "Paper Trading")
    acts = LiveActions({"menge": 1}, dr, lock)
    out = []
    assert run_sequence(acts, 30000.0, SEQUENZEN["alle"], say=out.append, sleep=lambda s: None)
    assert [p[0] for p in dr.played] == ["kaufen", "breakeven", "schliessen",
                                         "verkaufen", "breakeven", "schliessen"]
    assert dr.played[0][1] == {"menge": 1, "stop": 29950.0, "ziel": 30050.0}
    assert dr.played[1][1] == {"entry": 29980.0}          # Long: SL unter dem Kurs
    assert dr.played[3][1] == {"menge": 1, "stop": 30050.0, "ziel": 29950.0}
    assert dr.played[4][1] == {"entry": 30020.0}          # Short: SL über dem Kurs


def test_aktions_test_bricht_bei_fehler_ab(tmp_path):
    from livebot.runner import run_sequence
    lock = PaperLock({"konto": [1, 1, 10, 10]}, Journal(tmp_path), read_fn=lambda r: "Echtgeld")
    acts = LiveActions({"menge": 1}, FakeDrawer(), lock)
    out = []
    assert not run_sequence(acts, 30000.0, ["kaufen", "schliessen"], say=out.append,
                            sleep=lambda s: None)
    assert any("Kein Paper-Konto" in o for o in out) and not any("'schliessen' ausgeführt" in o for o in out)
