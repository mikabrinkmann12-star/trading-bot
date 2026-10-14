from pathlib import Path

from replaybot.csv_source import read_candles
from replaybot.journal import Journal
from replaybot.live import CANDLE, DONE, ERROR, STATUS, LiveReader
from replaybot.strategy import STOP, StrategyEngine

DATA = Path(__file__).parent / "data"


def make(readings, tmp_path, **kw):
    """readings: Liste von (vals|None, text) - eine pro step()."""
    it = iter(readings)
    posts = []
    engine = StrategyEngine("2026-09-25")
    reader = LiveReader(engine, Journal(tmp_path),
                        read_fn=lambda: (*next(it), None),
                        post=lambda k, p: posts.append((k, p)), **kw)
    return reader, engine, posts


def run_all(reader, n):
    for _ in range(n):
        if not reader.step():
            break


def test_tag_a_live_gelesen(tmp_path):
    candles = read_candles(DATA / "2026-09-25.csv")
    readings = []
    for c in candles:
        v = (c.o, c.h, c.l, c.c)
        readings += [(v, "")] * 3          # jede Kerze wird mehrfach gepollt
    reader, engine, posts = make(readings, tmp_path, start="09:10")
    run_all(reader, len(readings))
    assert [c.time for c in engine.candles] == [c.time for c in candles]
    assert engine.result == STOP and engine.r == -1
    assert posts[-1][0] == DONE
    assert (tmp_path / "trades.csv").read_text(encoding="utf-8").count("2026-09-25") == 1


def test_einmal_gelesen_reicht_nicht(tmp_path):
    v1 = (100.0, 101.0, 99.0, 100.5)
    v2 = (100.5, 102.0, 100.0, 101.0)
    reader, engine, _ = make([(v1, ""), (v1, ""), (v2, ""), (v1, "")], tmp_path)
    run_all(reader, 4)
    # v2 tauchte nur einmal auf (z.B. Maus kurz über dem Chart) -> nicht übernommen
    assert len(engine.candles) == 1


def test_lesefehler_dreimal_neu_dann_stopp(tmp_path):
    reader, engine, posts = make([(None, "xx")] * 10, tmp_path)
    run_all(reader, 10)
    assert reader.finished
    assert [k for k, _ in posts].count(STATUS) == 3     # 3x neu lesen
    assert posts[-1][0] == ERROR


def test_lesefehler_zwischendurch_wird_zurueckgesetzt(tmp_path):
    v = (100.0, 101.0, 99.0, 100.5)
    reader, engine, posts = make([(None, "")] * 3 + [(v, "")] * 2 + [(None, "")] * 3, tmp_path)
    run_all(reader, 8)
    assert not reader.finished
    assert len(engine.candles) == 1


def test_ziffer_verschluckt_wird_nicht_uebernommen(tmp_path):
    v = (30877.0, 30888.75, 30847.5, 30874.25)
    bad = (3087.0, 30888.75, 3080.0, 30874.25)  # wäre L<=O,C<=H-ok, aber 90 % Sprung
    reader, engine, posts = make([(v, "")] * 2 + [(bad, "")] * 5, tmp_path)
    run_all(reader, 7)
    assert len(engine.candles) == 1
    assert posts[-1][0] == ERROR


def test_maus_im_chart_wird_nicht_gelesen(tmp_path):
    v = (100.0, 101.0, 99.0, 100.5)
    reader, engine, posts = make([(v, "")] * 4, tmp_path,
                                 mouse_fn=lambda: (500, 500), chart_rect=[0, 0, 1000, 800])
    run_all(reader, 4)
    assert engine.candles == []
    assert "Maus" in posts[-1][1][0]


def test_open_luecke_gibt_warnung(tmp_path):
    big1 = (30000.0, 30010.0, 29990.0, 30000.0)
    big2 = (30040.0, 30050.0, 30030.0, 30045.0)   # Open 40 Punkte vom letzten Close weg
    reader, engine, posts = make([(big1, "")] * 2 + [(big2, "")] * 2, tmp_path,
                                 max_open_gap=25)
    run_all(reader, 4)
    assert len(engine.candles) == 2
    assert any(k == STATUS and "übersprungen" in p[0] for k, p in posts)
    assert any(k == CANDLE for k, _ in posts)
