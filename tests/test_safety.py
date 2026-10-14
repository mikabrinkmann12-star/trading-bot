import pytest

from replaybot.journal import Journal
from replaybot.safety import Guard, SafetyError

CFG = {
    "naechste_kerze": [900, 925],
    "chart": [60, 80, 1500, 800],
    "preisachse": [1600, 80, 70, 800],
    "ablaeufe": {"long": [{"punkt": [700, 1010], "doppel": False, "tippe": None}]},
}


class FakeBackend:
    def __init__(self):
        self.calls = []

    def click(self, x, y, double=False):
        self.calls.append(("dclick" if double else "click", x, y))

    def drag(self, x1, y1, x2, y2):
        self.calls.append(("drag", x1, y1, x2, y2))

    def type_text(self, text):
        self.calls.append(("type", text))

    def press(self, key):
        self.calls.append(("press", key))

    def move(self, x, y):
        self.calls.append(("move", x, y))


def make(tmp_path, title="NQ1! - TradingView", exe="TradingView.exe", fg=None, **kw):
    be = FakeBackend()
    g = Guard(CFG, Journal(tmp_path), backend=be, window_fn=lambda x, y: (title, exe),
              foreground_fn=lambda: fg or (title, exe), **kw)
    return g, be.calls


def log(tmp_path):
    return (tmp_path / "logs" / "aktionen.log").read_text(encoding="utf-8")


def test_klick_erlaubt(tmp_path):
    g, calls = make(tmp_path)
    g.click_next()
    assert calls == [("click", 900, 925)]
    assert "Aktion 1/200" in log(tmp_path)


def test_desktop_app_ohne_tradingview_im_titel(tmp_path):
    g, calls = make(tmp_path, title="NQ1! 30.222,25 -1,85% / TJR", exe="TradingView.exe")
    g.click_next()
    assert calls


def test_falsches_fenster(tmp_path):
    g, calls = make(tmp_path, title="Editor", exe="notepad.exe")
    with pytest.raises(SafetyError):
        g.click_next()
    assert calls == []
    assert "VERWEIGERT" in log(tmp_path)


def test_punkt_nicht_kalibriert(tmp_path):
    g, calls = make(tmp_path)
    with pytest.raises(SafetyError):
        g.click(500, 500, "irgendwo")
    assert calls == []


def test_ablauf_punkt_und_doppelklick_erlaubt(tmp_path):
    g, calls = make(tmp_path)
    g.click(705, 1008, "Long-Werkzeug", double=True)
    assert calls == [("dclick", 705, 1008)]


def test_max_aktionen(tmp_path):
    g, calls = make(tmp_path, max_clicks=3)
    for _ in range(3):
        g.click_next()
    with pytest.raises(SafetyError):
        g.click_next()
    assert len(calls) == 3


def test_ziehen_nur_im_bereich(tmp_path):
    g, calls = make(tmp_path)
    g.drag(1630, 400, 1630, 500, "preisachse", "Zoom")
    assert calls == [("drag", 1630, 400, 1630, 500)]
    with pytest.raises(SafetyError):
        g.drag(1630, 400, 1630, 950, "preisachse", "zu weit")
    with pytest.raises(SafetyError):
        g.drag(100, 100, 100, 200, "gibtsnicht", "x")
    assert len(calls) == 1


def test_tippen_nur_wenn_tradingview_vorne(tmp_path):
    g, calls = make(tmp_path)
    g.type_text("30845,00", "Entry")
    assert calls == [("type", "30845,00")]
    g2, calls2 = make(tmp_path, fg=("Chat - Discord", "Discord.exe"))
    with pytest.raises(SafetyError):
        g2.type_text("30845,00", "Entry")
    with pytest.raises(SafetyError):
        g2.press("esc", "x")
    assert calls2 == []


def test_click_in_bereich(tmp_path):
    g, calls = make(tmp_path)
    g.click_in("chart", 1333, 555, "Box", double=True)
    assert calls == [("dclick", 1333, 555)]
    with pytest.raises(SafetyError):
        g.click_in("chart", 1580, 555, "außerhalb")
    with pytest.raises(SafetyError):
        g.click_in("gibtsnicht", 100, 100, "x")
    assert len(calls) == 1


def test_nie_doppelklick_an_der_preisachse(tmp_path):
    cfg = dict(CFG, ablaeufe={"long": [{"punkt": [1590, 400], "doppel": True, "tippe": None}]})
    be = FakeBackend()
    g = Guard(cfg, Journal(tmp_path), backend=be, window_fn=lambda x, y: ("TradingView", ""),
              foreground_fn=lambda: ("TradingView", ""))
    with pytest.raises(SafetyError, match="Auto"):
        g.click(1590, 400, "aufgenommen, aber zu nah an der Achse", double=True)
    with pytest.raises(SafetyError):
        g.click_in("chart", 1595, 400, "auf der Achse")
    g.click_in("chart", 1500, 400, "weit genug weg", double=True)
    assert be.calls == [("dclick", 1500, 400)]
