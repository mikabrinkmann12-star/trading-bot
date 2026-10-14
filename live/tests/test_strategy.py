from pathlib import Path

import pytest

from livebot.csv_source import read_candles
from livebot.models import Candle, m2t, t2m
from livebot.strategy import (ERROR, LONG, NO_TRADE, NOT_FILLED, SHORT, STOP, TARGET,
                                TIME_EXIT, StrategyEngine)

DATA = Path(__file__).parent / "data"


def run(candles, date=""):
    e = StrategyEngine(date)
    for c in candles:
        e.on_candle(c)
        if e.done:
            break
    e.end_of_data()
    return e


# ------------------------------------------------------------ echte Testtage

def test_tag_a_2026_09_25():
    e = run(read_candles(DATA / "2026-09-25.csv"))
    assert e.direction == LONG
    assert e.bos_candle.time == "09:50"
    assert e.entry == pytest.approx(30845.0)
    assert e.stop == pytest.approx(30763.5)
    assert e.risk == pytest.approx(81.5)
    assert e.target == pytest.approx(31008.0)
    assert e.fill_candle.time == "10:00"
    assert e.result == STOP
    assert e.r == pytest.approx(-1.0)


def test_tag_b_2026_09_14():
    e = run(read_candles(DATA / "2026-09-14.csv"))
    assert e.direction == LONG
    assert e.bos_candle.time == "09:45"
    assert e.swing_highs[0].time == "09:30"
    assert e.entry == pytest.approx(28962.25)   # = 28962.3 gerundet
    assert e.stop == pytest.approx(28874.75)
    assert e.risk == pytest.approx(87.5)
    assert e.target == pytest.approx(29137.25)
    assert e.fill_candle.time == "10:35"
    assert e.result == TARGET
    assert e.exit_candle.time == "11:30"
    assert e.r == pytest.approx(2.0)


# ------------------------------------------------------------ konstruierter Tag
# Basis-Long-Tag: Swing-Hoch 120 (9:35), BOS 9:45 (Close 125),
# Leg 90..126 -> Entry 108, Stop 86, Risiko 22, Ziel 152.
BASE = {
    "09:30": (100, 105, 90, 104),
    "09:35": (104, 120, 103, 112),
    "09:40": (112, 115, 108, 110),
    "09:45": (110, 126, 109, 125),
}
PRE = (100, 101, 99, 100)     # vor 9:30
POST = (130, 131, 129, 130)   # nach 9:45: über Entry, unter Ziel


def day(overrides=None, start="09:00", end="11:55"):
    data = dict(BASE)
    data.update(overrides or {})
    out = []
    for m in range(t2m(start), t2m(end) + 1, 5):
        t = m2t(m)
        default = PRE if m < t2m("09:30") else POST
        out.append(Candle(t, *data.get(t, default)))
    return out


def mirror(candles, axis=200):
    """Spiegelt einen Long-Tag zu einem Short-Tag."""
    return [Candle(c.time, axis - c.o, axis - c.l, axis - c.h, axis - c.c) for c in candles]


def test_basis_setup_werte():
    e = run(day())
    assert e.direction == LONG
    assert e.bos_candle.time == "09:45"
    assert (e.entry, e.stop, e.risk, e.target) == pytest.approx((108, 86, 22, 152))


def test_nicht_gefuellt_bis_1100():
    e = run(day())
    assert e.result == NOT_FILLED
    assert e.fill_candle is None


def test_fuellung_nach_1100_zaehlt_nicht():
    e = run(day({"11:05": (130, 131, 100, 110)}))
    assert e.result == NOT_FILLED


def test_fuellung_1100_zaehlt_noch():
    e = run(day({"11:00": (130, 131, 100, 110), "11:30": (130, 160, 129, 150)}))
    assert e.fill_candle.time == "11:00"
    assert e.result == TARGET


def test_ziel():
    e = run(day({"10:00": (130, 131, 105, 110), "10:30": (130, 155, 129, 150)}))
    assert e.fill_candle.time == "10:00"
    assert e.result == TARGET
    assert e.exit_candle.time == "10:30"
    assert e.r == pytest.approx(2.0)


def test_fuellkerze_beruehrt_stop():
    e = run(day({"10:00": (130, 131, 80, 100)}))
    assert e.result == STOP
    assert e.exit_candle.time == "10:00"
    assert e.r == pytest.approx(-1.0)


def test_fuellkerze_ziel_zaehlt_nicht_und_zeit_exit():
    # Füll-Kerze reicht bis 160 (> Ziel 152), zählt aber nicht. Danach nichts -> 11:55 Close 130.
    e = run(day({"10:00": (130, 160, 105, 110)}))
    assert e.result == TIME_EXIT
    assert e.exit_candle.time == "11:55"
    assert e.r == pytest.approx((130 - 108) / 22)


def test_stop_vor_ziel_auf_derselben_kerze():
    e = run(day({"10:00": (130, 131, 105, 110), "10:05": (100, 160, 80, 100)}))
    assert e.result == STOP


def test_bos_kerze_selbst_fuellt_nicht():
    # Füllung erst ab der Kerze NACH dem BOS. Die BOS-Kerze hat Tief 109 > 108 sowieso;
    # hier mit Tief 100 auf der BOS-Kerze (Leg-Tief bleibt 90).
    e = run(day({"09:45": (110, 126, 100, 125)}))
    assert e.result == NOT_FILLED


def test_open_gleich_close_kein_trade():
    e = run(day({"09:40": (112, 115, 99, 100)}))
    assert e.result == NO_TRADE
    assert e.direction == "kein"


def test_kein_bos_bis_0955():
    flat = (119, 119.5, 118, 119)
    e = run(day({"09:45": (110, 119.5, 109, 119), "09:50": flat, "09:55": flat}))
    assert e.result == NO_TRADE
    assert e.bos_candle is None


def test_docht_ueber_swing_ist_kein_bos():
    flat = (119, 119.5, 118, 119)
    e = run(day({"09:45": (110, 125, 109, 119), "09:50": flat, "09:55": flat}))
    assert e.bos_candle is None
    assert e.result == NO_TRADE


def test_bos_auf_0955_moeglich():
    flat = (119, 119.5, 118, 119)
    e = run(day({"09:45": (110, 119.5, 109, 119), "09:50": flat, "09:55": (119, 126, 118, 125)}))
    assert e.bos_candle.time == "09:55"


def test_risiko_ueber_100_kein_trade():
    e = run(day({"09:45": (110, 400, 109, 125)}))
    assert e.risk > 100
    assert e.result == NO_TRADE


def test_risiko_genau_100_ist_erlaubt():
    # Leg 90..282 -> Entry 186, Stop 86, Risiko 100
    e = run(day({"09:45": (110, 282, 109, 125)}))
    assert e.risk == pytest.approx(100)
    assert e.result != NO_TRADE


def test_letztes_swing_zaehlt_nicht_das_hoechste():
    # Älteres, höheres Swing-Hoch 150 um 9:15; das letzte ist 120 (9:35) -> BOS bei 125.
    e = run(day({"09:15": (100, 150, 99, 100)}))
    assert [s.h for s in e.swing_highs][:2] == [150, 120]
    assert e.bos_candle.time == "09:45"


def test_short_spiegelbildlich():
    long_day = day({"10:00": (130, 131, 105, 110), "10:30": (130, 155, 129, 150)})
    e = run(mirror(long_day))
    assert e.direction == SHORT
    assert e.bos_candle.time == "09:45"
    assert (e.entry, e.stop, e.risk, e.target) == pytest.approx((92, 114, 22, 48))
    assert e.fill_candle.time == "10:00"
    assert e.result == TARGET
    assert e.r == pytest.approx(2.0)


def test_short_zeit_exit_r():
    e = run(mirror(day({"10:00": (130, 131, 105, 110)})))
    assert e.result == TIME_EXIT
    # Short: (Entry - Close) / Risiko = (92 - 70) / 22
    assert e.r == pytest.approx((92 - 70) / 22)


def test_start_erst_0910():
    e = run(day(start="09:10", overrides={"10:00": (130, 131, 105, 110),
                                          "10:30": (130, 155, 129, 150)}))
    assert e.result == TARGET


def test_ohne_0930_fehler():
    e = run(day(start="09:35"))
    assert e.result == ERROR


def test_kerzen_vor_0900_werden_ignoriert():
    candles = [Candle("08:55", 100, 500, 1, 100)] + day()
    e = run(candles)
    assert e.candles[0].time == "09:00"
    assert e.swing_highs[0].time == "09:35"


def test_reihenfolge_falsch_gibt_fehler():
    e = StrategyEngine()
    e.on_candle(Candle("09:05", *PRE))
    with pytest.raises(ValueError):
        e.on_candle(Candle("09:00", *PRE))


def test_unplausible_kerze_gibt_fehler():
    with pytest.raises(ValueError):
        StrategyEngine().on_candle(Candle("09:00", 100, 99, 98, 100))  # O > H
