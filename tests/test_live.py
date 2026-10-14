from pathlib import Path

from replaybot.csv_source import read_candles
from replaybot.journal import Journal
from replaybot.live import DONE, ERROR, STATUS, LiveReader
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


def test_open_luecke_stoppt(tmp_path):
    big1 = (30000.0, 30010.0, 29990.0, 30000.0)
    big2 = (30040.0, 30050.0, 30030.0, 30045.0)   # Open 40 Punkte vom letzten Close weg
    reader, engine, posts = make([(big1, "")] * 2 + [(big2, "")] * 2, tmp_path,
                                 max_open_gap=25)
    run_all(reader, 4)
    assert len(engine.candles) == 1
    assert reader.finished
    assert posts[-1][0] == ERROR and "übersprungen" in posts[-1][1]


def _v(c):
    return (c.o, c.h, c.l, c.c)


def test_fall_aus_dem_screenshot_zu_schnell_geklickt(tmp_path):
    """9:30 verpasst (zu schnell geklickt), dann Maus über der 9:30 -> muss stoppen,
    statt die 9:35 als 9:30 zu zählen."""
    cs = {c.time: c for c in read_candles(DATA / "2026-09-25.csv")}
    seq = ["09:10", "09:15", "09:20", "09:25", "09:35", "09:30", "09:35"]
    reader, engine, posts = make([(_v(cs[t]), "") for t in seq for _ in range(2)],
                                 tmp_path, start="09:10")
    run_all(reader, 14)
    assert [c.time for c in engine.candles] == ["09:10", "09:15", "09:20", "09:25"]
    assert posts[-1][0] == ERROR


def test_maus_ueber_alter_kerze_wird_ignoriert(tmp_path):
    cs = {c.time: c for c in read_candles(DATA / "2026-09-25.csv")}
    seq = ["09:10", "09:15", "09:20", "09:15", "09:15", "09:15", "09:20", "09:25"]
    reader, engine, posts = make([(_v(cs[t]), "") for t in seq for _ in range(2)],
                                 tmp_path, start="09:10")
    run_all(reader, 16)
    assert [c.time for c in engine.candles] == ["09:10", "09:15", "09:20", "09:25"]
    assert engine.candles[-1].o == cs["09:25"].o
    assert any(k == STATUS and "ältere Kerze" in p[0] for k, p in posts)


class FakeReplay:
    """Simuliert TradingView: die Legende springt erst nach einem Klick weiter."""

    def __init__(self, candles):
        self.candles = candles
        self.i = 0
        self.clicks = 0

    def read(self):
        return _v(self.candles[self.i]), "", None

    def click(self):
        self.clicks += 1
        if self.i < len(self.candles) - 1:
            self.i += 1


def test_auto_klickt_bis_ergebnis(tmp_path):
    replay = FakeReplay(read_candles(DATA / "2026-09-14.csv"))
    engine = StrategyEngine("2026-09-14")
    posts = []
    reader = LiveReader(engine, Journal(tmp_path), read_fn=replay.read,
                        post=lambda k, p: posts.append((k, p)), clicker=replay.click,
                        click_pause=0)
    run_all(reader, 500)
    assert engine.result == "Ziel" and engine.r == 2
    assert engine.candles[-1].time == "11:30"
    assert replay.clicks == len(engine.candles) - 1     # nach der letzten Kerze kein Klick
    assert posts[-1][0] == DONE


def test_auto_timeout_wenn_nichts_passiert(tmp_path):
    now = [0.0]
    replay = FakeReplay(read_candles(DATA / "2026-09-14.csv"))
    replay.click = lambda: None                         # Klick bewirkt nichts
    engine = StrategyEngine("2026-09-14")
    posts = []
    reader = LiveReader(engine, Journal(tmp_path), read_fn=replay.read,
                        post=lambda k, p: posts.append((k, p)), clicker=replay.click,
                        click_timeout=5, clock=lambda: now[0])
    for _ in range(30):
        if not reader.step():
            break
        now[0] += 0.5
    assert posts[-1][0] == ERROR and "keine neue Kerze" in posts[-1][1]
    assert len(engine.candles) == 1


def test_auto_klick_verweigert_stoppt(tmp_path):
    from replaybot.safety import SafetyError

    def refuse():
        raise SafetyError("kein TradingView-Fenster")
    replay = FakeReplay(read_candles(DATA / "2026-09-14.csv"))
    engine = StrategyEngine("2026-09-14")
    posts = []
    reader = LiveReader(engine, Journal(tmp_path), read_fn=replay.read,
                        post=lambda k, p: posts.append((k, p)), clicker=refuse)
    run_all(reader, 10)
    assert posts[-1][0] == ERROR and "verweigert" in posts[-1][1]


def test_auto_ohne_timeout_wartet_einfach(tmp_path):
    """Standard: kein Abbruch, auch wenn die Kerze nach dem Klick lange braucht."""
    now = [0.0]
    replay = FakeReplay(read_candles(DATA / "2026-09-14.csv"))
    clicks = []
    engine = StrategyEngine("2026-09-14")
    posts = []
    reader = LiveReader(engine, Journal(tmp_path), read_fn=replay.read,
                        post=lambda k, p: posts.append((k, p)), clicker=lambda: clicks.append(1),
                        clock=lambda: now[0])
    for _ in range(100):                      # 50 s lang passiert nichts
        assert reader.step()
        now[0] += 0.5
    assert not reader.finished
    assert len(clicks) == 1                   # und es wird NICHT nochmal geklickt
    assert "seit" in posts[-1][1][0]
    replay.click()                            # jetzt kommt die Kerze doch
    reader.step()
    reader.step()
    assert len(engine.candles) == 2


def test_auto_pause_nach_klick(tmp_path):
    """Nach jedem Klick 2 s nichts lesen und nicht klicken."""
    now = [0.0]
    replay = FakeReplay(read_candles(DATA / "2026-09-14.csv"))
    click_times = []

    def click():
        click_times.append(now[0])
        replay.click()
    engine = StrategyEngine("2026-09-14")
    reader = LiveReader(engine, Journal(tmp_path), read_fn=replay.read, post=lambda k, p: None,
                        clicker=click, clock=lambda: now[0], click_pause=2.0)
    for _ in range(40):
        reader.step()
        now[0] += 0.5
    gaps = [b - a for a, b in zip(click_times, click_times[1:])]
    assert gaps and min(gaps) >= 2.0
